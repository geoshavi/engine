from decimal import Decimal
from pathlib import Path

from engine.config import Config
from engine.orchestrator.execution_plan import (
    ExecutionStep,
    build_execution_plan,
    validate_execution_plan,
)
from engine.orchestrator.task_analyzer import classify_task

KNOWN_ROLES = {"research", "coding", "testing", "refactoring"}


def _config(tmp_path: Path) -> Config:
    return Config(
        anthropic_api_key="fake",
        openai_api_key=None,
        google_api_key=None,
        max_retries=3,
        db_path=tmp_path / "state.db",
        max_tokens=100_000,
        timeout_seconds=600.0,
        max_agents=10,
        planned_budget=Decimal("1.00"),
        review_max_tokens=10_000,
        review_planned_budget=Decimal("0.10"),
    )


def test_build_execution_plan_returns_research_coding_testing_in_order(tmp_path: Path) -> None:
    analysis = classify_task("do the thing")
    plan = build_execution_plan(analysis, _config(tmp_path))

    assert [s.agent for s in plan.steps] == ["research", "coding", "testing"]
    assert plan.steps[0].depends_on == []
    assert plan.steps[1].depends_on == ["research"]
    assert plan.steps[2].depends_on == ["coding"]
    assert plan.task_text == "do the thing"
    assert plan.task_id == analysis.task_id


def test_build_execution_plan_copies_budget_fields_from_config(tmp_path: Path) -> None:
    config = _config(tmp_path)
    plan = build_execution_plan(classify_task("do the thing"), config)

    assert plan.max_tokens == config.max_tokens
    assert plan.timeout_seconds == config.timeout_seconds
    assert plan.max_agents == config.max_agents
    assert plan.planned_budget == config.planned_budget


def test_validate_execution_plan_accepts_the_default_plan(tmp_path: Path) -> None:
    plan = build_execution_plan(classify_task("do the thing"), _config(tmp_path))
    assert validate_execution_plan(plan, KNOWN_ROLES) == []


def test_validate_execution_plan_rejects_empty_plan(tmp_path: Path) -> None:
    plan = build_execution_plan(classify_task("do the thing"), _config(tmp_path))
    plan.steps = []
    assert validate_execution_plan(plan, KNOWN_ROLES) != []


def test_validate_execution_plan_rejects_empty_task_text(tmp_path: Path) -> None:
    plan = build_execution_plan(classify_task("do the thing"), _config(tmp_path))
    plan.task_text = "   "
    errors = validate_execution_plan(plan, KNOWN_ROLES)
    assert any("task_text" in e for e in errors)


def test_validate_execution_plan_rejects_unknown_role(tmp_path: Path) -> None:
    plan = build_execution_plan(classify_task("do the thing"), _config(tmp_path))
    errors = validate_execution_plan(plan, {"coding", "testing"})
    assert any("research" in e for e in errors)


def test_validate_execution_plan_rejects_forward_dependency(tmp_path: Path) -> None:
    plan = build_execution_plan(classify_task("do the thing"), _config(tmp_path))
    plan.steps = [
        ExecutionStep(agent="coding", depends_on=["testing"]),
        ExecutionStep(agent="testing", depends_on=[]),
    ]
    errors = validate_execution_plan(plan, KNOWN_ROLES)
    assert any("testing" in e for e in errors)


def test_validate_execution_plan_rejects_too_many_steps_for_max_agents(tmp_path: Path) -> None:
    plan = build_execution_plan(classify_task("do the thing"), _config(tmp_path))
    plan.max_agents = 1
    errors = validate_execution_plan(plan, KNOWN_ROLES)
    assert any("max_agents" in e for e in errors)


def test_validate_execution_plan_rejects_non_positive_budget_fields(tmp_path: Path) -> None:
    plan = build_execution_plan(classify_task("do the thing"), _config(tmp_path))
    plan.max_tokens = 0
    plan.timeout_seconds = 0
    plan.planned_budget = Decimal(0)

    errors = validate_execution_plan(plan, KNOWN_ROLES)

    assert any("max_tokens" in e for e in errors)
    assert any("timeout_seconds" in e for e in errors)
    assert any("planned_budget" in e for e in errors)
