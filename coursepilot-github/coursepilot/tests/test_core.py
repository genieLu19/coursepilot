import json

import pytest

from coursepilot.ingest import extract, ingest, split_sections
from coursepilot.learning import Learning
from coursepilot.retrieval import Retriever, bm25, rrf


def seed(store, provider, course="ml"):
    ingest(store, provider, course, "metrics.md", "# Метрики\n\nRecall = TP / (TP + FN). Полнота классификации.".encode())


def test_chunking_preserves_headings_pages_and_tail():
    text = "# Тема\n" + "важный текст " * 300 + "КОНЕЦ"
    chunks = list(split_sections([(7, text)], size=150, overlap=25))
    assert all(c["page"] == 7 and c["section"] == "Тема" for c in chunks)
    assert chunks[-1]["text"].endswith("КОНЕЦ")
    assert all(len(c["text"]) <= 150 for c in chunks)


def test_invalid_overlap():
    with pytest.raises(ValueError):
        list(split_sections([(0, "data")], size=10, overlap=10))


@pytest.mark.parametrize("filename,data", [("a.exe", b"abc"), ("a.txt", b""), ("a.txt", b"\xff"), ("a.md", b"x" * (10 * 1024 * 1024 + 1))],
                         ids=["unsupported", "empty", "encoding", "oversized"])
def test_bad_uploads(filename, data):
    with pytest.raises(ValueError):
        extract(filename, data)


def test_reindex_replaces_old_document_and_removes_stale_chunks(store, provider):
    seed(store, provider)
    first_id = store.chunks("ml")[0]["id"]
    seed(store, provider)
    assert len(store.chunks("ml")) == 1
    assert store.chunks("ml")[0]["id"] == first_id
    ingest(store, provider, "ml", "metrics.md", b"# Changed\nNew content")
    assert len(store.chunks("ml")) == 1
    assert store.chunks("ml")[0]["id"] != first_id


def test_failed_embeddings_preserve_document(store, provider):
    seed(store, provider)
    before = store.chunks("ml")
    provider.embed = lambda _: (_ for _ in ()).throw(ValueError("network"))
    with pytest.raises(ValueError):
        ingest(store, provider, "ml", "metrics.md", b"New content")
    assert store.chunks("ml") == before


def test_course_isolation_in_retrieval(store, provider):
    seed(store, provider, "ml")
    ingest(store, provider, "other", "secret.md", b"private another course")
    result = Retriever(store, provider).search("ml", "Recall", mode="hybrid")
    assert result and all(c["course"] == "ml" for c in result)
    assert "vector" not in result[0]


def test_embedding_model_mismatch(store, provider):
    seed(store, provider)
    provider.embedding_model = "another"
    with pytest.raises(ValueError, match="эмбеддингов"):
        Retriever(store, provider).search("ml", "Recall")


def test_lexical_has_no_results_for_unmatched_query(store, provider):
    seed(store, provider)
    assert Retriever(store, provider).search("ml", "астрономия", mode="lexical") == []


def test_bm25_and_rrf():
    scores = bm25("SSO_ERROR_42", ["common login", "SSO_ERROR_42 authorization"])
    assert scores[1] > scores[0]
    assert rrf([[1, 2], [2, 3]])[0] == 2


def test_history_and_progress_are_scoped(store):
    store.save_turn("alice", "ml", "question", "answer")
    assert store.history("bob", "ml") == []
    assert store.history("alice", "other") == []
    assert len(store.history("alice", "ml")) == 2


def test_quiz_hides_keys_and_grades_once(store, provider):
    seed(store, provider)
    learning = Learning(store, provider, Retriever(store, provider))
    quiz = learning.create_quiz("alice", "ml", "Recall")
    assert all("correct" not in q and "explanation" not in q for q in quiz["questions"])
    with pytest.raises(ValueError):
        store.grade("bob", quiz["id"], [0, 1, 2])
    assert store.grade("alice", quiz["id"], [0, 1, 2])["score"] == 1
    assert store.grade("alice", quiz["id"], [3, 3, 3])["score"] == 1
    assert store.progress("alice", "ml")["completed_quizzes"] == 1
    assert store.progress("alice", "other")["completed_quizzes"] == 0


def test_quiz_rejects_wrong_answer_count(store, provider):
    seed(store, provider)
    learning = Learning(store, provider, Retriever(store, provider))
    quiz = learning.create_quiz("alice", "ml", "Recall")
    with pytest.raises(ValueError):
        store.grade("alice", quiz["id"], [0])


def test_plan_persists_and_validates_budget(store, provider):
    seed(store, provider)
    learning = Learning(store, provider, Retriever(store, provider))
    plan = learning.build_plan("alice", "ml", "Recall", 30)
    assert store.progress("alice", "ml")["plan"] == plan
    with pytest.raises(ValueError):
        learning.build_plan("alice", "ml", "Recall", 3)
