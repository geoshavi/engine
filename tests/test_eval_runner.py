"""Tests for eval/runner.py: cost/latency aggregation from linked
agent_execution_metrics rows, per-category accuracy, empty-benchmark
handling, and error isolation (one failing case must never abort the rest).
"""

from decimal import Decimal
from pathlib import Path

from engine.config import Config
from engine.eval import runner as runner_module
from engine.eval.dataset import EvalCase
from engine.eval.runner import _aggregate, run_benchmark, run_case, select_cases
from engine.providers.base import GenerationResult
from engine.runtime.budget import BudgetController
from engine.runtime.gateway import LLMGateway
from engine.state import db
from engine.state.models import AgentExecutionMetric, EvalCaseResult, VerificationResult


class _FakeProvider:
    name = "fake"

    def generate(self, *args: object, **kwargs: object) -> GenerationResult:
        raise AssertionError("run_case must go through the mocked run_verification, not a provider")


def _gateway() -> LLMGateway:
    return LLMGateway(_FakeProvider())


def _budget() -> BudgetController:
    return BudgetController(max_tokens=100_000, planned_budget=Decimal(10))


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


def _case(**overrides) -> EvalCase:
    defaults = {
        "eval_case_id": "x",
        "category": "correctness",
        "task_text": "t",
        "files": {"a.py": "x = 1\n"},
        "expected_verdict": "OK",
        "expected_defect_category": None,
    }
    defaults.update(overrides)
    return EvalCase(**defaults)


def _write_metric(conn, run_id: int, task_id: str, *, agent_name: str, cost: Decimal, latency_ms: int) -> None:
    db.record_agent_execution_metric(
        conn,
        AgentExecutionMetric(
            run_id=run_id,
            task_id=task_id,
            agent_name=agent_name,
            model="m",
            input_tokens=10,
            output_tokens=10,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            latency_ms=latency_ms,
            actual_spend=cost,
            status="ok",
            error=None,
        ),
    )


def test_select_cases_filters_by_category() -> None:
    security_cases = select_cases("security")
    assert len(security_cases) == 10
    assert all(c.category == "security" for c in security_cases)


def test_select_cases_returns_all_when_category_is_none() -> None:
    assert len(select_cases(None)) == 40


def test_run_case_cost_and_latency_equal_sum_of_linked_metric_rows(monkeypatch, tmp_path: Path) -> None:
    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        conn, run_id, task_id = kwargs["conn"], kwargs["run_id"], kwargs["task_id"]
        for i in range(3):
            _write_metric(conn, run_id, task_id, agent_name=f"judge:lens{i}", cost=Decimal("0.001"), latency_ms=100)
        return "OK", {"defects": [], "verdict": "OK"}, []

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    with db.connect(tmp_path / "state.db") as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        result = run_case(
            _case(), gateway=_gateway(), budget=_budget(), judge_model="m", conn=conn, run_id=run_id, eval_run_id=1
        )
        conn.commit()

    assert result.cost == Decimal("0.003")
    assert result.latency_ms == 300
    assert result.error is None
    assert result.passed is True


def test_run_case_records_error_and_partial_cost_when_verification_raises(monkeypatch, tmp_path: Path) -> None:
    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        conn, run_id, task_id = kwargs["conn"], kwargs["run_id"], kwargs["task_id"]
        _write_metric(conn, run_id, task_id, agent_name="judge:lens0", cost=Decimal("0.001"), latency_ms=100)
        _write_metric(conn, run_id, task_id, agent_name="judge:lens1", cost=Decimal("0.001"), latency_ms=100)
        raise RuntimeError("simulated failure on lens 3")

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    with db.connect(tmp_path / "state.db") as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        result = run_case(
            _case(eval_case_id="partial"),
            gateway=_gateway(),
            budget=_budget(),
            judge_model="m",
            conn=conn,
            run_id=run_id,
            eval_run_id=1,
        )
        conn.commit()

    assert result.error is not None
    assert "simulated failure" in result.error
    assert result.cost == Decimal("0.002")  # only the 2 lenses that completed
    assert result.latency_ms == 200
    assert result.passed is False


