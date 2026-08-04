"""Tests for eval/dataset.py: dataset shape and validate_dataset()."""

from engine.eval.dataset import (
    CASES,
    CATEGORIES,
    JUDGE_DIMENSIONS,
    TASKS,
    EvalCase,
    validate_dataset,
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


def test_dataset_has_forty_cases_from_twenty_tasks() -> None:
    assert len(TASKS) == 20
    assert len(CASES) == 40


def test_dataset_has_ten_cases_per_category() -> None:
    counts: dict[str, int] = {}
    for case in CASES:
        counts[case.category] = counts.get(case.category, 0) + 1
    assert counts == {"correctness": 10, "security": 10, "quality": 10, "edge_case": 10}


def test_dataset_case_ids_are_unique() -> None:
    ids = [c.eval_case_id for c in CASES]
    assert len(set(ids)) == len(ids)


def test_dataset_is_evenly_split_broken_and_clean() -> None:
    verdicts = [c.expected_verdict for c in CASES]
    assert verdicts.count("UNVERIFIED") == 20
    assert verdicts.count("OK") == 20


def test_broken_cases_have_a_judge_dimension_defect_category() -> None:
    for case in CASES:
        if case.expected_verdict == "UNVERIFIED":
            assert case.expected_defect_category in JUDGE_DIMENSIONS, case.eval_case_id


def test_clean_cases_have_no_expected_defect_category() -> None:
    for case in CASES:
        if case.expected_verdict == "OK":
            assert case.expected_defect_category is None, case.eval_case_id


def test_categories_constant_matches_the_four_benchmark_categories() -> None:
    assert set(CATEGORIES) == {"correctness", "security", "quality", "edge_case"}


def test_validate_dataset_accepts_the_real_dataset() -> None:
    assert validate_dataset(CASES) == []


def test_validate_dataset_rejects_unknown_expected_verdict() -> None:
    errors = validate_dataset([_case(expected_verdict="MAYBE")])
    assert any("expected_verdict" in e for e in errors)


def test_validate_dataset_accepts_only_ok_and_unverified() -> None:
    assert validate_dataset([_case(expected_verdict="OK")]) == []
    assert validate_dataset([_case(expected_verdict="UNVERIFIED", expected_defect_category="CORRECTNESS")]) == []
    for bad in ("ok", "unverified", "PASS", "FAIL", ""):
        errors = validate_dataset([_case(expected_verdict=bad)])
        assert any("expected_verdict" in e for e in errors), bad


def test_validate_dataset_rejects_unknown_category() -> None:
    errors = validate_dataset([_case(category="not-a-category")])
    assert any("category" in e for e in errors)


def test_validate_dataset_rejects_invalid_defect_category() -> None:
    errors = validate_dataset(
        [_case(expected_verdict="UNVERIFIED", expected_defect_category="EDGE_CASE")]
    )
    assert any("expected_defect_category" in e for e in errors)


def test_validate_dataset_accepts_the_three_judge_dimensions() -> None:
    for dim in JUDGE_DIMENSIONS:
        errors = validate_dataset([_case(expected_verdict="UNVERIFIED", expected_defect_category=dim)])
        assert errors == [], dim


def test_validate_dataset_rejects_duplicate_case_ids() -> None:
    errors = validate_dataset([_case(eval_case_id="dup"), _case(eval_case_id="dup", category="security")])
    assert any("duplicate" in e for e in errors)


def test_validate_dataset_rejects_empty_files() -> None:
    errors = validate_dataset([_case(files={})])
    assert any("files" in e for e in errors)


def test_validate_dataset_rejects_empty_task_text() -> None:
    errors = validate_dataset([_case(task_text="   ")])
    assert any("task_text" in e for e in errors)


def test_validate_dataset_empty_list_is_valid() -> None:
    assert validate_dataset([]) == []
