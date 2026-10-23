"""Opt-in live integration check. Uses paid OpenAI requests."""
import json
from pathlib import Path

from openai import APIError

from coursepilot.agent import Agent
from coursepilot.config import settings
from coursepilot.ingest import ingest
from coursepilot.learning import Learning
from coursepilot.llm import OpenAIProvider
from coursepilot.retrieval import Retriever
from coursepilot.store import Store


def main():
    config = settings()
    store = Store(config.data_dir / "smoke.sqlite3")
    llm = OpenAIProvider(config, store)
    text = "# Метрики\n\nRecall = TP / (TP + FN). Precision = TP / (TP + FP). "
    text += "F1 — гармоническое среднее precision и recall. Accuracy — доля верных предсказаний. "
    text += "При дисбалансе классов accuracy может скрывать ошибки редкого класса."
    ingest(store, llm, "smoke", "metrics.md", text.encode())
    retriever = Retriever(store, llm)
    learning = Learning(store, llm, retriever)
    agent = Agent(store, llm, retriever, learning)
    answer = agent.chat("smoke", "smoke", "Как рассчитать Recall? Ответь по материалам со ссылкой.")
    quiz = learning.create_quiz("smoke", "smoke", "Метрики классификации")
    graded = store.grade("smoke", quiz["id"], [0, 0, 0])
    plan = learning.build_plan("smoke", "smoke", "Разобраться в метриках", 30)
    refusal = agent.chat("smoke", "smoke", "Как приготовить борщ? Есть ли ответ в материалах?")
    report = {"status": "passed", "answer": answer, "quiz_id": quiz["id"],
              "quiz_questions": len(quiz["questions"]), "score": graded["score"],
              "plan_steps": len(plan["steps"]), "out_of_scope_answer": refusal["answer"], "usage": llm.usage}
    target = Path("runtime/live_smoke.json")
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "quiz_questions": len(quiz["questions"]),
                      "plan_steps": len(plan["steps"]), "report": str(target)}))


if __name__ == "__main__":
    try:
        main()
    except APIError as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "code": getattr(exc, "code", None),
                          "status_code": getattr(exc, "status_code", None)}))
        raise SystemExit(1)
