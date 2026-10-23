from coursepilot.agent import Agent
from coursepilot.ingest import ingest
from coursepilot.learning import Learning
from coursepilot.retrieval import Retriever
from conftest import response, tool


def test_search_answer_without_citation_fails_closed(store, provider):
    ingest(store, provider, "ml", "notes.md", b"Recall = TP/(TP+FN)")
    provider.responses = [response(calls=[tool("search_materials", '{"query":"Recall"}')]),
                          response("Unverified claim without a citation")]
    retriever = Retriever(store, provider)
    result = Agent(store, provider, retriever, Learning(store, provider, retriever)).chat("user", "ml", "Recall?")
    assert "не найден подтверждённый ответ" in result["answer"]


def test_no_sources_refuses(store, provider):
    provider.responses = [response(calls=[tool("search_materials", '{"query":"question"}')]),
                          response("Unsupported answer")]
    retriever = Retriever(store, provider)
    result = Agent(store, provider, retriever, Learning(store, provider, retriever)).chat("user", "ml", "Question?")
    assert "не найден подтверждённый ответ" in result["answer"]