def test_partial_failure_excluded_from_accuracy_but_counted_in_total_cost(monkeypatch, tmp_path: Path) -> None:
    """Requirement 7: a partial-failure row's cost AND latency must reflect
    only the lenses that actually completed (a real sum of 2 rows, not zero
    and not a hardcoded full-3-lens total), the row must be excluded from
    every verdict-accuracy bucket (correct_verdicts/false_pass/
    false_unverified/category_accuracy) -- not just the numerator -- and its
    partial cost must still count toward total_cost.
    """

    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        conn, run_id, task_id = kwargs["conn"], kwargs["run_id"], kwargs["task_id"]
        # 2 of 3 lenses complete and write metrics; the 3rd raises before
        # writing anything -- proves a real sum of what's there, not a
        # hardcoded "first row only" or an even 3-way split.
        _write_metric(conn, run_id, task_id, agent_name="judge:lens0", cost=Decimal("0.001"), latency_ms=100)
        _write_metric(conn, run_id, task_id, agent_name="judge:lens1", cost=Decimal("0.002"), latency_ms=150)
        raise RuntimeError("boom on lens 3")

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    case = _case(eval_case_id="partial", category="correctness")
    with db.connect(tmp_path / "state.db") as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        result = run_case(
            case, gateway=_gateway(), budget=_budget(), judge_model="m", conn=conn, run_id=run_id, eval_run_id=1
        )
        conn.commit()

    # Cost/latency reflect only the 2 completed lenses: 0.001+0.002,
    # 100+150 -- not zero, not the 3-lens total.
    assert result.cost == Decimal("0.003")
    assert result.latency_ms == 250
    assert result.error is not None and "boom on lens 3" in result.error

    aggregates = _aggregate([case], [result])
    assert aggregates["total_cases"] == 1
    assert aggregates["correct_verdicts"] == 0
    assert aggregates["false_pass"] == 0
    assert aggregates["false_unverified"] == 0
    assert aggregates["category_accuracy"] == {}  # excluded entirely -- no non-error cases
    assert aggregates["total_cost"] == Decimal("0.003")  # but the partial cost still counts
    assert aggregates["average_cost"] == Decimal("0.003")  # only 1 case in this aggregate


def test_aggregate_computes_per_category_accuracy() -> None:
    cases = [
        _case(eval_case_id="c1", category="correctness", expected_verdict="OK"),
        _case(eval_case_id="c2", category="correctness", expected_verdict="OK"),
        _case(eval_case_id="s1", category="security", expected_verdict="UNVERIFIED"),
    ]
    results = [
        EvalCaseResult(
            eval_run_id=1, eval_case_id="c1", task_id="t1", expected_verdict="OK", actual_verdict="OK",
            expected_defect_category=None, detected_defect_categories=[], latency_ms=10,
            cost=Decimal("0.001"), passed=True,
        ),
        EvalCaseResult(
            eval_run_id=1, eval_case_id="c2", task_id="t2", expected_verdict="OK", actual_verdict="UNVERIFIED",
            expected_defect_category=None, detected_defect_categories=["CORRECTNESS"], latency_ms=10,
            cost=Decimal("0.001"), passed=False,
        ),
        EvalCaseResult(
            eval_run_id=1, eval_case_id="s1", task_id="t3", expected_verdict="UNVERIFIED", actual_verdict="UNVERIFIED",
            expected_defect_category="SECURITY", detected_defect_categories=["SECURITY"], latency_ms=10,
            cost=Decimal("0.001"), passed=True,
        ),
    ]

    aggregates = _aggregate(cases, results)

    assert aggregates["category_accuracy"] == {"correctness": 0.5, "security": 1.0}
    assert aggregates["correct_verdicts"] == 2
    assert aggregates["false_unverified"] == 1  # c2: expected OK, got UNVERIFIED
    assert aggregates["false_pass"] == 0


def test_aggregate_handles_empty_results_without_crashing() -> None:
    aggregates = _aggregate([], [])

    assert aggregates["total_cases"] == 0
    assert aggregates["correct_verdicts"] == 0
    assert aggregates["false_pass"] == 0
    assert aggregates["false_unverified"] == 0
    assert aggregates["category_accuracy"] == {}
    assert aggregates["average_cost"] == Decimal(0)
    assert aggregates["average_latency"] == 0
    assert aggregates["total_cost"] == Decimal(0)


