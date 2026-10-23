"""Evaluate retrieval independently of answer generation. Lexical mode is offline."""
import argparse
import hashlib
import json
import statistics
import tempfile
import time
from pathlib import Path

from coursepilot.config import ROOT, settings
from coursepilot.ingest import extract, ingest, split_sections
from coursepilot.llm import OpenAIProvider
from coursepilot.retrieval import Retriever
from coursepilot.store import Store


def run(mode):
    config = settings()
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    questions = json.loads((ROOT / "evaluation" / "questions.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(dir=runtime) as temporary:
        store = Store(Path(temporary) / "eval.sqlite3")
        llm = OpenAIProvider(config, store)
        for path in sorted((ROOT / "data" / "sample_course").glob("*.md")):
            if mode == "lexical":
                chunks = []
                for i, fragment in enumerate(split_sections(extract(path.name, path.read_bytes()))):
                    chunks.append({**fragment, "id": hashlib.sha256(f"{path.name}:{i}".encode()).hexdigest()[:16],
                                   "course": "eval", "source": path.name, "model": "offline", "vector": "[]"})
                store.replace_document("eval", path.name, chunks)
            else:
                ingest(store, llm, "eval", path.name, path.read_bytes())
        retriever = Retriever(store, llm)
        results, reciprocal, hits, timings = [], [], [], []
        for q in questions:
            if q.get("unanswerable"):
                continue
            start = time.perf_counter()
            found = retriever.search("eval", q["question"], mode=mode)
            timings.append((time.perf_counter() - start) * 1000)
            positions = [i + 1 for i, source in enumerate(found)
                         if source["source"] == q["source"] and source["section"] == q["section"]]
            hits.append(bool(positions))
            reciprocal.append(1 / positions[0] if positions else 0)
            results.append({"question": q["question"], "first_relevant_rank": positions[0] if positions else None,
                            "retrieved": [{"source": s["source"], "section": s["section"]} for s in found]})
        return {"mode": mode, "answerable_questions": len(hits), "corpus_chunks": len(store.chunks("eval")),
                "hit_rate_at_5": statistics.mean(hits), "mrr_at_5": statistics.mean(reciprocal),
                "median_latency_ms": statistics.median(timings), "usage": llm.usage,
                "scope": "Retrieval only; one annotated relevant section per question. No answer-quality claim.",
                "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["lexical", "dense", "hybrid", "rerank"], default="lexical")
    parser.add_argument("--output", type=Path, default=Path("evaluation/results.json"))
    args = parser.parse_args()
    report = run(args.mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False, indent=2))
