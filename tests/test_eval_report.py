"""Tests for eval/report.py: the exact --dry-run layout, dataset_version/
benchmark_version mismatch detection, and --compare diffing.
"""

from decimal import Decimal
from typing import Any

from engine.eval.dataset import BENCHMARK_VERSION, CASES, DATASET_VERSION, EvalCase
from engine.eval.report import detect_version_mismatch, format_comparison, format_dry_run_plan
from engine.eval.runner import BENCHMARK_PLANNED_BUDGET
from engine.state.models import EvalCaseResult, EvalRun

JUDGE_MODEL = "claude-haiku-4-5-20251001"


def _eval_run(**overrides) -> EvalRun:
    defaults = {
        "id": 1,
        "created_at": "now",
        "git_commit_sha": "abc123",
        "benchmark_name": "engine-review-benchmark",
        "benchmark_version": BENCHMARK_VERSION,
        "dataset_version": DATASET_VERSION,
        "total_cases": 40,
        "correct_verdicts": 35,
        "false_pass": 2,
        "false_unverified": 3,
        "category_accuracy": {"correctness": 0.9},
        "average_cost": Decimal("0.01"),
        "average_latency": 1000,
        "total_cost": Decimal("0.4"),
    }
    defaults.update(overrides)
    return EvalRun(**defaults)


def _result(**overrides: Any) -> EvalCaseResult:
    # Explicitly dict[str, Any] (not the inferred dict[str, object] every
    # other **overrides helper in this test suite uses) -- EvalCaseResult
    # is the one dataclass in this file that Phase 2.1 added fields to, and
    # object-typed unpacking makes mypy flag EVERY constructor parameter
    # (including ones this dict never sets) each time the dataclass grows.
    defaults: dict[str, Any] = {
        "eval_run_id": 1,
        "eval_case_id": "c1",
        "task_id": "t1",
        "expected_verdict": "OK",
        "actual_verdict": "OK",
        "expected_defect_category": None,
        "detected_defect_categories": [],
        "latency_ms": 100,
        "cost": Decimal("0.01"),
        "passed": True,
    }
    defaults.update(overrides)
    return EvalCaseResult(**defaults)


def test_format_dry_run_plan_matches_the_exact_requested_layout() -> None:
    text, errors = format_dry_run_plan(CASES, JUDGE_MODEL)
    lines = text.splitlines()

    assert lines[0] == "Benchmark plan:"
    assert lines[1] == "  Cases: 40"
    assert lines[2] == "  Security: 10"
    assert lines[3] == "  Correctness: 10"
    assert lines[4] == "  Quality: 10"
    assert lines[5] == "  Edge: 10"
    assert lines[6] == f"  dataset_version: {DATASET_VERSION}"
    assert lines[7] == f"  benchmark_version: {BENCHMARK_VERSION}"
    assert lines[8].startswith("  Estimated max cost: $")
    assert lines[9] == f"  Benchmark budget ceiling: ${BENCHMARK_PLANNED_BUDGET}"
    assert errors == []


def test_format_dry_run_plan_warns_when_estimate_exceeds_ceiling() -> None:
    huge_cases = CASES * 1000  # guaranteed worst-case cost far above $3.00
    text, _errors = format_dry_run_plan(huge_cases, JUDGE_MODEL)
    assert "WARNING: estimated max cost" in text
    assert "exceeds" in text


def test_format_dry_run_plan_surfaces_dataset_validation_errors() -> None:
    bad_case = EvalCase(
        eval_case_id="bad",
        category="correctness",
        task_text="t",
        files={"a.py": "x = 1\n"},
        expected_verdict="NOT_A_VERDICT",
        expected_defect_category=None,
    )
    text, errors = format_dry_run_plan([bad_case], JUDGE_MODEL)
    assert errors != []
    assert "WARNING: dataset validation failed" in text


