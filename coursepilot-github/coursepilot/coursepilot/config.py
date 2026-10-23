import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_key: str
    model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    rerank: bool = False


def settings() -> Settings:
    load_dotenv(ROOT / ".env.local", override=False)
    load_dotenv(ROOT / ".env", override=False)
    directory = Path(os.getenv("COURSEPILOT_DATA_DIR", str(ROOT / "runtime")))
    return Settings(directory, os.getenv("OPENAI_API_KEY", ""),
                    os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                    os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
                    os.getenv("RERANK_ENABLED", "false").lower() == "true")