def test_run_benchmark_continues_after_one_case_errors(monkeypatch, tmp_path: Path) -> None:
    call_count = {"n": 0}

    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("boom on case 2")
        return "OK", {"defects": [], "verdict": "OK"}, []

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    eval_run, results = run_benchmark(
        config=_config(tmp_path), provider_name="anthropic", judge_model="m", category="security"
    )

    assert len(results) == 10  # every case in the category was attempted
    assert call_count["n"] == 10  # none skipped after the failure
    errored = [r for r in results if r.error is not None]
    assert len(errored) == 1
    assert "boom on case 2" in errored[0].error
    assert eval_run.total_cases == 10


def test_run_benchmark_persists_and_reads_back_via_get_eval_run(monkeypatch, tmp_path: Path) -> None:
    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        return "OK", {"defects": [], "verdict": "OK"}, []

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    config = _config(tmp_path)
    eval_run, results = run_benchmark(config=config, provider_name="anthropic", judge_model="m", category="quality")

    with db.connect(config.db_path) as conn:
        reloaded = db.get_eval_run(conn, eval_run.id)
        reloaded_results = db.get_eval_case_results(conn, eval_run.id)

    assert reloaded is not None
    assert reloaded.total_cases == 10
    assert len(reloaded_results) == 10
    assert {r.eval_case_id for r in reloaded_results} == {r.eval_case_id for r in results}


# ---------------------------------------------------------------- Phase 2.1


def test_run_case_records_a_lens_result_row_for_a_lens_that_found_nothing(
    monkeypatch, tmp_path: Path
) -> None:
    """A lens that ran and found zero defects must still produce a row --
    empty is data, not absence of data. Only the security lens here reports
    a defect; correctness and code-quality must still show call_status='ok'
    with defect_count=0, not be silently missing.
    """

    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        conn, run_id, task_id = kwargs["conn"], kwargs["run_id"], kwargs["task_id"]
        for lens in ("correctness", "security", "code-quality"):
            _write_metric(conn, run_id, task_id, agent_name=f"judge:{lens}", cost=Decimal("0.001"), latency_ms=100)
        merged = {
            "defects": [
                {
                    "id": "S1",
                    "category": "SECURITY",
                    "severity": "LOW",
                    "location": "x",
                    "fix": "y",
                    "lens": "security",
                }
            ],
            "verdict": "OK",
        }
        return "OK", merged, []

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    with db.connect(tmp_path / "state.db") as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        result = run_case(
            _case(), gateway=_gateway(), budget=_budget(), judge_model="m", conn=conn, run_id=run_id, eval_run_id=1
        )

    assert result.defects == [
        {"id": "S1", "category": "SECURITY", "severity": "LOW", "location": "x", "fix": "y", "lens": "security"}
    ]
    by_lens = {lr.lens: lr for lr in result.lens_results}
    assert set(by_lens) == {"correctness", "security", "code-quality"}
    assert by_lens["security"].call_status == "ok"
    assert by_lens["security"].defect_count == 1
    assert by_lens["security"].schema_valid is True
    assert by_lens["correctness"].call_status == "ok"
    assert by_lens["correctness"].defect_count == 0  # ran, found nothing -- not missing
    assert by_lens["code-quality"].defect_count == 0


