from dataclasses import dataclass, field


@dataclass
class PlannedTask:
    agent_role: str
    subtask_text: str
    priority: int
    dependencies: list[str] = field(default_factory=list)


def plan_subtasks(task_text: str) -> list[PlannedTask]:
    """Deterministic default plan: research -> coding -> testing, in that
    order, each operating on the same top-level task text.

    There is no LLM-driven decomposition yet -- that is a later phase. This
    establishes the real, validated multi-agent plan *shape* so a smarter
    planner can slot in behind it later without changing any caller.
    """
    return [
        PlannedTask(agent_role="research", subtask_text=task_text, priority=1, dependencies=[]),
        PlannedTask(agent_role="coding", subtask_text=task_text, priority=2, dependencies=["research"]),
        PlannedTask(agent_role="testing", subtask_text=task_text, priority=3, dependencies=["coding"]),
    ]


def validate_plan(plan: list[PlannedTask], known_roles: set[str]) -> list[str]:
    """Structural validation only -- this never judges the *content* of a
    plan, only whether it is safe to execute: known roles, positive
    priorities, non-empty subtasks, and dependencies that refer to a role
    earlier in the plan. Mirrors how judge output is schema-validated before
    anything downstream trusts it.
    """
    errors: list[str] = []
    if not plan:
        return ["plan must contain at least one task"]

    seen_roles: list[str] = []
    for i, task in enumerate(plan):
        if not task.subtask_text.strip():
            errors.append(f"plan[{i}]: subtask_text must not be empty")
        if task.agent_role not in known_roles:
            errors.append(
                f"plan[{i}]: unknown agent_role {task.agent_role!r}, known roles: {sorted(known_roles)}"
            )
        if task.priority < 1:
            errors.append(f"plan[{i}]: priority must be >= 1, got {task.priority}")
        for dep in task.dependencies:
            if dep not in seen_roles:
                errors.append(
                    f"plan[{i}]: dependency {dep!r} must refer to a role earlier in the plan"
                )
        seen_roles.append(task.agent_role)

    return errors
