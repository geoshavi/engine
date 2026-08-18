"""Witness observability (Phase 8D.2C).

The witness layer can demote a blocking defect. Without a record of which
defects carried a witness, what verification said about each, and which case
verdicts moved as a result, a benchmark run cannot tell a working mechanism
apart from a model that never used it -- exactly the gap that made Phase 8D.1
unreadable.

This log is passive. It is derived from data the run already produced, written
once after every database commit, and is incapable of changing a verdict.
"""

import json
from decimal import Decimal
from pathlib import Path

from engine.config import Config
from engine.eval import runner as runner_module
from engine.eval import witness_log
from engine.eval.runner import run_benchmark
from engine.state.models import EvalCaseResult
from engine.verification import witness


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


def _result(defects: list[dict], *, actual: str = "UNVERIFIED", expected: str = "OK") -> EvalCaseResult:
    return EvalCaseResult(
        eval_run_id=1,
        eval_case_id="some-case",
        task_id="eval-1-some-case",
        expected_verdict=expected,
        actual_verdict=actual,
        expected_defect_category=None,
        detected_defect_categories=[],
        latency_ms=0,
        cost=Decimal(0),
        passed=actual == expected,
        defects=defects,
    )


def _defect(severity: str, **extra: object) -> dict:
    d = {
        "lens": "correctness",
        "id": "C1",
        "category": "CORRECTNESS",
        "severity": severity,
        "location": "solution.py:2",
        "fix": "...",
    }
    d.update(extra)
    return d


def _one(defect: dict) -> dict:
    return witness_log.case_record(_result([defect]))["defects"][0]


# ------------------------------------------- 1-5. every status is recorded


def test_1_no_witness_is_recorded() -> None:
    row = _one(_defect("HIGH"))
    assert row["witness_emitted"] is False
    assert row["witness_executed"] is False
    assert row["witness_result"] == witness.NO_WITNESS
    assert row["blocking"] is True


def test_2_verified_is_recorded() -> None:
    row = _one(_defect("HIGH", witness={"call": "f"}, witness_result=witness.VERIFIED))
    assert row["witness_emitted"] is True
    assert row["witness_executed"] is True
    assert row["witness_result"] == witness.VERIFIED
    assert row["blocking"] is True


def test_3_refuted_is_recorded() -> None:
    row = _one(
        _defect(
            "MEDIUM",
            witness={"call": "f"},
            witness_result=witness.REFUTED,
            original_severity="HIGH",
        )
    )
    assert row["witness_result"] == witness.REFUTED
    assert row["blocking"] is False


def test_4_unsupported_is_recorded() -> None:
    row = _one(_defect("CRITICAL", witness="prose", witness_result=witness.UNSUPPORTED))
    assert row["witness_result"] == witness.UNSUPPORTED
    assert row["blocking"] is True


def test_5_inconclusive_is_recorded() -> None:
    row = _one(_defect("HIGH", witness={"call": "f"}, witness_result=witness.INCONCLUSIVE))
    assert row["witness_result"] == witness.INCONCLUSIVE
    assert row["blocking"] is True


def test_a_witness_on_a_non_blocking_defect_is_never_reported_as_verified() -> None:
    """The engine only executes witnesses on blocking defects, so a witness on
    a MEDIUM finding is emitted but never run. That must read as "not
    executed", not as a verification that happened to succeed.
    """
    row = _one(_defect("MEDIUM", witness={"call": "f"}))
    assert row["witness_emitted"] is True
    assert row["witness_executed"] is False
    assert row["witness_result"] == witness_log.NOT_EXECUTED


# ------------------------------------- 6-8. severity, authority, invariant


def test_6_original_severity_is_preserved_in_diagnostics() -> None:
    row = _one(
        _defect(
            "MEDIUM",
            witness={"call": "f"},
            witness_result=witness.REFUTED,
            original_severity="CRITICAL",
        )
    )
    assert row["original_severity"] == "CRITICAL"
    assert row["effective_severity"] == "MEDIUM"


