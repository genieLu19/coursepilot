import json

from fastapi.testclient import TestClient

from coursepilot.agent import Agent
from coursepilot.api import create_app
from coursepilot.ingest import ingest
from coursepilot.learning import Learning
from coursepilot.retrieval import Retriever
from conftest import FakeProvider, response, tool


def test_api_static_health_upload_and_session(config):
    app = create_app(config, FakeProvider)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/status").json()["configured"] is False
        assert "coursepilot_session" in client.cookies
        assert client.get("/static/app.js").status_code == 200
        assert client.post("/api/documents", data={"course": "ml"}, files={"file": ("notes.md", b"# Recall\nTP/(TP+FN)")}).status_code == 200
        assert client.get("/api/courses").json()[0]["id"] == "ml"
        assert client.post("/api/chat", json={"course": "empty", "message": "Hello"}).status_code == 400
        assert client.post("/api/quiz", json={"course": "ml", "topic": "Recall"}).status_code == 200


def test_cross_origin_requests_blocked(config):
    with TestClient(create_app(config, FakeProvider)) as client:
        response_ = client.post("/api/seed", headers={"Origin": "https://untrusted.example"})
        assert response_.status_code == 403


def test_upload_path_traversal_is_not_written(config):
    with TestClient(create_app(config, FakeProvider)) as client:
        result = client.post("/api/documents", data={"course": "ml"}, files={"file": ("../../notes.md", b"Safe content")})
        assert result.json()["source"] == "notes.md"
        assert client.post("/api/documents", data={"course": "../../x"}, files={"file": ("notes.md", b"text")}).status_code == 400


def test_agent_calls_tools_and_returns_sources(store, provider):
    ingest(store, provider, "ml", "notes.md", b"# Recall\nRecall = TP / (TP + FN)")
    source_id = store.chunks("ml")[0]["id"]
    provider.responses = [response(calls=[tool("search_materials", '{"query":"Recall"}')]),
                          response(f"Recall = TP/(TP+FN) [{source_id}]")]
    retriever = Retriever(store, provider)
    result = Agent(store, provider, retriever, Learning(store, provider, retriever)).chat("alice", "ml", "Recall?")
    assert result["sources"][0]["id"] == source_id
    assert result["trace"][0]["tool"] == "search_materials"
    assert len(store.history("alice", "ml")) == 2


def test_agent_blocks_invented_citation(store, provider):
    provider.responses = [response("Факт [0123456789abcdef]")]
    retriever = Retriever(store, provider)
    result = Agent(store, provider, retriever, Learning(store, provider, retriever)).chat("alice", "ml", "Вопрос")
    assert "Не удалось подтвердить" in result["answer"]


def test_tool_budget_stops_infinite_loop(store, provider):
    provider.responses = [response(calls=[tool("get_progress")]) for _ in range(10)]
    retriever = Retriever(store, provider)
    result = Agent(store, provider, retriever, Learning(store, provider, retriever)).chat("alice", "ml", "Прогресс")
    assert provider.calls == 6
    assert "лимит" in result["answer"]
