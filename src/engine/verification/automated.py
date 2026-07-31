import subprocess
import sys
from pathlib import Path

from engine.state.models import VerificationResult

TIMEOUT_SECONDS = 120


def _run(cmd: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {TIMEOUT_SECONDS}s"
    passed = result.returncode == 0
    detail = (result.stdout + result.stderr).strip() or "ok"
    return passed, detail


def run_automated_gates(workspace: Path) -> list[VerificationResult]:
    py_files = list(workspace.rglob("*.py"))
    if not py_files:
        return [VerificationResult("automated", True, "no Python files to check")]

    results: list[VerificationResult] = []

    passed, detail = _run([sys.executable, "-m", "ruff", "check", "."], workspace)
    results.append(VerificationResult("ruff", passed, detail))

    passed, detail = _run(
        [sys.executable, "-m", "mypy", "--ignore-missing-imports", "."], workspace
    )
    results.append(VerificationResult("mypy", passed, detail))

    test_files = list(workspace.rglob("test_*.py")) + list(workspace.rglob("*_test.py"))
    if test_files:
        passed, detail = _run([sys.executable, "-m", "pytest", "-q"], workspace)
        results.append(VerificationResult("pytest", passed, detail))
    else:
        results.append(VerificationResult("pytest", True, "no test files present"))

    return results
