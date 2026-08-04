"""Owns the retry/dispatch loop: turns a validated ExecutionPlan into agent
calls, one at a time, in plan order, coordinating through the Agent
Registry. Agents never call each other or the Gateway on their own outside
of the AgentContext this module hands them for a single call -- all
communication is mediated here.

Execution is strictly sequential this phase: steps run in list order
regardless of ``parallel_group``, which is reserved for a later phase.

Two failure modes are terminal for the whole run (not retried, unlike a
provider hiccup or bad generation): budget exhaustion and the run deadline.
Retrying either can't fix it -- the budget doesn't replenish and the clock
doesn't reset -- so both stop the run immediately instead of burning the
remaining attempts.
"""

import shutil
import time
from pathlib import Path

from engine.config import Config
from engine.orchestrator.agents.base import AgentContext
from engine.orchestrator.agents.registry import AGENT_REGISTRY, get_agent
from engine.orchestrator.execution_plan import ExecutionPlan, validate_execution_plan
from engine.runtime.budget import BudgetController, BudgetExceededError
from engine.runtime.gateway import LLMGateway
from engine.state import db
from engine.state.models import AgentExecutionRecord, AttemptRecord, RunResult
from engine.verification.pipeline import build_retry_feedback, run_verification

# Per-call ceiling; the timeout actually passed to each call is
# min(this, time remaining until the plan's overall deadline), so a call
# near the end of the run's time budget can't itself blow past it.
DEFAULT_CALL_TIMEOUT_SECONDS = 120.0


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


def _budget_exceeded_verdict(message: str) -> dict:
    return {
        "defects": [
            {
                "id": "BUDGET0",
                "category": "CORRECTNESS",
                "severity": "CRITICAL",
                "location": "budget",
                "fix": message,
            }
        ],
        "verdict": "FAIL",
    }


