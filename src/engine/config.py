import os
from dataclasses import dataclass
from decimal import Decimal
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
    max_tokens: int
    timeout_seconds: float
    max_agents: int
    planned_budget: Decimal
    # Separate, lower ceiling for api.py's /review endpoint: a single-shot
    # verification pass (3 judge calls, no agent generation, no retries)
    # costs a small fraction of a full generation run and shouldn't share
    # that run's budget.
    review_max_tokens: int
    review_planned_budget: Decimal


def load_config() -> Config:
    return Config(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        google_api_key=os.environ.get("GOOGLE_API_KEY"),
        max_retries=int(os.environ.get("ENGINE_MAX_RETRIES", "3")),
        db_path=Path(os.environ.get("ENGINE_DB_PATH", ".engine/state.db")),
        max_tokens=int(os.environ.get("ENGINE_MAX_TOKENS", "100000")),
        timeout_seconds=float(os.environ.get("ENGINE_TIMEOUT_SECONDS", "600")),
        max_agents=int(os.environ.get("ENGINE_MAX_AGENTS", "10")),
        # os.environ values are always str, so this never constructs a
        # Decimal from a float -- see runtime/budget.py's rules.
        planned_budget=Decimal(os.environ.get("ENGINE_PLANNED_BUDGET", "1.00")),
        review_max_tokens=int(os.environ.get("ENGINE_REVIEW_MAX_TOKENS", "10000")),
        review_planned_budget=Decimal(os.environ.get("ENGINE_REVIEW_PLANNED_BUDGET", "0.10")),
    )
