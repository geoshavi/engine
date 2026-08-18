from typing import Any

from engine.verification.rubric import BLOCKING, CRITIC_KEYS, DEFECT_KEYS, DIMENSIONS, SEVERITIES


def derive_verdict(defects: Any) -> str:
    """The authoritative verdict rule: any CRITICAL/HIGH defect means FAIL.

    Single source of truth for "does this set of findings block". The model
    also emits a "verdict" string, but it is a duplicate of information the
    severities already carry and is normalized to this value after parsing --
    an LLM-supplied string must never be able to override the structured
    severity evidence, in either direction.
    """
    if not isinstance(defects, list):
        return "OK"
    return (
        "FAIL"
        if any(isinstance(d, dict) and d.get("severity") in BLOCKING for d in defects)
        else "OK"
    )


def enforce_critic_schema(critic: Any) -> list[str]:
    errs: list[str] = []

    if not isinstance(critic, dict):
        return [f"critic must be a JSON object, got {type(critic).__name__}"]

    defects = critic.get("defects")
    if not isinstance(defects, list):
        errs.append("defects: must be a list")
        defects = []
    for i, d in enumerate(defects):
        if not isinstance(d, dict):
            errs.append(f"defects[{i}]: must be an object")
            continue
        missing = DEFECT_KEYS - d.keys()
        if missing:
            errs.append(f"defects[{i}]: missing keys {sorted(missing)}")
        if d.get("severity") not in SEVERITIES:
            errs.append(f"defects[{i}].severity: must be one of {sorted(SEVERITIES)}")
        if d.get("category") not in DIMENSIONS:
            # Deliberate fail-closed, decided 2026-08-06 -- not an oversight.
            # A lens can honestly find an off-topic defect (observed:
            # security lens labeling a sort-order bug "LOGIC" instead of
            # "SECURITY", 8/8 runs on correctness-04-broken). Rejected two
            # alternatives: coercing the category to the lens's own fixed
            # value would silently overwrite what the model actually said;
            # widening DIMENSIONS would change eval/dataset.py's
            # category_accuracy scoring right after it was stabilized.
            # Every observed occurrence so far was redundantly caught by a
            # different lens at blocking severity, so this has cost
            # visibility, not accuracy. Revisit ONLY if a future run shows
            # an out-of-enum category as the ONLY lens catching a real
            # defect -- query eval_case_schema_failures for error_detail
            # LIKE '%.category:%' to check.
            errs.append(f"defects[{i}].category: must be one of {list(DIMENSIONS)}")

    verdict = critic.get("verdict")
    if verdict not in ("OK", "FAIL"):
        errs.append("verdict: must be 'OK' or 'FAIL'")
    # A verdict that disagrees with its own defect severities is NOT an error.
    # Severities are authoritative -- verdict.merge() and verdict.gate() have
    # always decided on severity alone and never read this field, so the string
    # carries no downstream authority. Rejecting the whole response over it
    # discarded a lens's entire findings and failed the case closed (Phase 8C:
    # 6 of 7 schema failures were exactly this, after severities correctly
    # softened to MEDIUM/LOW but a stale "FAIL" was still emitted).
    # _parse_critic() normalizes the field to derive_verdict() instead, so no
    # consumer ever sees a contradictory value. The unsafe direction stays
    # safe by construction: "OK" alongside a HIGH defect now *keeps* that
    # defect and blocks on it, where before the defect was thrown away and
    # only the schema error blocked.

    stray = set(critic.keys()) - CRITIC_KEYS
    if stray:
        errs.append(f"unexpected top-level keys: {sorted(stray)}")

    return errs
