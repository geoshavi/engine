from dataclasses import dataclass, field
from pathlib import Path

from engine.config import Config
from engine.orchestrator.planner import plan_subtasks
from engine.orchestrator.subagent import generate_code, parse_files, write_files
from engine.providers.base import Provider
from engine.providers.registry import DEFAULT_MODELS
from engine.state import db
from engine.state.models import VerificationResult
from engine.verification.pipeline import build_retry_feedback, run_verification


@dataclass
class RunResult:
    run_id: int
    task_text: str
    workspace: Path
    passed: bool
    attempts: int
    verification_history: list[list[VerificationResult]] = field(default_factory=list)


def run_task(
    task_text: str, workspace: Path, provider: Provider, config: Config, provider_name: str = "anthropic"
) -> RunResult:
    models = DEFAULT_MODELS[provider_name]
    workspace.mkdir(parents=True, exist_ok=True)

    with db.connect(config.db_path) as conn:
        run_id = db.create_run(conn, task_text, provider_name, models["coder"])

        subtasks = plan_subtasks(task_text)
        verification_history: list[list[VerificationResult]] = []
        passed = False
        feedback: str | None = None

        for attempt in range(1, config.max_retries + 1):
            for subtask in subtasks:
                response_text = generate_code(provider, models["coder"], subtask, feedback)
                files = parse_files(response_text)
                write_files(workspace, files)

            passed, results = run_verification(workspace, provider, models["judge"], task_text)
            verification_history.append(results)
            db.record_verification(conn, run_id, attempt, results)

            if passed:
                break
            feedback = build_retry_feedback(results)

        db.finish_run(conn, run_id, "passed" if passed else "failed", len(verification_history))

    return RunResult(
        run_id=run_id,
        task_text=task_text,
        workspace=workspace,
        passed=passed,
        attempts=len(verification_history),
        verification_history=verification_history,
    )
