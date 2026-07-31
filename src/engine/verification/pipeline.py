from pathlib import Path

from engine.providers.base import Provider
from engine.state.models import VerificationResult
from engine.verification.automated import run_automated_gates
from engine.verification.judge import run_judge_gates


def read_code_snapshot(workspace: Path) -> str:
    parts = []
    for path in sorted(workspace.rglob("*.py")):
        parts.append(f"# --- {path.relative_to(workspace)} ---\n{path.read_text()}")
    return "\n\n".join(parts) if parts else "(no code produced)"


def run_verification(
    workspace: Path, provider: Provider, judge_model: str, task_text: str
) -> tuple[bool, list[VerificationResult]]:
    automated_results = run_automated_gates(workspace)
    code_snapshot = read_code_snapshot(workspace)
    judge_results = run_judge_gates(provider, judge_model, task_text, code_snapshot)

    all_results = automated_results + judge_results
    automated_passed = all(r.passed for r in automated_results)
    judge_passed_count = sum(1 for r in judge_results if r.passed)
    judge_passed = judge_passed_count >= (len(judge_results) // 2 + 1) if judge_results else True

    return automated_passed and judge_passed, all_results


def build_retry_feedback(results: list[VerificationResult]) -> str:
    failed = [r for r in results if not r.passed]
    if not failed:
        return ""
    lines = ["The previous attempt failed verification. Fix these issues:"]
    for r in failed:
        lines.append(f"\n[{r.gate_name}]\n{r.detail}")
    return "\n".join(lines)
