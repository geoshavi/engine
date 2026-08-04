import shutil
from dataclasses import dataclass, field
from pathlib import Path

from engine.config import Config
from engine.orchestrator.agents.base import AgentContext
from engine.orchestrator.agents.registry import AGENT_REGISTRY, get_agent
from engine.orchestrator.planner import PlannedTask, plan_subtasks, validate_plan
from engine.providers.base import Provider
from engine.providers.registry import DEFAULT_MODELS
from engine.state import db
from engine.state.models import AgentExecutionRecord, AttemptRecord
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


def _invalid_plan_verdict(errors: list[str]) -> dict:
    return {
        "defects": [
            {
                "id": f"PLAN{i}",
                "category": "CORRECTNESS",
                "severity": "CRITICAL",
                "location": "planner",
                "fix": error,
            }
            for i, error in enumerate(errors)
        ],
        "verdict": "FAIL",
    }


def run_task(
    task_text: str, workspace: Path, provider: Provider, config: Config, provider_name: str = "anthropic"
) -> RunResult:
    models = DEFAULT_MODELS[provider_name]

    with db.connect(config.db_path) as conn:
        run_id = db.create_run(conn, task_text, provider_name, models["coding"])

        plan = plan_subtasks(task_text)
        plan_errors = validate_plan(plan, set(AGENT_REGISTRY))
        verification_history: list[AttemptRecord] = []
        passed = False
        feedback: str | None = None

        if plan_errors:
            # Structurally invalid and attempt-invariant under a deterministic
            # planner -- retrying would just reproduce the same broken plan,
            # so fail once instead of burning max_retries attempts on it.
            merged = _invalid_plan_verdict(plan_errors)
            verification_history.append(AttemptRecord("UNVERIFIED", [], merged))
            db.record_verification(conn, run_id, 1, [])
            db.record_defects(conn, run_id, 1, merged.get("defects", []))
            conn.commit()
            db.finish_run(conn, run_id, "failed", 1)
            return RunResult(
                run_id=run_id,
                task_text=task_text,
                workspace=workspace,
                passed=False,
                attempts=1,
                verification_history=verification_history,
            )

        ordered_plan: list[PlannedTask] = sorted(plan, key=lambda t: t.priority)

        for attempt in range(1, config.max_retries + 1):
            _reset_workspace(workspace)
            skipped_paths: list[str] = []
            provider_error: str | None = None
            agent_records: list[AgentExecutionRecord] = []

            for task in ordered_plan:
                agent = get_agent(task.agent_role)
                context = AgentContext(
                    task_text=task.subtask_text,
                    workspace=workspace,
                    provider=provider,
                    model=models[task.agent_role],
                    feedback=feedback,
                )
                try:
                    output = agent.run(context)
                except Exception as exc:  # noqa: BLE001 - a provider/network failure must not crash the run
                    provider_error = f"{type(exc).__name__}: {exc}"
                    agent_records.append(
                        AgentExecutionRecord(
                            agent_name=type(agent).__name__,
                            agent_role=task.agent_role,
                            subtask_text=task.subtask_text,
                            success=False,
                            produced_files=[],
                            error=provider_error,
                        )
                    )
                    break
                agent_records.append(
                    AgentExecutionRecord(
                        agent_name=type(agent).__name__,
                        agent_role=task.agent_role,
                        subtask_text=task.subtask_text,
                        success=True,
                        produced_files=sorted(output.files),
                        error=None,
                    )
                )
                skipped_paths.extend(output.skipped_paths)

            db.record_agent_executions(conn, run_id, attempt, agent_records)

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

            verification_history.append(AttemptRecord(status, automated_results, merged, agent_records))
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
