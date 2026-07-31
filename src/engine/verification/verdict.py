from engine.verification.rubric import BLOCKING


def _has_blocking(merged: dict) -> bool:
    return any(d.get("severity") in BLOCKING for d in merged.get("defects", []))


def merge(critic_outputs: list[dict], script_defects: list[dict]) -> dict:
    all_defects: list[dict] = []
    for critic in critic_outputs:
        all_defects.extend(critic.get("defects", []) or [])
    all_defects.extend(script_defects or [])
    verdict = "FAIL" if any(d.get("severity") in BLOCKING for d in all_defects) else "OK"
    return {"defects": all_defects, "verdict": verdict}


def gate(merged: dict, automated_passed: bool, schema_errors: list[str]) -> str:
    if schema_errors:
        return "UNVERIFIED"
    if not automated_passed:
        return "UNVERIFIED"
    if _has_blocking(merged):
        return "UNVERIFIED"
    return "OK"