def test_detect_version_mismatch_flags_both_fields_independently() -> None:
    current = _eval_run(dataset_version="v2", benchmark_version="v2")
    previous = _eval_run(dataset_version="v1", benchmark_version="v1")

    warnings = detect_version_mismatch(current, previous)

    assert any("dataset_version" in w for w in warnings)
    assert any("benchmark_version" in w for w in warnings)
    assert len(warnings) == 2


def test_detect_version_mismatch_flags_only_the_differing_field() -> None:
    current = _eval_run(dataset_version="v2", benchmark_version="v1")
    previous = _eval_run(dataset_version="v1", benchmark_version="v1")

    warnings = detect_version_mismatch(current, previous)

    assert len(warnings) == 1
    assert "dataset_version" in warnings[0]


def test_detect_version_mismatch_empty_when_versions_match() -> None:
    current = _eval_run(id=2)
    previous = _eval_run(id=1)
    assert detect_version_mismatch(current, previous) == []


def test_format_comparison_warns_prominently_on_mismatched_versions() -> None:
    current = _eval_run(id=2, dataset_version="v2")
    previous = _eval_run(id=1, dataset_version="v1")

    text = format_comparison(current, [], previous, [])

    assert "WARNING: dataset_version differs" in text


def test_format_comparison_does_not_silently_skip_the_warning_when_matched() -> None:
    current = _eval_run(id=2)
    previous = _eval_run(id=1)
    text = format_comparison(current, [], previous, [])
    assert "WARNING" not in text


def test_format_comparison_reports_verdict_changes() -> None:
    current_results = [
        _result(
            eval_run_id=2,
            eval_case_id="c1",
            task_id="t1",
            expected_verdict="UNVERIFIED",
            actual_verdict="OK",
            expected_defect_category="SECURITY",
            passed=False,
        )
    ]
    previous_results = [
        _result(
            eval_run_id=1,
            eval_case_id="c1",
            task_id="t0",
            expected_verdict="UNVERIFIED",
            actual_verdict="UNVERIFIED",
            expected_defect_category="SECURITY",
            detected_defect_categories=["SECURITY"],
            passed=True,
        )
    ]

    text = format_comparison(_eval_run(id=2), current_results, _eval_run(id=1), previous_results)

    assert "c1: UNVERIFIED -> OK" in text


def test_format_comparison_reports_defect_category_changes() -> None:
    current_results = [_result(detected_defect_categories=["SECURITY", "CODE-QUALITY"])]
    previous_results = [_result(detected_defect_categories=["SECURITY"])]

    text = format_comparison(_eval_run(id=2), current_results, _eval_run(id=1), previous_results)

    assert "Defect category changes: none" not in text
    assert "c1:" in text


def test_format_comparison_reports_total_cost_and_latency_differences() -> None:
    current = _eval_run(id=2, total_cost=Decimal("0.50"))
    previous = _eval_run(id=1, total_cost=Decimal("0.40"))
    current_results = [_result(latency_ms=500, cost=Decimal("0.5"))]
    previous_results = [_result(latency_ms=300, cost=Decimal("0.4"))]

    text = format_comparison(current, current_results, previous, previous_results)

    assert "Total cost difference: +0.10" in text
    assert "Total latency difference: +200ms" in text


def test_format_comparison_reports_per_case_cost_and_latency_deltas() -> None:
    current_results = [_result(eval_case_id="c1", latency_ms=500, cost=Decimal("0.5"))]
    previous_results = [_result(eval_case_id="c1", latency_ms=300, cost=Decimal("0.4"))]

    text = format_comparison(_eval_run(id=2), current_results, _eval_run(id=1), previous_results)

    assert "c1: +0.1" in text  # cost delta by case
    assert "c1: +200ms" in text  # latency delta by case


def test_format_comparison_reports_no_changes_when_nothing_differs() -> None:
    results = [_result()]
    text = format_comparison(_eval_run(id=2), results, _eval_run(id=1), results)

    assert "Verdict changes: none" in text
    assert "Defect category changes: none" in text
    assert "Cost delta by case: none" in text
    assert "Latency delta by case: none" in text