def test_7_effective_blocking_status_is_recorded() -> None:
    assert _one(_defect("CRITICAL"))["blocking"] is True
    assert _one(_defect("HIGH"))["blocking"] is True
    assert _one(_defect("MEDIUM"))["blocking"] is False
    assert _one(_defect("LOW"))["blocking"] is False


def test_8_only_refuted_ever_shows_authority_removed() -> None:
    """The record must make the invariant auditable after the fact: a severity
    that moved, in any run, can only ever have moved via REFUTED.
    """
    for status in (witness.VERIFIED, witness.UNSUPPORTED, witness.INCONCLUSIVE):
        row = _one(_defect("HIGH", witness={"call": "f"}, witness_result=status))
        assert row["original_severity"] == row["effective_severity"] == "HIGH"
        assert row["blocking"] is True
        assert row["authority_removed"] is False

    refuted = _one(
        _defect(
            "MEDIUM", witness={"call": "f"}, witness_result=witness.REFUTED, original_severity="HIGH"
        )
    )
    assert refuted["authority_removed"] is True


# --------------------------------------------------- 9. multiple defects


def test_9_multiple_defects_retain_separate_statuses() -> None:
    record = witness_log.case_record(
        _result(
            [
                _defect("MEDIUM", id="C1", witness={"call": "f"},
                        witness_result=witness.REFUTED, original_severity="HIGH"),
                _defect("HIGH", id="C2", witness={"call": "g"}, witness_result=witness.VERIFIED),
                _defect("CRITICAL", id="C3"),
            ]
        )
    )
    by_id = {d["id"]: d for d in record["defects"]}

    assert by_id["C1"]["witness_result"] == witness.REFUTED
    assert by_id["C2"]["witness_result"] == witness.VERIFIED
    assert by_id["C3"]["witness_result"] == witness.NO_WITNESS
    assert record["demoted"] == 1
    assert record["blocking_defects"] == 2
    assert record["witness_changed_verdict"] is False  # C2/C3 still block


def test_10_a_malformed_witness_can_never_appear_as_a_successful_verification() -> None:
    for malformed in ("prose", [], {"call": "os.system"}, 7):
        row = _one(_defect("HIGH", witness=malformed, witness_result=witness.UNSUPPORTED))
        assert row["witness_result"] != witness.VERIFIED
        assert row["blocking"] is True
        assert row["authority_removed"] is False


# ------------------------------------------- verdict-attribution reporting


def test_witness_changed_verdict_is_true_only_when_a_demotion_opened_the_gate() -> None:
    demoted_alone = witness_log.case_record(
        _result(
            [_defect("MEDIUM", witness={"call": "f"}, witness_result=witness.REFUTED,
                     original_severity="HIGH")],
            actual="OK",
            expected="OK",
        )
    )
    assert demoted_alone["witness_changed_verdict"] is True
    assert demoted_alone["demoted"] == 1

    never_blocked = witness_log.case_record(_result([_defect("LOW")], actual="OK", expected="OK"))
    assert never_blocked["witness_changed_verdict"] is False


# ----------------------------------------------- run-level integration


def _fake_verification(defects: list[dict], status: str):
    def _run(workspace, gateway, budget, judge_model, task_text, **kwargs):
        return status, {"defects": [dict(d) for d in defects], "verdict": "FAIL"}, []

    return _run


def test_the_log_is_written_beside_the_database_one_line_per_case(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        runner_module,
        "run_verification",
        _fake_verification(
            [_defect("MEDIUM", witness={"call": "f"}, witness_result=witness.REFUTED,
                     original_severity="HIGH")],
            "OK",
        ),
    )
    config = _config(tmp_path)

    eval_run, results = run_benchmark(
        config=config, provider_name="anthropic", judge_model="m", category="quality"
    )

    log_path = tmp_path / f"witness-{eval_run.id}.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == len(results) == 10
    records = [json.loads(line) for line in lines]
    assert {r["eval_case_id"] for r in records} == {r.eval_case_id for r in results}
    assert all(r["defects"][0]["witness_result"] == witness.REFUTED for r in records)
    assert all(r["witness_changed_verdict"] for r in records)