def test_run_case_error_preserves_completed_lens_status_but_not_unknown_defect_content(
    monkeypatch, tmp_path: Path
) -> None:
    """Mirrors the existing partial-cost behavior (Requirement 7) at the
    defect layer: two lenses complete before a third raises. Their
    call_status must still read 'ok' (we know they succeeded via
    agent_execution_metrics), but defect_count/schema_valid must be None,
    not a fabricated 0 -- the parsed critic content itself was discarded
    when the exception unwound past run_judge_gates (see the limitation
    documented there). The un-started lens reads 'not_run'.
    """

    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        conn, run_id, task_id = kwargs["conn"], kwargs["run_id"], kwargs["task_id"]
        _write_metric(conn, run_id, task_id, agent_name="judge:correctness", cost=Decimal("0.001"), latency_ms=100)
        _write_metric(conn, run_id, task_id, agent_name="judge:security", cost=Decimal("0.001"), latency_ms=100)
        raise RuntimeError("boom on code-quality lens")

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    with db.connect(tmp_path / "state.db") as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        result = run_case(
            _case(eval_case_id="partial"),
            gateway=_gateway(),
            budget=_budget(),
            judge_model="m",
            conn=conn,
            run_id=run_id,
            eval_run_id=1,
        )

    assert result.error is not None
    assert result.defects == []  # merge() never ran -- nothing recoverable here
    by_lens = {lr.lens: lr for lr in result.lens_results}
    assert by_lens["correctness"].call_status == "ok"
    assert by_lens["correctness"].defect_count is None  # unknown, not 0 -- content was lost, not absent
    assert by_lens["correctness"].schema_valid is None
    assert by_lens["security"].call_status == "ok"
    assert by_lens["security"].defect_count is None
    assert by_lens["code-quality"].call_status == "not_run"
    assert by_lens["code-quality"].defect_count is None


def test_run_case_records_lens_call_error_with_message(monkeypatch, tmp_path: Path) -> None:
    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        conn, run_id, task_id = kwargs["conn"], kwargs["run_id"], kwargs["task_id"]
        db.record_agent_execution_metric(
            conn,
            AgentExecutionMetric(
                run_id=run_id,
                task_id=task_id,
                agent_name="judge:security",
                model="m",
                input_tokens=10,
                output_tokens=0,
                cache_read_tokens=0,
                cache_creation_tokens=0,
                latency_ms=50,
                actual_spend=None,
                status="error",
                error="BadRequestError: credit balance too low",
            ),
        )
        raise RuntimeError("propagated after the metric was recorded")

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    with db.connect(tmp_path / "state.db") as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        result = run_case(
            _case(eval_case_id="errored"),
            gateway=_gateway(),
            budget=_budget(),
            judge_model="m",
            conn=conn,
            run_id=run_id,
            eval_run_id=1,
        )

    by_lens = {lr.lens: lr for lr in result.lens_results}
    assert by_lens["security"].call_status == "error"
    assert by_lens["security"].error is not None and "credit balance too low" in by_lens["security"].error
    assert by_lens["correctness"].call_status == "not_run"


def test_run_case_captures_automated_gate_results(monkeypatch, tmp_path: Path) -> None:
    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        return (
            "UNVERIFIED",
            {"defects": [], "verdict": "OK"},
            [
                VerificationResult("ruff", False, "E501 line too long"),
                VerificationResult("mypy", True, "ok"),
                VerificationResult("pytest", True, "no test files present"),
            ],
        )

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    with db.connect(tmp_path / "state.db") as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        result = run_case(
            _case(), gateway=_gateway(), budget=_budget(), judge_model="m", conn=conn, run_id=run_id, eval_run_id=1
        )

    assert [(r.gate_name, r.passed) for r in result.automated_gate_results] == [
        ("ruff", False),
        ("mypy", True),
        ("pytest", True),
    ]


def test_run_case_automated_gate_results_empty_when_case_errors_before_verification(
    monkeypatch, tmp_path: Path
) -> None:
    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        raise RuntimeError("boom before automated gates ever ran")

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    with db.connect(tmp_path / "state.db") as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        result = run_case(
            _case(eval_case_id="early-crash"),
            gateway=_gateway(),
            budget=_budget(),
            judge_model="m",
            conn=conn,
            run_id=run_id,
            eval_run_id=1,
        )

    assert result.automated_gate_results == []


