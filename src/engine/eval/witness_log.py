"""Passive per-defect record of what witness verification did in a run.

Purely derived: every field comes from data ``run_benchmark`` already produced,
the log is written once after every database commit, and nothing here can reach
a verdict. A failure to write is reported, never propagated -- Phase 8D.1 lost
35 computed case results to an exception raised inside a persistence path, and
observability must never be able to repeat that.

It exists to separate two outcomes a verdict column cannot tell apart: a
mechanism that ran and did not help, and a mechanism the model never used.

The record lives beside the run's database (``witness-<eval_run_id>.jsonl``), so
an experiment pointed at an isolated ``ENGINE_DB_PATH`` keeps its own log with
no schema change and no migration.
"""

import json
import sys
from pathlib import Path

from engine.state.models import EvalCaseResult
from engine.verification.rubric import BLOCKING
from engine.verification.witness import (
    INCONCLUSIVE,
    NO_WITNESS,
    REFUTED,
    UNSUPPORTED,
    VERIFIED,
)

# Not a verification outcome: the witness layer only executes witnesses on
# blocking defects, so a witness attached to a MEDIUM/LOW finding is emitted and
# never run. Recording that as NO_WITNESS would understate emission, and as a
# verification status would claim an execution that never happened.
NOT_EXECUTED = "NOT_EXECUTED"

_STATUSES = (NO_WITNESS, VERIFIED, REFUTED, UNSUPPORTED, INCONCLUSIVE)


def _defect_record(defect: dict) -> dict:
    effective = defect.get("severity")
    # original_severity is written by the witness layer only on demotion, so
    # its absence means the severity is untouched.
    original = defect.get("original_severity", effective)
    emitted = defect.get("witness") is not None
    status = defect.get("witness_result")
    return {
        "lens": defect.get("lens"),
        "id": defect.get("id"),
        "category": defect.get("category"),
        "original_severity": original,
        "effective_severity": effective,
        "witness_emitted": emitted,
        "witness_executed": status is not None,
        "witness_result": status or (NOT_EXECUTED if emitted else NO_WITNESS),
        "blocking": effective in BLOCKING,
        "authority_removed": original in BLOCKING and effective not in BLOCKING,
    }


def case_record(result: EvalCaseResult) -> dict:
    defects = [_defect_record(d) for d in result.defects]
    would_block = any(d["original_severity"] in BLOCKING for d in defects)
    does_block = any(d["blocking"] for d in defects)
    return {
        "eval_run_id": result.eval_run_id,
        "eval_case_id": result.eval_case_id,
        "expected_verdict": result.expected_verdict,
        "actual_verdict": result.actual_verdict,
        "passed": result.passed,
        "error": result.error,
        "blocking_defects_before": sum(1 for d in defects if d["original_severity"] in BLOCKING),
        "blocking_defects": sum(1 for d in defects if d["blocking"]),
        "demoted": sum(1 for d in defects if d["witness_result"] == REFUTED),
        # The attribution question: would this case have been blocked by the
        # severities the critics actually filed, and is it not blocked now?
        "witness_changed_verdict": would_block and not does_block,
        "defects": defects,
    }


def summarize(records: list[dict]) -> dict:
    defects = [d for r in records for d in r["defects"]]
    by_status = {s: 0 for s in _STATUSES}
    for d in defects:
        by_status[d["witness_result"]] = by_status.get(d["witness_result"], 0) + 1
    return {
        "cases": len(records),
        "defects": len(defects),
        "blocking_defects_before": sum(1 for d in defects if d["original_severity"] in BLOCKING),
        "blocking_defects_after": sum(1 for d in defects if d["blocking"]),
        "by_status": by_status,
        "emitted": sum(1 for d in defects if d["witness_emitted"]),
        "executed": sum(1 for d in defects if d["witness_executed"]),
        "demoted": sum(1 for d in defects if d["witness_result"] == REFUTED),
        "verdicts_changed": sum(1 for r in records if r["witness_changed_verdict"]),
    }


def write_witness_log(
    db_path: Path, eval_run_id: int, results: list[EvalCaseResult]
) -> Path | None:
    """One JSON object per case, beside the run's database. None if it failed."""
    path = Path(db_path).parent / f"witness-{eval_run_id}.jsonl"
    try:
        with path.open("w", encoding="utf-8") as handle:
            for result in results:
                handle.write(json.dumps(case_record(result), ensure_ascii=True) + "\n")
    except OSError as exc:
        # Reported, not raised: the run's verdicts are already committed and
        # must not be lost to a diagnostics failure.
        print(f"WARNING: witness log could not be written to {path}: {exc}", file=sys.stderr)
        return None
    return path
