"""Tests for runtime/gateway.py: the sole entry point for LLM calls.
Budget is checked before every call regardless of DB state; metrics are
written after every call (success or failure) but only when a live
connection is given -- no DB handle means no write, not a crash.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from engine.config import Config
from engine.providers.base import GenerationResult, Message
from engine.runtime.budget import BudgetController, BudgetExceededError
from engine.runtime.gateway import LLMGateway
from engine.state import db

MODEL = "claude-sonnet-5"


class _FakeProvider:
    name = "fake"

    def __init__(self, text: str = "ok", raises: Exception | None = None) -> None:
        self._text = text
        self._raises = raises
        self.calls = 0

    def generate(
        self,
        messages: list[Message],
        model: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
    ) -> GenerationResult:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return GenerationResult(
            text=self._text,
            model=model,
            provider=self.name,
            input_tokens=5,
            output_tokens=7,
            cache_read_tokens=1,
            cache_creation_tokens=2,
        )


def _budget() -> BudgetController:
    return BudgetController(max_tokens=100_000, planned_budget=Decimal("1.00"))


def test_generate_without_conn_still_calls_the_provider_but_skips_metrics() -> None:
    provider = _FakeProvider()
    gateway = LLMGateway(provider)

    result = gateway.generate(
        budget=_budget(),
        messages=[Message(role="user", content="hi")],
        model=MODEL,
        agent_name="TestAgent",
    )

    assert provider.calls == 1
    assert result.text == "ok"


def test_generate_requires_run_id_and_task_id_when_conn_is_given(tmp_path: Path) -> None:
    gateway = LLMGateway(_FakeProvider())
    with db.connect(tmp_path / "state.db") as conn, pytest.raises(ValueError, match="run_id/task_id"):
        gateway.generate(
            budget=_budget(),
            messages=[Message(role="user", content="hi")],
            model=MODEL,
            agent_name="TestAgent",
            conn=conn,
        )


def test_generate_records_a_metric_row_on_success(tmp_path: Path) -> None:
    gateway = LLMGateway(_FakeProvider())
    db_path = tmp_path / "state.db"

    with db.connect(db_path) as conn:
        run_id = db.create_run(conn, "task", "anthropic", MODEL)
        gateway.generate(
            budget=_budget(),
            messages=[Message(role="user", content="hi")],
            model=MODEL,
            agent_name="CodingAgent",
            conn=conn,
            run_id=run_id,
            task_id="task-1",
        )
        conn.commit()

    with db.connect(db_path) as conn:
        metrics = db.get_agent_execution_metrics(conn, run_id)

    assert len(metrics) == 1
    m = metrics[0]
    assert m.status == "ok"
    assert m.agent_name == "CodingAgent"
    assert m.task_id == "task-1"
    assert m.input_tokens == 5
    assert m.output_tokens == 7
    assert m.cache_read_tokens == 1
    assert m.cache_creation_tokens == 2
    assert m.actual_spend is not None and m.actual_spend > 0
    assert m.error is None


def test_generate_records_an_error_metric_when_the_provider_raises(tmp_path: Path) -> None:
    gateway = LLMGateway(_FakeProvider(raises=RuntimeError("boom")))
    db_path = tmp_path / "state.db"

    with db.connect(db_path) as conn:
        run_id = db.create_run(conn, "task", "anthropic", MODEL)
        with pytest.raises(RuntimeError):
            gateway.generate(
                budget=_budget(),
                messages=[Message(role="user", content="hi")],
                model=MODEL,
                agent_name="CodingAgent",
                conn=conn,
                run_id=run_id,
                task_id="task-1",
            )
        conn.commit()

    with db.connect(db_path) as conn:
        metrics = db.get_agent_execution_metrics(conn, run_id)

    assert len(metrics) == 1
    assert metrics[0].status == "error"
    assert metrics[0].actual_spend is None
    assert metrics[0].error is not None and "boom" in metrics[0].error


def test_generate_checks_budget_before_calling_the_provider() -> None:
    provider = _FakeProvider()
    gateway = LLMGateway(provider)
    tiny_budget = BudgetController(max_tokens=10, planned_budget=Decimal("1.00"))

    with pytest.raises(BudgetExceededError):
        gateway.generate(
            budget=tiny_budget,
            messages=[Message(role="user", content="hi")],
            model=MODEL,
            agent_name="CodingAgent",
            max_tokens=100,
        )

    assert provider.calls == 0  # pre-flight check blocked it before any call


def test_from_config_wraps_the_provider_built_by_the_registry(monkeypatch) -> None:
    sentinel_provider = _FakeProvider()
    monkeypatch.setattr("engine.runtime.gateway.build_provider", lambda name, config: sentinel_provider)

    config = Config(
        anthropic_api_key="key",
        openai_api_key=None,
        google_api_key=None,
        max_retries=3,
        db_path=Path("unused"),
        max_tokens=1,
        timeout_seconds=1.0,
        max_agents=1,
        planned_budget=Decimal(1),
        review_max_tokens=1,
        review_planned_budget=Decimal(1),
    )
    gateway = LLMGateway.from_config("anthropic", config)

    gateway.generate(
        budget=_budget(), messages=[Message(role="user", content="hi")], model=MODEL, agent_name="x"
    )
    assert sentinel_provider.calls == 1
