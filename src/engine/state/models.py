from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


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


@dataclass
class AgentExecutionMetric:
    """One row per LLM call made through the Gateway -- an agent's call, or
    a single judge lens's call. Cost is always derived (see runtime/budget.py
    PRICE_TABLE), never accepted as a raw input.
    """

    run_id: int
    task_id: str
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    latency_ms: int
    actual_spend: Decimal | None  # None iff status == "error" before any usage was returned
    status: str  # "ok" | "error"
    error: str | None = None


@dataclass
class RunResult:
    run_id: int
    task_text: str
    workspace: Path
    passed: bool
    attempts: int
    verification_history: list[AttemptRecord] = field(default_factory=list)
