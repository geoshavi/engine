from dataclasses import dataclass


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
