"""Turns a TaskAnalysis into a concrete, validated ExecutionPlan. Supersedes
the Phase-2 planner.py (PlannedTask/plan_subtasks/validate_plan) -- see
validate_execution_plan for exactly how each of its checks was preserved,
dropped, or extended.

Ordering is expressed structurally: a step's position in ``steps`` plus its
``depends_on`` list, not a separate priority/execution_order field.
``parallel_group`` is reserved for a later phase; execution stays strictly
sequential (steps run in list order) regardless of its value today.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from engine.config import Config
from engine.orchestrator.task_analyzer import TaskAnalysis


@dataclass
class ExecutionStep:
    agent: str
    depends_on: list[str] = field(default_factory=list)
    parallel_group: str | None = None
    # Unused this phase (falls back to the plan's task_text); reserved so a
    # future planner can give per-agent instructions without touching this
    # dataclass, the validator, and every test again.
    instruction: str | None = None


@dataclass
class ExecutionPlan:
    task_id: str
    task_text: str
    steps: list[ExecutionStep]
    max_tokens: int
    timeout_seconds: float
    max_agents: int
    planned_budget: Decimal


def build_execution_plan(analysis: TaskAnalysis, config: Config) -> ExecutionPlan:
    steps = [
        ExecutionStep(agent=role, depends_on=[analysis.required_roles[i - 1]] if i > 0 else [])
        for i, role in enumerate(analysis.required_roles)
    ]
    return ExecutionPlan(
        task_id=analysis.task_id,
        task_text=analysis.task_text,
        steps=steps,
        max_tokens=config.max_tokens,
        timeout_seconds=config.timeout_seconds,
        max_agents=config.max_agents,
        planned_budget=config.planned_budget,
    )


def validate_execution_plan(plan: ExecutionPlan, known_roles: set[str]) -> list[str]:
    """Structural validation only -- never judges plan *content*, only
    whether it's safe to execute. Mirrors how judge output is
    schema-validated before anything downstream trusts it.

    Checks ported from Phase 2's validate_plan:
      - non-empty plan
      - each step's agent is a known/registered role
      - each dependency refers to a role earlier in the plan
    Checks dropped, with reason:
      - "priority >= 1" -- there is no priority field anymore; ordering is
        expressed via list position + depends_on, so there's nothing left
        to validate.
    Checks changed in shape:
      - "subtask_text non-empty" -- ExecutionStep has no per-step text
        field (every step falls back to the plan's task_text), so this
        becomes a single plan-level check instead of one per step.
    New checks (new fields Phase 2 didn't have):
      - len(steps) <= max_agents
      - max_tokens, timeout_seconds, planned_budget are all positive
    """
    errors: list[str] = []

    if not plan.task_text.strip():
        errors.append("task_text must not be empty")
    if plan.max_tokens <= 0:
        errors.append(f"max_tokens must be positive, got {plan.max_tokens}")
    if plan.timeout_seconds <= 0:
        errors.append(f"timeout_seconds must be positive, got {plan.timeout_seconds}")
    if plan.planned_budget <= 0:
        errors.append(f"planned_budget must be positive, got {plan.planned_budget}")

    if not plan.steps:
        errors.append("plan must contain at least one step")
        return errors

    if len(plan.steps) > plan.max_agents:
        errors.append(f"plan has {len(plan.steps)} steps, exceeding max_agents ({plan.max_agents})")

    seen_agents: list[str] = []
    for i, step in enumerate(plan.steps):
        if step.agent not in known_roles:
            errors.append(f"steps[{i}]: unknown agent {step.agent!r}, known roles: {sorted(known_roles)}")
        for dep in step.depends_on:
            if dep not in seen_agents:
                errors.append(f"steps[{i}]: dependency {dep!r} must refer to an agent earlier in the plan")
        seen_agents.append(step.agent)

    return errors