def test_eval_case_defects_and_lens_results_persist_with_correct_fk(monkeypatch, tmp_path: Path) -> None:
    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        conn, run_id, task_id = kwargs["conn"], kwargs["run_id"], kwargs["task_id"]
        for lens in ("correctness", "security", "code-quality"):
            _write_metric(conn, run_id, task_id, agent_name=f"judge:{lens}", cost=Decimal("0.001"), latency_ms=50)
        merged = {
            "defects": [
                {
                    "id": "C1",
                    "category": "CORRECTNESS",
                    "severity": "HIGH",
                    "location": "a:1",
                    "fix": "z",
                    "lens": "correctness",
                }
            ],
            "verdict": "FAIL",
        }
        return "UNVERIFIED", merged, [VerificationResult("ruff", True, "ok")]

    monkeypatch.setattr(runner_module, "run_verification", fake_run_verification)

    config = _config(tmp_path)
    with db.connect(config.db_path) as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        eval_run_id = db.create_eval_run(conn, "sha", "bench", "v1", "v1")
        conn.commit()

        result = run_case(
            _case(expected_verdict="UNVERIFIED"),
            gateway=_gateway(),
            budget=_budget(),
            judge_model="m",
            conn=conn,
            run_id=run_id,
            eval_run_id=eval_run_id,
        )
        eval_case_result_id = db.record_eval_case_result(conn, result)
        db.record_eval_case_defects(conn, eval_case_result_id, result.defects)
        db.record_eval_case_lens_results(conn, eval_case_result_id, result.lens_results)
        db.record_eval_case_automated_gates(conn, eval_case_result_id, result.automated_gate_results)
        conn.commit()

        # A second, unrelated case-result row to prove lookups are FK-scoped,
        # not "everything in the table so far".
        other_id = db.record_eval_case_result(
            conn,
            EvalCaseResult(
                eval_run_id=eval_run_id,
                eval_case_id="other",
                task_id="t-other",
                expected_verdict="OK",
                actual_verdict="OK",
                expected_defect_category=None,
                detected_defect_categories=[],
                latency_ms=0,
                cost=Decimal(0),
                passed=True,
            ),
        )
        db.record_eval_case_defects(conn, other_id, [])
        conn.commit()

        stored_defects = db.get_eval_case_defects(conn, eval_case_result_id)
        stored_lens_results = db.get_eval_case_lens_results(conn, eval_case_result_id)
        stored_gates = db.get_eval_case_automated_gates(conn, eval_case_result_id)
        other_defects = db.get_eval_case_defects(conn, other_id)

    assert isinstance(eval_case_result_id, int)
    assert len(stored_defects) == 1
    assert stored_defects[0]["lens"] == "correctness"
    assert stored_defects[0]["category"] == "CORRECTNESS"
    assert stored_defects[0]["severity"] == "HIGH"
    assert {lr.lens for lr in stored_lens_results} == {"correctness", "security", "code-quality"}
    assert [g.gate_name for g in stored_gates] == ["ruff"]
    assert other_defects == []  # FK-scoped: the other case's rows don't leak in


def test_record_eval_case_defects_falls_back_to_automated_for_script_defects(tmp_path: Path) -> None:
    """automated_defects() (ruff/mypy/pytest failures) never tags a "lens"
    key -- only judge.py's run_judge_gates does that. The writer must not
    crash or silently drop these rows; it labels them "automated".
    """
    with db.connect(tmp_path / "state.db") as conn:
        run_id = db.create_run(conn, "eval", "anthropic", "m")
        eval_run_id = db.create_eval_run(conn, "sha", "bench", "v1", "v1")
        eval_case_result_id = db.record_eval_case_result(
            conn,
            EvalCaseResult(
                eval_run_id=eval_run_id,
                eval_case_id="x",
                task_id=f"eval-{run_id}-x",
                expected_verdict="UNVERIFIED",
                actual_verdict="UNVERIFIED",
                expected_defect_category="CORRECTNESS",
                detected_defect_categories=["CORRECTNESS"],
                latency_ms=0,
                cost=Decimal(0),
                passed=True,
            ),
        )
        db.record_eval_case_defects(
            conn,
            eval_case_result_id,
            [{"id": "AUTO0-mypy", "category": "CORRECTNESS", "severity": "HIGH", "location": "mypy", "fix": "f"}],
        )
        conn.commit()

        stored = db.get_eval_case_defects(conn, eval_case_result_id)

    assert stored[0]["lens"] == "automated"
