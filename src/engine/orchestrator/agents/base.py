import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from engine.runtime.budget import BudgetController
from engine.runtime.gateway import LLMGateway


@dataclass
class AgentContext:
    task_text: str
    workspace: Path
    gateway: LLMGateway
    budget: BudgetController
    model: str
    run_id: int
    task_id: str
    conn: sqlite3.Connection | None = None
    timeout_seconds: float | None = None
    feedback: str | None = None


@dataclass
class AgentOutput:
    files: dict[str, str]
    skipped_paths: list[str] = field(default_factory=list)


class Agent(Protocol):
    role: str

    def run(self, context: AgentContext) -> AgentOutput: ...
