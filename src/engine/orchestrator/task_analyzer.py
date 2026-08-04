"""Task analysis is a separate responsibility from execution: this module
only classifies an incoming task and decides which agents it needs, in what
order. It never dispatches an agent or calls the Gateway itself -- that's
execution_plan.py (turning the analysis into a concrete plan) and
manager.py (running it).

Classification is deterministic for this phase, not LLM-driven: every task
gets the same research -> coding -> testing sequence, matching what
plan_subtasks did before it. TaskAnalysis is a real, validated shape a
smarter (LLM-driven) classifier can sit behind later without changing any
caller.
"""

import uuid
from dataclasses import dataclass, field

DEFAULT_ROLE_SEQUENCE = ["research", "coding", "testing"]


@dataclass
class TaskAnalysis:
    task_id: str
    task_text: str
    task_class: str
    required_roles: list[str] = field(default_factory=list)


def classify_task(task_text: str) -> TaskAnalysis:
    return TaskAnalysis(
        task_id=uuid.uuid4().hex,
        task_text=task_text,
        task_class="general",
        required_roles=list(DEFAULT_ROLE_SEQUENCE),
    )