def test_11_a_failing_log_write_cannot_change_any_verdict(monkeypatch, tmp_path: Path) -> None:
    """Phase 8D.1 lost 35 computed case results to a crash in a persistence
    path. Observability must never be able to do that: it runs after every
    commit, and a failure is reported rather than propagated.
    """
    monkeypatch.setattr(
        runner_module, "run_verification", _fake_verification([_defect("HIGH")], "UNVERIFIED")
    )

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(runner_module.witness_log, "write_witness_log", _boom)

    eval_run, results = run_benchmark(
        config=_config(tmp_path), provider_name="anthropic", judge_model="m", category="quality"
    )

    assert len(results) == 10
    assert eval_run.total_cases == 10
    assert all(r.error is None for r in results)
    assert [r.actual_verdict for r in results] == ["UNVERIFIED"] * 10


def test_write_witness_log_reports_rather_than_raises_on_an_unwritable_path(
    tmp_path: Path, capsys
) -> None:
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("i am a file", encoding="utf-8")

    written = witness_log.write_witness_log(blocked / "state.db", 1, [_result([_defect("HIGH")])])

    assert written is None
    assert "witness log" in capsys.readouterr().err.lower()


def test_12_a_run_with_no_witnesses_is_unchanged_and_logs_only_no_witness(
    monkeypatch, tmp_path: Path
) -> None:
    """The safe path must stay the safe path: with no witness anywhere, every
    verdict is what it always was and every record says so.
    """
    monkeypatch.setattr(
        runner_module, "run_verification", _fake_verification([_defect("HIGH")], "UNVERIFIED")
    )

    eval_run, results = run_benchmark(
        config=_config(tmp_path), provider_name="anthropic", judge_model="m", category="quality"
    )

    assert [r.actual_verdict for r in results] == ["UNVERIFIED"] * 10
    records = [
        json.loads(line)
        for line in (tmp_path / f"witness-{eval_run.id}.jsonl").read_text("utf-8").splitlines()
    ]
    assert all(d["witness_result"] == witness.NO_WITNESS for r in records for d in r["defects"])
    assert all(r["demoted"] == 0 for r in records)
    assert not any(r["witness_changed_verdict"] for r in records)


def test_summary_counts_every_status_across_a_run() -> None:
    """The aggregate the phase actually reads: emission, execution and
    refutation rates come straight off these counts.
    """
    results = [
        _result([_defect("HIGH")]),
        _result([_defect("HIGH", witness={"call": "f"}, witness_result=witness.VERIFIED)]),
        _result(
            [_defect("MEDIUM", witness={"call": "f"}, witness_result=witness.REFUTED,
                     original_severity="HIGH")],
            actual="OK",
        ),
        _result([_defect("HIGH", witness="prose", witness_result=witness.UNSUPPORTED)]),
        _result([_defect("HIGH", witness={"call": "f"}, witness_result=witness.INCONCLUSIVE)]),
    ]
    summary = witness_log.summarize([witness_log.case_record(r) for r in results])

    assert summary["defects"] == 5
    assert summary["blocking_defects_before"] == 5
    assert summary["blocking_defects_after"] == 4
    assert summary["by_status"] == {
        witness.NO_WITNESS: 1,
        witness.VERIFIED: 1,
        witness.REFUTED: 1,
        witness.UNSUPPORTED: 1,
        witness.INCONCLUSIVE: 1,
    }
    assert summary["emitted"] == 4
    assert summary["executed"] == 4
    assert summary["demoted"] == 1
    assert summary["verdicts_changed"] == 1
