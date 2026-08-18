"""Refutation-only witness verification.

A critic may attach a ``witness`` to a CRITICAL/HIGH defect: one call it claims
demonstrates the defect. This module executes that call and compares the result
with what the critic said would happen.

**The invariant, and the whole point of the design:**

    Execution may only ever REMOVE blocking authority, and only when a
    deterministic observation CONTRADICTS the critic's own claim.

    VERIFIED / UNSUPPORTED / INCONCLUSIVE / NO_WITNESS -> severity untouched.
    REFUTED -> that one defect drops below blocking.

Nothing a model writes can raise a severity, and every path that fails to
produce a clean contradiction leaves the finding exactly as filed. That
asymmetry is what makes the mechanism safe when it does not work: a model that
supplies no witness, or an unusable one, gets the engine's existing behaviour.

Phase 8D.1 asked the model to judge its own evidence and it fabricated evidence
that read as concrete -- "is_close_enough(0.1 + 0.2, 0.3) currently returns
False", which returns True. The correction is not stronger wording. The prompt
asks for the observation; this module, never the model, decides what it is
worth.

Scope, deliberately narrow: a single call, JSON-literal arguments, and either a
JSON-representable return value or an exception type. Findings that cannot be
put in that form -- an injection that needs a live connection, a race, a naming
preference -- are UNSUPPORTED and keep their severity. That is not a gap to be
closed later; it is the reason those findings stay blocking.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from engine.verification.rubric import BLOCKING

VERIFIED = "VERIFIED"
REFUTED = "REFUTED"
UNSUPPORTED = "UNSUPPORTED"  # the witness could not be read as a checkable claim
INCONCLUSIVE = "INCONCLUSIVE"  # it was checkable, but no clean observation came back
NO_WITNESS = "NO_WITNESS"

TIMEOUT_SECONDS = 10
DEMOTED_SEVERITY = "MEDIUM"

_RUNNER = Path(__file__).with_name("witness_runner.py")

# The child runs code that, in production, a model wrote. automated.py's gates
# inherit the whole environment; this must not -- os.environ holds the provider
# API keys. Allowlist rather than denylist, and PATH is kept deliberately:
# removing it changes what the reviewed code does (a missing binary turns into
# FileNotFoundError), which could refute a true finding for the wrong reason.
_ENV_ALLOWLIST = frozenset(
    {"COMSPEC", "LANG", "LC_ALL", "PATH", "PATHEXT", "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP",
     "TMPDIR", "WINDIR"}
)

_NO_OBSERVATION = frozenset(
    {"import_error", "missing_callable", "not_callable", "foreign_callable", "unrepresentable"}
)


def _is_json_literal(value: Any) -> bool:
    """True iff ``value`` survives a JSON round trip unchanged.

    Rejects NaN/Infinity (which ``json`` accepts by default but no other
    parser does) and dicts keyed by anything but strings, which JSON silently
    coerces -- a comparison against a coerced value would be meaningless.
    """
    try:
        return bool(json.loads(json.dumps(value, allow_nan=False)) == value)
    except (TypeError, ValueError):
        return False


def _parse(witness: Any) -> dict | None:
    """The witness as a checkable claim, or None if it is not one."""
    if not isinstance(witness, dict):
        return None

    call = witness.get("call")
    # A plain identifier only: no dotted paths, and no dunder/private names.
    # The runner resolves exactly one attribute, so anything else is refused
    # here rather than handed to getattr.
    if not isinstance(call, str) or not call.isidentifier() or call.startswith("_"):
        return None

    args = witness.get("args")
    if not isinstance(args, list) or not _is_json_literal(args):
        return None

    expect = witness.get("expect")
    if not isinstance(expect, dict) or len(expect) != 1:
        return None
    if "returns" in expect:
        if not _is_json_literal(expect["returns"]):
            return None
    elif "raises" in expect:
        exc = expect["raises"]
        if not isinstance(exc, str) or not exc.isidentifier():
            return None
    else:
        return None

    return {"call": call, "args": args, "expect": expect}


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}
    # Engine-set, not inherited: the observation crosses the pipe as JSON and
    # must not depend on the parent's console codepage.
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _observe(work_dir: Path, modules: list[str], claim: dict) -> dict:
    """One execution. Any failure to get an answer is an absent observation."""
    spec = json.dumps({"modules": modules, "call": claim["call"], "args": claim["args"]})
    try:
        proc = subprocess.run(
            [sys.executable, str(_RUNNER)],
            cwd=work_dir,
            input=spec,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT_SECONDS,
            check=False,
            env=_child_env(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return {"outcome": "no_answer"}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"outcome": "no_answer"}
    try:
        observation = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"outcome": "no_answer"}
    return observation if isinstance(observation, dict) else {"outcome": "no_answer"}


def _classify(observation: dict, expect: dict) -> str:
    outcome = observation.get("outcome")
    if outcome in _NO_OBSERVATION or outcome == "no_answer":
        return INCONCLUSIVE
    if outcome == "raised":
        # An exception where a value was claimed is the ABSENCE of the claimed
        # kind of observation, not a contradiction of it -- and it is what a
        # witness whose arguments do not fit the function's contract produces.
        # Reading it as refutation would let a badly-shaped witness disarm a
        # finding whose real entry point takes a live object (a connection, a
        # socket, a file handle) that no JSON literal can supply. A different
        # exception type than claimed is treated the same way, for the same
        # reason: it is indistinguishable from an argument-shape failure.
        if "raises" not in expect:
            return INCONCLUSIVE
        return VERIFIED if observation.get("exc_type") == expect["raises"] else INCONCLUSIVE
    if outcome == "returned":
        # The reverse direction IS a clean contradiction: the call ran to
        # completion, so "it raises" was observed to be false.
        if "returns" not in expect:
            return REFUTED
        # Deliberately `==` rather than a strict type match: the dangerous
        # direction is a wrong REFUTED, so 1 vs 1.0 and 1 vs True are treated
        # as agreement, which costs nothing (severity is left alone) instead of
        # disarming a finding on a formatting difference.
        return VERIFIED if observation.get("value") == expect["returns"] else REFUTED
    return INCONCLUSIVE


def verify(witness: Any, workspace: Path) -> str:
    """One of VERIFIED / REFUTED / UNSUPPORTED / INCONCLUSIVE / NO_WITNESS."""
    if witness is None:
        return NO_WITNESS
    claim = _parse(witness)
    if claim is None:
        return UNSUPPORTED

    with tempfile.TemporaryDirectory() as tmp:
        # A copy, so reviewed code that writes files cannot disturb the
        # workspace the rest of the run still depends on. Module names come
        # from the workspace's own filenames -- never from the model.
        work_dir = Path(tmp) / "work"
        shutil.copytree(workspace, work_dir)
        modules = sorted(p.stem for p in work_dir.glob("*.py") if p.stem.isidentifier())
        if not modules:
            return INCONCLUSIVE

        first = _observe(work_dir, modules, claim)
        status = _classify(first, claim["expect"])
        if status != REFUTED:
            return status

        # Only a refutation costs anything, so only a refutation has to be
        # shown twice. Both executions share a working directory on purpose:
        # a function that answers differently the second time -- because it is
        # random, or because it kept state -- must not be read as contradicted.
        if _observe(work_dir, modules, claim) != first:
            return INCONCLUSIVE
        return REFUTED


def apply_witness_verification(merged: dict, workspace: Path) -> dict:
    """Demote every blocking defect whose own witness is refuted by execution.

    Untouched: non-blocking defects (a witness cannot raise a severity),
    defects with no witness, and script defects from the automated gates, which
    are engine-generated and never carry one.
    """
    defects = merged.get("defects") or []
    if not any(
        isinstance(d, dict) and d.get("severity") in BLOCKING and d.get("witness") is not None
        for d in defects
    ):
        return merged  # nothing executable -- not even a copy of the workspace

    checked = [_check(d, workspace) for d in defects]
    return {
        **merged,
        "defects": checked,
        # merge() derives this field from the severities it merged, so a
        # demotion leaves it stale. Recomputing keeps merge()'s own invariant;
        # it is not a normalization of anything the model said, and gate()
        # reads the severities regardless.
        "verdict": "FAIL" if any(d.get("severity") in BLOCKING for d in checked) else "OK",
    }


def _check(defect: Any, workspace: Path) -> Any:
    if not isinstance(defect, dict) or defect.get("severity") not in BLOCKING:
        return defect
    if defect.get("witness") is None:
        return defect

    status = verify(defect["witness"], workspace)
    if status != REFUTED:
        return {**defect, "witness_result": status}
    return {
        **defect,
        "severity": DEMOTED_SEVERITY,
        "original_severity": defect.get("severity"),
        "witness_result": status,
    }
