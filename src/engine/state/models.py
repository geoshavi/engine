from dataclasses import dataclass, field


@dataclass
class RunRecord:
    id: int
    task_text: str
    provider: str
    model: str
    status: str  # "running" | "passed" | "failed"
    attempts: int
    created_at: str
    finished_at: str | None


@dataclass
class VerificationResult:
    gate_name: str
    passed: bool
    detail: str


@dataclass
class AgentExecutionRecord:
    agent_name: str  # concrete class, e.g. "CodingAgent"
    agent_role: str  # registry key, e.g. "coding"
    subtask_text: str
    success: bool
    produced_files: list[str]
    error: str | None = None


@dataclass
class AttemptRecord:
    status: str  # "OK" | "UNVERIFIED" -- decided by verdict.gate, never by an LLM
    automated_results: list[VerificationResult]
    merged_critic: dict
    agent_executions: list[AgentExecutionRecord] = field(default_factory=list)
