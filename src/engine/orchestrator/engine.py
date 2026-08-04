import shutil
from dataclasses import dataclass, field
from pathlib import Path

from engine.config import Config
from engine.orchestrator.planner import plan_subtasks
from engine.orchestrator.subagent import generate_code, parse_files, write_files
from engine.providers.base import Provider
from engine.providers.registry import DEFAULT_MODELS
from engine.state import db
from engine.state.models import AttemptRecord
from engine.verification.pipeline import build_retry_feedback, run_verification


@dataclass
class RunResult:
    run_id: int
    task_text: str
    workspace: Path
    passed: bool
    attempts: int
    verification_history: list[AttemptRecord] = field(default_factory=list)


def _reset_workspace(workspace: Path) -> None:
    """Wipe the workspace before each attempt so a retry never sees files
    left over from a previous attempt that the new attempt didn't regenerate."""
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)


def _unsafe_path_verdict(skipped_paths: list[str]) -> dict:
    return {
        "defects": [
            {
                "id": f"PATH{i}",
                "category": "SECURITY",
                "severity": "CRITICAL",
                "location": path,
                "fix": (
                    "Write only relative paths inside the workspace. '..' traversal and "
                    "absolute paths are not allowed."
                ),
            }
            for i, path in enumerate(skipped_paths)
        ],
        "verdict": "FAIL",
    }


def _no_code_verdict() -> dict:
    return {
        "defects": [
            {
                "id": "NOCODE0",
                "category": "CORRECTNESS",
                "severity": "CRITICAL",
                "location": "workspace",
                "fix": "No FILE: blocks were produced. Output at least one file in the required format.",
            }
        ],
        "verdict": "FAIL",
    }


def _provider_error_verdict(message: str) -> dict:
    return {
        "defects": [
            {
                "id": "PROVIDER0",
                "category": "CORRECTNESS",
                "severity": "HIGH",
                "location": "provider",
                "fix": f"Provider call failed and will be retried: {message}",
            }
        ],
        "verdict": "FAIL",
    }


def run_task(
    task_text: str, workspace: Path, provider: Provider, config: Config, provider_name: str = "anthropic"
) -> RunResult:
    models = DEFAULT_MODELS[provider_name]

    with db.connect(config.db_path) as conn:
        run_id = db.create_run(conn, task_text, provider_name, models["coder"])

        subtasks = plan_subtasks(task_text)
        verification_history: list[AttemptRecord] = []
        passed = False
        feedback: str | None = None

        for attempt in range(1, config.max_retries + 1):
            _reset_workspace(workspace)
            skipped_paths: list[str] = []
            provider_error: str | None = None
            try:
                for subtask in subtasks:
                    response_text = generate_code(provider, models["coder"], subtask, feedback)
                    files = parse_files(response_text)
                    skipped_paths.extend(write_files(workspace, files))
            except Exception as exc:  # noqa: BLE001 - a provider/network failure must not crash the run
                provider_error = f"{type(exc).__name__}: {exc}"

            if provider_error is not None:
                status = "UNVERIFIED"
                merged = _provider_error_verdict(provider_error)
                automated_results: list = []
            elif skipped_paths:
                status = "UNVERIFIED"
                merged = _unsafe_path_verdict(skipped_paths)
                automated_results = []
            elif not any(workspace.rglob("*.py")):
                status = "UNVERIFIED"
                merged = _no_code_verdict()
                automated_results = []
            else:
                try:
                    status, merged, automated_results = run_verification(
                        workspace, provider, models["judge"], task_text
                    )
                except Exception as exc:  # noqa: BLE001 - same as above, for the judge calls
                    status = "UNVERIFIED"
                    merged = _provider_error_verdict(f"{type(exc).__name__}: {exc}")
                    automated_results = []

            verification_history.append(AttemptRecord(status, automated_results, merged))
            db.record_verification(conn, run_id, attempt, automated_results)
            db.record_defects(conn, run_id, attempt, merged.get("defects", []))
            conn.commit()

            passed = status == "OK"
            if passed:
                break
            feedback = build_retry_feedback(merged)

        db.finish_run(conn, run_id, "passed" if passed else "failed", len(verification_history))

    return RunResult(
        run_id=run_id,
        task_text=task_text,
        workspace=workspace,
        passed=passed,
        attempts=len(verification_history),
        verification_history=verification_history,
    )
