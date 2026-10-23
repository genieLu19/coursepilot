import hashlib
import io
import json
import re
from pathlib import Path

from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
MAX_CHARACTERS = 350_000


def extract(filename: str, content: bytes):
    if len(content) > MAX_BYTES:
        raise ValueError("Размер файла должен быть не больше 10 МБ.")
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > 150:
            raise ValueError("Поддерживается до 150 страниц в одном PDF.")
        pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    elif extension in {".md", ".txt"}:
        try:
            pages = [(0, content.decode("utf-8-sig"))]
        except UnicodeDecodeError as exc:
            raise ValueError("Сохрани текстовый файл в UTF-8.") from exc
    else:
        raise ValueError("Поддерживаются PDF с текстовым слоем, Markdown и TXT.")
    if sum(len(text) for _, text in pages) > MAX_CHARACTERS:
        raise ValueError("Документ слишком большой: максимум 350 000 символов.")
    if not any(text.strip() for _, text in pages):
        raise ValueError("Текст не найден. Для сканированного PDF сначала нужен OCR.")
    return pages


def split_sections(pages, size=1100, overlap=160):
    if not 0 <= overlap < size:
        raise ValueError("Overlap must be smaller than chunk size")
    section = "Материал"
    for page, text in pages:
        parts = re.split(r"(?m)^(#{1,6}\s+.+)$", text)
        for part in parts:
            if re.match(r"^#{1,6}\s+", part):
                section = part.lstrip("# ").strip()
                continue
            part = part.strip()
            start = 0
            while start < len(part):
                end = min(start + size, len(part))
                if end < len(part):
                    boundary = part.rfind(" ", start + size // 2, end)
                    if boundary > start:
                        end = boundary
                body = part[start:end].strip()
                if body:
                    yield {"page": page, "section": section, "text": body}
                if end == len(part):
                    break
                start = max(start + 1, end - overlap)


def ingest(store, llm, course, filename, content):
    source = Path(filename.replace("\\", "/")).name
    if not source or len(source) > 180:
        raise ValueError("Некорректное имя файла.")
    fragments = list(split_sections(extract(source, content)))
    if not fragments:
        raise ValueError("Документ не содержит индексируемого текста.")
    vectors = llm.embed([f["section"] + "\n" + f["text"] for f in fragments])
    if len(vectors) != len(fragments):
        raise ValueError("Не удалось получить эмбеддинги всех фрагментов.")
    chunks = []
    for index, (fragment, vector) in enumerate(zip(fragments, vectors)):
        identity = f"{course}:{source}:{index}:{fragment['text']}"
        chunks.append({**fragment, "id": hashlib.sha256(identity.encode()).hexdigest()[:16],
                       "course": course, "source": source, "model": llm.embedding_model,
                       "vector": json.dumps(vector)})
    store.replace_document(course, source, chunks)
    return {"source": source, "chunks": len(chunks), "course": course}
