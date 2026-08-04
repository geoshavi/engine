from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from engine.providers.base import Provider


@dataclass
class AgentContext:
    task_text: str
    workspace: Path
    provider: Provider
    model: str
    feedback: str | None = None


@dataclass
class AgentOutput:
    files: dict[str, str]
    skipped_paths: list[str] = field(default_factory=list)


class Agent(Protocol):
    role: str

    def run(self, context: AgentContext) -> AgentOutput: ...
