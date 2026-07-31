import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str | None
    openai_api_key: str | None
    google_api_key: str | None
    max_retries: int
    db_path: Path


def load_config() -> Config:
    return Config(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        google_api_key=os.environ.get("GOOGLE_API_KEY"),
        max_retries=int(os.environ.get("ENGINE_MAX_RETRIES", "3")),
        db_path=Path(os.environ.get("ENGINE_DB_PATH", ".engine/state.db")),
    )
