import hashlib
import re
from types import SimpleNamespace

import pytest

from coursepilot.config import Settings
from coursepilot.store import Store


class FakeProvider:
    embedding_model = "test-embeddings"
    usage = {"input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0}

    def __init__(self, *args):
        self.calls = 0
        self.responses = []

    def embed(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * 64
            for term in re.findall(r"\w+", text.lower()):
                index = int(hashlib.sha256(term.encode()).hexdigest()[:8], 16) % 64
                vector[index] += 1
            vectors.append(vector)
        return vectors

    def respond(self, **kwargs):
        self.calls += 1
        return self.responses.pop(0)

    def structured(self, schema, instructions, data):
        import json
        source = json.loads(data)["sources"][0]["id"]
        if schema.__name__ == "Quiz":
            return schema.model_validate({"title": "Тест", "questions": [
                {"question": f"Вопрос {i}", "options": ["A", "B", "C", "D"], "correct": i,
                 "explanation": "Подтверждается материалом", "source_id": source} for i in range(3)]})
        if schema.__name__ == "Plan":
            return schema.model_validate({"goal": "Изучить метрики", "steps": [
                {"title": "Занятие", "task": "Повторить материал", "minutes": 20, "source_ids": [source]} for _ in range(3)]})
        raise ValueError("Unexpected schema")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.sqlite3")


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def config(tmp_path):
    return Settings(tmp_path, "", embedding_model="test-embeddings")


def response(text="", calls=None):
    return SimpleNamespace(output=calls or [], output_text=text)


def tool(name, arguments="{}"):
    return SimpleNamespace(type="function_call", name=name, arguments=arguments, call_id="call_1")
