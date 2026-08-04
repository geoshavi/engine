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


@dataclass
class EvalRun:
    """One row per `engine bench` invocation. Created with placeholder (zero)
    aggregate fields before any case runs -- the id is baked into every
    case's task_id for agent_execution_metrics attribution, but the
    aggregates can only be computed once every case has finished.
    """

    id: int
    created_at: str
    git_commit_sha: str
    benchmark_name: str
    benchmark_version: str
    dataset_version: str
    total_cases: int
    correct_verdicts: int
    false_pass: int
    false_unverified: int
    category_accuracy: dict[str, float]
    average_cost: Decimal
    average_latency: int
    total_cost: Decimal


@dataclass
class EvalCaseResult:
    """One row per evaluated case. ``task_id`` is the exact value passed to
    run_verification() for this case, so agent_execution_metrics rows for
    it are found by an explicit (run_id, task_id) match -- never inferred
    from timestamps or insertion order. ``cost``/``latency_ms`` are the SUM
    of whatever metric rows exist for that task_id -- if ``error`` is set,
    that sum may reflect only the lenses that completed before the failure,
    not a full 3-lens measurement.
    """

    eval_run_id: int
    eval_case_id: str
    task_id: str
    expected_verdict: str  # "OK" | "UNVERIFIED"
    actual_verdict: str
    expected_defect_category: str | None
    detected_defect_categories: list[str]
    latency_ms: int
    cost: Decimal
    passed: bool
    error: str | None = None  # set iff run_verification() raised for this case
