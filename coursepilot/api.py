import logging
import re
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import APIConnectionError, APIError, AuthenticationError, RateLimitError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import Agent
from .config import ROOT, settings
from .ingest import MAX_BYTES, ingest
from .learning import Learning
from .llm import OpenAIProvider
from .retrieval import Retriever
from .schemas import ChatInput, GradeInput, PlanInput, TopicInput
from .store import Store


def create_app(config=None, provider_factory=OpenAIProvider):
    config = config or settings()
    store = Store(config.data_dir / "coursepilot.sqlite3")
    app = FastAPI(title="CoursePilot", version="0.1.0", description="AI learning assistant with hybrid RAG")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    app.state.store, app.state.config = store, config

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.headers.get('host')}"
            if origin and origin != expected:
                return JSONResponse({"detail": "Запрос с другого сайта запрещён."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'")
        if request.url.path in {"/docs", "/redoc"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                "img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'")
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(AuthenticationError)
    async def auth_error(request, exc):
        return JSONResponse({"detail": "OpenAI отклонил ключ. Проверь его срок действия и перезапусти сервис."}, status_code=503)

    @app.exception_handler(RateLimitError)
    async def quota_error(request, exc):
        detail = "Лимит запросов OpenAI достигнут. Подожди и повтори запрос."
        if exc.code in {"billing_not_active", "insufficient_quota"}:
            detail = "OpenAI API: биллинг не активирован или исчерпана квота. Проверь Billing в OpenAI Platform."
        return JSONResponse({"detail": detail}, status_code=503)

    @app.exception_handler(APIConnectionError)
    async def connection_error(request, exc):
        return JSONResponse({"detail": "Нет соединения с OpenAI. Проверь подключение и доступность API."}, status_code=503)

    @app.exception_handler(APIError)
    async def api_error(request, exc):
        return JSONResponse({"detail": "OpenAI не обработал запрос. Проверь доступ к выбранной модели."}, status_code=503)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        logging.getLogger("coursepilot").error("Request failed: %s", type(exc).__name__)
        return JSONResponse({"detail": "Не удалось обработать запрос. Проверь файл или повтори действие."}, status_code=500)

    def session(request: Request, response: Response):
        value = request.cookies.get("coursepilot_session", "")
        try:
            value = str(uuid.UUID(value))
        except ValueError:
            value = str(uuid.uuid4())
            response.set_cookie("coursepilot_session", value, httponly=True,
                                samesite="strict", max_age=60 * 60 * 24 * 365)
        return value

    def services():
        llm = provider_factory(config, store)
        retriever = Retriever(store, llm, config.rerank)
        learning = Learning(store, llm, retriever)
        return llm, retriever, learning

    @app.get("/api/status")
    def status(profile=Depends(session)):
        return {"configured": bool(config.api_key), "model": config.model,
                "embedding_model": config.embedding_model, "rerank": config.rerank}

    @app.get("/api/courses")
    def courses():
        return store.courses()

    @app.get("/api/progress")
    def progress(course: str, profile=Depends(session)):
        return store.progress(profile, course)

    @app.get("/api/history")
    def history(course: str, profile=Depends(session)):
        return store.history(profile, course)

    @app.post("/api/seed")
    def seed():
        llm, _, _ = services()
        results = []
        for path in sorted((ROOT / "data" / "sample_course").glob("*.md")):
            results.append(ingest(store, llm, "ml-foundations", path.name, path.read_bytes()))
        if not results:
            raise ValueError("Не найдены файлы примера курса.")
        return results

    @app.post("/api/documents")
    def upload(course: str = Form(...), file: UploadFile = File(...)):
        if not re.fullmatch(r"[a-z0-9_-]{1,80}", course):
            raise ValueError("ID курса: латинские строчные буквы, цифры, дефис или подчёркивание.")
        content = file.file.read(MAX_BYTES + 1)
        llm, _, _ = services()
        return ingest(store, llm, course, file.filename or "", content)

    @app.post("/api/chat")
    def chat(body: ChatInput, profile=Depends(session)):
        if not store.chunks(body.course):
            raise ValueError("Сначала добавь материалы в выбранный курс.")
        llm, retriever, learning = services()
        return Agent(store, llm, retriever, learning).chat(profile, body.course, body.message)

    @app.post("/api/quiz")
    def quiz(body: TopicInput, profile=Depends(session)):
        _, _, learning = services()
        return learning.create_quiz(profile, body.course, body.topic)

    @app.get("/api/quiz/{quiz_id}")
    def get_quiz(quiz_id: str, profile=Depends(session)):
        _, _, learning = services()
        return learning.public_quiz(profile, quiz_id)

    @app.post("/api/quiz/{quiz_id}/grade")
    def grade(quiz_id: str, body: GradeInput, profile=Depends(session)):
        return store.grade(profile, quiz_id, body.answers)

    @app.post("/api/plan")
    def plan(body: PlanInput, profile=Depends(session)):
        _, _, learning = services()
        return learning.build_plan(profile, body.course, body.topic, body.minutes_per_day)

    @app.get("/")
    def index():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return app


app = create_app()