def _deadline_exceeded_verdict(message: str) -> dict:
    return {
        "defects": [
            {
                "id": "DEADLINE0",
                "category": "CORRECTNESS",
                "severity": "CRITICAL",
                "location": "run_deadline",
                "fix": message,
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


_VERDICT_BY_KIND = {
    "deadline": _deadline_exceeded_verdict,
    "budget": _budget_exceeded_verdict,
    "provider": _provider_error_verdict,
}
# "budget" and "deadline" are terminal (never retried); "provider" is not.
_TERMINAL_KINDS = {"deadline", "budget"}


class OrchestratorManager:
    def __init__(self, gateway: LLMGateway, models: dict[str, str]) -> None:
        self._gateway = gateway
        self._models = models

    def execute(
        self, plan: ExecutionPlan, workspace: Path, config: Config, provider_name: str
    ) -> RunResult:
        plan_errors = validate_execution_plan(plan, set(AGENT_REGISTRY))

        with db.connect(config.db_path) as conn:
            run_id = db.create_run(conn, plan.task_text, provider_name, self._models["coding"])

            if plan_errors:
                # Structurally invalid and attempt-invariant -- retrying
                # would just reproduce the same broken plan, so fail once
                # instead of burning max_retries attempts on it.
                merged = _invalid_plan_verdict(plan_errors)
                history = [AttemptRecord("UNVERIFIED", [], merged)]
                db.record_verification(conn, run_id, 1, [])
                db.record_defects(conn, run_id, 1, merged.get("defects", []))
                conn.commit()
                db.finish_run(conn, run_id, "failed", 1)
                return RunResult(run_id, plan.task_text, workspace, False, 1, history)

            budget = BudgetController(max_tokens=plan.max_tokens, planned_budget=plan.planned_budget)
            deadline = time.monotonic() + plan.timeout_seconds
            verification_history: list[AttemptRecord] = []
            passed = False
            feedback: str | None = None

            for attempt in range(1, config.max_retries + 1):
                _reset_workspace(workspace)
                skipped_paths: list[str] = []
                terminal_error: tuple[str, str] | None = None
                agent_records: list[AgentExecutionRecord] = []

                for step in plan.steps:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        terminal_error = ("deadline", f"run deadline of {plan.timeout_seconds}s exceeded")
                        break

                    agent = get_agent(step.agent)
                    context = AgentContext(
                        task_text=step.instruction or plan.task_text,
                        workspace=workspace,
                        gateway=self._gateway,
                        budget=budget,
                        model=self._models[step.agent],
                        run_id=run_id,
                        task_id=plan.task_id,
                        conn=conn,
                        timeout_seconds=min(DEFAULT_CALL_TIMEOUT_SECONDS, remaining),
                        feedback=feedback,
                    )
                    try:
                        output = agent.run(context)
                    except BudgetExceededError as exc:
                        terminal_error = ("budget", str(exc))
                    except Exception as exc:  # noqa: BLE001 - a provider/network failure must not crash the run
                        terminal_error = ("provider", f"{type(exc).__name__}: {exc}")

                    if terminal_error is not None:
                        agent_records.append(
                            AgentExecutionRecord(
                                agent_name=type(agent).__name__,
                                agent_role=step.agent,
                                subtask_text=context.task_text,
                                success=False,
                                produced_files=[],
                                error=terminal_error[1],
                            )
                        )
                        break

                    agent_records.append(
                        AgentExecutionRecord(
                            agent_name=type(agent).__name__,
                            agent_role=step.agent,
                            subtask_text=context.task_text,
                            success=True,
                            produced_files=sorted(output.files),
                            error=None,
                        )
                    )
                    skipped_paths.extend(output.skipped_paths)

                db.record_agent_executions(conn, run_id, attempt, agent_records)

                has_code = any(workspace.rglob("*.py"))
                verify_result: tuple[str, dict, list] | None = None
                if terminal_error is None and not skipped_paths and has_code:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        terminal_error = (
                            "deadline",
                            f"run deadline of {plan.timeout_seconds}s exceeded before verification",
                        )
                    else:
                        try:
                            verify_result = run_verification(
                                workspace,
                                self._gateway,
                                budget,
                                self._models["judge"],
                                plan.task_text,
                                run_id=run_id,
                                task_id=plan.task_id,
                                conn=conn,
                                timeout_seconds=min(DEFAULT_CALL_TIMEOUT_SECONDS, remaining),
                            )
                        except BudgetExceededError as exc:
                            terminal_error = ("budget", str(exc))
                        except Exception as exc:  # noqa: BLE001 - same as above, for the judge calls
                            terminal_error = ("provider", f"{type(exc).__name__}: {exc}")

                if terminal_error is not None:
                    kind, message = terminal_error
                    status = "UNVERIFIED"
                    merged = _VERDICT_BY_KIND[kind](message)
                    automated_results: list = []
                elif skipped_paths:
                    status = "UNVERIFIED"
                    merged = _unsafe_path_verdict(skipped_paths)
                    automated_results = []
                elif not has_code:
                    status = "UNVERIFIED"
                    merged = _no_code_verdict()
                    automated_results = []
                else:
                    assert verify_result is not None
                    status, merged, automated_results = verify_result

                verification_history.append(AttemptRecord(status, automated_results, merged, agent_records))
                db.record_verification(conn, run_id, attempt, automated_results)
                db.record_defects(conn, run_id, attempt, merged.get("defects", []))
                conn.commit()

                passed = status == "OK"
                terminal_hit = terminal_error is not None and terminal_error[0] in _TERMINAL_KINDS
                if passed or terminal_hit:
                    break
                feedback = build_retry_feedback(merged)

            db.finish_run(conn, run_id, "passed" if passed else "failed", len(verification_history))

        return RunResult(
            run_id=run_id,
            task_text=plan.task_text,
            workspace=workspace,
            passed=passed,
            attempts=len(verification_history),
            verification_history=verification_history,
        )
