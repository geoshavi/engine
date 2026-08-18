"""Refutation-only witness verification (Phase 8D.2B).

The single invariant every test here exists to protect:

    Executing a witness may only ever REMOVE blocking authority, and only when
    deterministic execution CONTRADICTS the critic's own claimed observation.

Nothing a model writes can raise a severity, and every path that fails to
produce a clean contradiction -- malformed witness, missing callable, timeout,
crashed child, unrepresentable value, nondeterministic result, no witness at
all -- leaves the defect exactly as the critic filed it.
"""

import json
from decimal import Decimal
from pathlib import Path

from engine.llm_types import Message
from engine.providers.base import GenerationResult
from engine.runtime.budget import BudgetController
from engine.runtime.gateway import LLMGateway
from engine.verification import verdict, witness
from engine.verification.pipeline import run_verification

# ------------------------------------------------------------------ fixtures

STRICT_TOLERANCE = (
    "def is_close_enough(a: float, b: float) -> bool:\n    return abs(a - b) < 0.01\n"
)
INCLUSIVE_TOLERANCE = (
    "def is_close_enough(a: float, b: float) -> bool:\n    return abs(a - b) <= 0.01\n"
)
CHAR_TRUNCATE = "def truncate(text: str, max_chars: int) -> str:\n    return text[:max_chars]\n"
BYTE_TRUNCATE = (
    "def truncate(text: str, max_chars: int) -> str:\n"
    '    return text.encode("utf-8")[:max_chars].decode("utf-8")\n'
)


def _workspace(tmp_path: Path, source: str) -> Path:
    (tmp_path / "solution.py").write_text(source, encoding="utf-8")
    return tmp_path


def _returns(call: str, args: list, value: object) -> dict:
    return {"call": call, "args": args, "expect": {"returns": value}}


def _raises(call: str, args: list, exc: str) -> dict:
    return {"call": call, "args": args, "expect": {"raises": exc}}


def _defect(severity: str, **extra: object) -> dict:
    d = {
        "id": "C1",
        "category": "CORRECTNESS",
        "severity": severity,
        "location": "solution.py:2",
        "fix": "...",
    }
    d.update(extra)
    return d


def _apply(defects: list[dict], workspace: Path) -> dict:
    return witness.apply_witness_verification(verdict.merge([{"defects": defects}], []), workspace)


def _blocking_count(merged: dict) -> int:
    return sum(1 for d in merged["defects"] if d["severity"] in ("CRITICAL", "HIGH"))


# ------------------------------------------------- A. the fabricated witness


def test_a_fabricated_float_witness_is_refuted_and_loses_blocking_authority(
    tmp_path: Path,
) -> None:
    """Verbatim from the Phase 8D.1 partial run: the judge rated
    `abs(a - b) < 0.01` HIGH and wrote "is_close_enough(0.1 + 0.2, 0.3)
    currently returns False". It returns True. That is the whole reason this
    mechanism exists.
    """
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    claim = _returns("is_close_enough", [0.30000000000000004, 0.3], False)

    assert witness.verify(claim, ws) == witness.REFUTED

    merged = _apply([_defect("HIGH", witness=claim)], ws)

    assert merged["defects"][0]["severity"] not in ("CRITICAL", "HIGH")
    assert merged["defects"][0]["original_severity"] == "HIGH"
    assert merged["defects"][0]["witness_result"] == witness.REFUTED
    assert verdict.gate(merged, True, []) == "OK"


# ---------------------------------------------- B. genuine boundary defect


def test_b_real_strict_boundary_violation_stays_blocking(tmp_path: Path) -> None:
    """`<=` where the task requires `<`: a difference of exactly the threshold
    is wrongly accepted. 0.0 and 0.01 are both exactly representable, so this
    witness carries no floating-point ambiguity of its own.
    """
    ws = _workspace(tmp_path, INCLUSIVE_TOLERANCE)
    claim = _returns("is_close_enough", [0.0, 0.01], True)

    assert witness.verify(claim, ws) == witness.VERIFIED

    merged = _apply([_defect("HIGH", witness=claim)], ws)

    assert merged["defects"][0]["severity"] == "HIGH"
    assert "original_severity" not in merged["defects"][0]
    assert verdict.gate(merged, True, []) == "UNVERIFIED"


# ------------------------------------------- C. the false byte-slicing claim


def test_c_character_slicing_called_byte_slicing_is_refuted(tmp_path: Path) -> None:
    """`str` slices code points, so no encoded sequence can be split. Both
    lenses asserted otherwise on every stored observation of this shape.
    """
    ws = _workspace(tmp_path, CHAR_TRUNCATE)
    claim = _raises("truncate", ["café naïve", 4], "UnicodeDecodeError")

    assert witness.verify(claim, ws) == witness.REFUTED
    assert _blocking_count(_apply([_defect("HIGH", witness=claim)], ws)) == 0


def test_c2_astral_character_slicing_is_also_refuted(tmp_path: Path) -> None:
    """The claim's own favourite example. Also proves an astral code point
    survives the JSON round trip through the runner.
    """
    ws = _workspace(tmp_path, CHAR_TRUNCATE)
    claim = _returns("truncate", ["\U0001f44b\U0001f44b\U0001f44b", 2], "\U0001f44b")

    assert witness.verify(claim, ws) == witness.REFUTED


# ---------------------------------------------- D. genuine encoding defect


def test_d_real_encoded_byte_truncation_stays_blocking(tmp_path: Path) -> None:
    """Truncating the encoded bytes really can cut a sequence in half."""
    ws = _workspace(tmp_path, BYTE_TRUNCATE)
    claim = _raises("truncate", ["héllo", 2], "UnicodeDecodeError")

    assert witness.verify(claim, ws) == witness.VERIFIED
    assert _blocking_count(_apply([_defect("HIGH", witness=claim)], ws)) == 1


def test_d2_wrong_exception_type_is_not_verified_and_still_does_not_demote(
    tmp_path: Path,
) -> None:
    """The code raises, but not what was claimed. That is not a verification --
    and it is not a refutation either, because it cannot be told apart from a
    witness whose arguments never fitted the function in the first place.
    """
    ws = _workspace(tmp_path, BYTE_TRUNCATE)
    claim = _raises("truncate", ["héllo", 2], "ValueError")

    assert witness.verify(claim, ws) == witness.INCONCLUSIVE
    assert _blocking_count(_apply([_defect("HIGH", witness=claim)], ws)) == 1


# ---------------------------------------------------- E. missing callable


def test_e_missing_callable_is_inconclusive_and_never_demotes(tmp_path: Path) -> None:
    """An import that cannot resolve is the absence of an observation, not a
    contradiction. Reading it as refutation would let a typo disarm a blocker.
    """
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    claim = _returns("no_such_function", [1], True)

    assert witness.verify(claim, ws) == witness.INCONCLUSIVE
    assert _blocking_count(_apply([_defect("CRITICAL", witness=claim)], ws)) == 1


def test_e2_attribute_that_is_not_callable_is_inconclusive(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "VERSION = 3\n")
    assert witness.verify(_returns("VERSION", [], 3), ws) == witness.INCONCLUSIVE


# ------------------------------------------------ F. unsupported witnesses


def test_f_witnesses_that_are_not_json_literals_are_unsupported(tmp_path: Path) -> None:
    """Rejected before anything is executed, and never as a refutation."""
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    rejected = [
        {"call": "is_close_enough", "args": "not-a-list", "expect": {"returns": True}},
        {"call": "is_close_enough", "args": [float("nan")], "expect": {"returns": True}},
        {"call": "is_close_enough", "args": [1, 2]},
        {"call": "is_close_enough", "args": [1, 2], "expect": {}},
        {"call": "is_close_enough", "args": [1, 2], "expect": {"returns": True, "raises": "E"}},
        {"call": "is_close_enough", "args": [1, 2], "expect": {"raises": 7}},
        {"args": [1, 2], "expect": {"returns": True}},
        "a witness written as prose",
        [],
    ]
    for claim in rejected:
        assert witness.verify(claim, ws) == witness.UNSUPPORTED, claim

    assert _blocking_count(_apply([_defect("HIGH", witness=rejected[0])], ws)) == 1


def test_q_call_names_that_are_not_plain_identifiers_are_unsupported(tmp_path: Path) -> None:
    """The runner resolves one attribute by name. Dotted paths and dunders are
    refused outright rather than handed to getattr.
    """
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    for name in ["os.system", "__import__", "_private", "", "is close enough"]:
        claim = _returns(name, [], True)
        assert witness.verify(claim, ws) == witness.UNSUPPORTED, name


def test_q2_a_callable_the_reviewed_code_merely_imported_is_not_executed(tmp_path: Path) -> None:
    """`from os import getcwd` puts a real stdlib callable at module top level.
    Only callables the reviewed file itself defines may be witnessed, or the
    witness becomes a way to invoke whatever the code happened to import.
    """
    ws = _workspace(tmp_path, "from os import getcwd\n\n\ndef f() -> int:\n    return 1\n")
    assert witness.verify(_returns("getcwd", [], "/"), ws) == witness.INCONCLUSIVE


# ------------------------------------------------------------- G. timeout


def test_g_timeout_is_inconclusive_and_never_demotes(tmp_path: Path, monkeypatch) -> None:
    ws = _workspace(tmp_path, "import time\n\n\ndef spin() -> int:\n    time.sleep(30)\n    return 1\n")
    monkeypatch.setattr(witness, "TIMEOUT_SECONDS", 1)
    claim = _returns("spin", [], 1)

    assert witness.verify(claim, ws) == witness.INCONCLUSIVE
    assert _blocking_count(_apply([_defect("HIGH", witness=claim)], ws)) == 1


# ----------------------------------------------------- H. crashed process


def test_h_child_process_death_is_inconclusive_and_never_demotes(tmp_path: Path) -> None:
    """The child dies without writing an observation. No output is not a
    contradiction.
    """
    ws = _workspace(tmp_path, "import os\n\n\ndef bail() -> int:\n    os._exit(3)\n")
    claim = _returns("bail", [], 1)

    assert witness.verify(claim, ws) == witness.INCONCLUSIVE
    assert _blocking_count(_apply([_defect("CRITICAL", witness=claim)], ws)) == 1


def test_h2_module_that_fails_to_import_is_inconclusive(tmp_path: Path) -> None:
    """An exception raised at import time is not the call raising -- reading it
    as the claimed exception would verify or refute on the wrong evidence.
    """
    ws = _workspace(tmp_path, 'raise RuntimeError("boom")\n')
    assert witness.verify(_raises("anything", [], "RuntimeError"), ws) == witness.INCONCLUSIVE


def test_h3_unrepresentable_return_value_is_inconclusive(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "def make() -> object:\n    return object()\n")
    assert witness.verify(_returns("make", [], None), ws) == witness.INCONCLUSIVE


# ---------------------------------------------------------- I. no witness


def test_i_a_defect_with_no_witness_is_left_exactly_as_filed(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    merged = _apply([_defect("HIGH"), _defect("CRITICAL")], ws)

    assert [d["severity"] for d in merged["defects"]] == ["HIGH", "CRITICAL"]
    assert all("witness_result" not in d for d in merged["defects"])
    assert verdict.gate(merged, True, []) == "UNVERIFIED"
    assert witness.verify(None, ws) == witness.NO_WITNESS


# --------------------------------------------------------- J. siblings


def test_j_only_the_refuted_defect_is_demoted(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    refuted = _defect("HIGH", id="C1", witness=_returns("is_close_enough", [0.0, 0.0], False))
    verified = _defect("HIGH", id="C2", witness=_returns("is_close_enough", [0.0, 0.0], True))
    bare = _defect("CRITICAL", id="C3")

    merged = _apply([refuted, verified, bare], ws)
    by_id = {d["id"]: d for d in merged["defects"]}

    assert by_id["C1"]["severity"] == "MEDIUM"
    assert by_id["C2"]["severity"] == "HIGH"
    assert by_id["C3"]["severity"] == "CRITICAL"
    assert verdict.gate(merged, True, []) == "UNVERIFIED"  # siblings still block


def test_j2_a_surviving_sibling_alone_keeps_the_case_blocked(tmp_path: Path) -> None:
    """The measured protection for broken cases: they carry 2-9 blocking
    findings, so one refutation cannot open the gate.
    """
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    merged = _apply(
        [
            _defect("HIGH", id="C1", witness=_returns("is_close_enough", [0.0, 0.0], False)),
            _defect("HIGH", id="C2"),
        ],
        ws,
    )
    assert verdict.gate(merged, True, []) == "UNVERIFIED"


# ------------------------------------- K/M/O. authority can only be removed


def test_k_blocking_severity_without_a_refutation_still_blocks(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    for severity in ("CRITICAL", "HIGH"):
        for claim in (None, _returns("gone", [], 1), {"call": "!", "args": [], "expect": {}}):
            defect = _defect(severity) if claim is None else _defect(severity, witness=claim)
            merged = _apply([defect], ws)
            assert verdict.gate(merged, True, []) == "UNVERIFIED", (severity, claim)


def test_m_a_finding_whose_witness_cannot_be_expressed_stays_blocking(tmp_path: Path) -> None:
    """The SQL-injection shape: the entry point needs a live connection object,
    which is not a JSON literal, so no witness for it can be formed at all.
    Protection by contract shape, not by a policy exception.
    """
    ws = _workspace(
        tmp_path,
        "import sqlite3\n\n\n"
        "def get_user(conn: sqlite3.Connection, email: str) -> object:\n"
        '    return conn.execute(f"SELECT * FROM users WHERE email = \'{email}\'").fetchone()\n',
    )
    claim = _returns("get_user", [{"__conn__": True}, "x' OR '1'='1"], None)

    assert witness.verify(claim, ws) == witness.INCONCLUSIVE
    merged = _apply([_defect("CRITICAL", category="SECURITY", witness=claim)], ws)
    assert merged["defects"][0]["severity"] == "CRITICAL"
    assert verdict.gate(merged, True, []) == "UNVERIFIED"


def test_o_a_verified_witness_never_raises_severity(tmp_path: Path) -> None:
    """Non-blocking findings are not executed at all, and no outcome -- not even
    a refutation -- may move a severity upward.
    """
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    verified = _defect("MEDIUM", id="C1", witness=_returns("is_close_enough", [0.0, 0.0], True))
    refuted = _defect("LOW", id="C2", witness=_returns("is_close_enough", [0.0, 0.0], False))

    merged = _apply([verified, refuted], ws)
    by_id = {d["id"]: d for d in merged["defects"]}

    assert by_id["C1"]["severity"] == "MEDIUM"
    assert by_id["C2"]["severity"] == "LOW"
    assert all("witness_result" not in d for d in merged["defects"])
    assert verdict.gate(merged, True, []) == "OK"


# ------------------------------------------------------ N. nondeterminism


def test_n_a_nondeterministic_observation_is_never_read_as_refutation(tmp_path: Path) -> None:
    """One mismatch is not a contradiction if the function does not answer the
    same way twice. Both executions share a working directory precisely so that
    state-dependent variation is visible to the guard.
    """
    ws = _workspace(
        tmp_path,
        "import pathlib\n\n\n"
        "def counter() -> int:\n"
        '    p = pathlib.Path("calls.txt")\n'
        "    n = int(p.read_text()) if p.exists() else 0\n"
        "    p.write_text(str(n + 1))\n"
        "    return n\n",
    )
    claim = _returns("counter", [], 99)

    assert witness.verify(claim, ws) == witness.INCONCLUSIVE
    assert _blocking_count(_apply([_defect("HIGH", witness=claim)], ws)) == 1


# ------------------------------------------------------- R. script defects


def test_r_automated_gate_defects_are_never_touched(tmp_path: Path) -> None:
    """ruff/mypy findings are engine-generated and carry no witness; they must
    pass through byte for byte.
    """
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    script = {
        "id": "AUTO1-mypy",
        "category": "CORRECTNESS",
        "severity": "HIGH",
        "location": "mypy",
        "fix": "type error on line 4",
    }
    merged = witness.apply_witness_verification(verdict.merge([], [dict(script)]), ws)

    assert merged["defects"] == [script]
    assert verdict.gate(merged, True, []) == "UNVERIFIED"


# ------------------------------------------------- P. environment scrubbing


def test_p_the_child_never_receives_provider_credentials(tmp_path: Path, monkeypatch) -> None:
    """The existing gates in automated.py inherit the whole environment. The
    witness child must not: it runs code that, in production, a model wrote.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-be-visible")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-should-never-be-visible")
    ws = _workspace(
        tmp_path,
        "import os\n\n\n"
        "def leaked() -> list[str]:\n"
        "    return sorted(k for k in os.environ if k.endswith(\"_API_KEY\"))\n",
    )
    assert witness.verify(_returns("leaked", [], []), ws) == witness.VERIFIED


# ------------------------------------------------- merged-object invariant


def test_merged_verdict_field_stays_consistent_with_its_own_severities(
    tmp_path: Path,
) -> None:
    """verdict.merge() computes "verdict" from the severities it merged. After
    a demotion that field would be stale, so it is recomputed -- keeping
    merge()'s own invariant, not normalizing anything the model said.
    """
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    merged = _apply(
        [_defect("HIGH", witness=_returns("is_close_enough", [0.0, 0.0], False))], ws
    )
    assert merged["verdict"] == "OK"

    still_blocking = _apply([_defect("HIGH")], ws)
    assert still_blocking["verdict"] == "FAIL"


# ------------------------------------------------------ L. end-to-end paths


class _FakeProvider:
    name = "fake"

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    def generate(
        self,
        messages: list[Message],
        model: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
    ) -> GenerationResult:
        return GenerationResult(
            text=self._response_text, model=model, provider=self.name, input_tokens=1, output_tokens=1
        )


def _run_pipeline(tmp_path: Path, response: str) -> str:
    ws = _workspace(tmp_path, STRICT_TOLERANCE)
    status, _merged, _gates = run_verification(
        ws,
        LLMGateway(_FakeProvider(response)),
        BudgetController(max_tokens=100_000, planned_budget=Decimal("1.00")),
        "claude-haiku-4-5-20251001",
        "compare currency amounts",
        run_id=1,
        task_id="task-1",
        conn=None,
    )
    return status


def test_end_to_end_a_refuted_blocker_opens_the_gate(tmp_path: Path) -> None:
    critic = json.dumps(
        {
            "defects": [
                {
                    "id": "C1",
                    "category": "CORRECTNESS",
                    "severity": "HIGH",
                    "location": "solution.py:2",
                    "fix": "use decimal arithmetic instead",
                    "witness": {
                        "call": "is_close_enough",
                        "args": [0.30000000000000004, 0.3],
                        "expect": {"returns": False},
                    },
                }
            ],
            "verdict": "FAIL",
        }
    )
    assert _run_pipeline(tmp_path, critic) == "OK"


def test_end_to_end_an_unwitnessed_blocker_still_closes_the_gate(tmp_path: Path) -> None:
    critic = json.dumps(
        {
            "defects": [
                {
                    "id": "C1",
                    "category": "CORRECTNESS",
                    "severity": "HIGH",
                    "location": "solution.py:2",
                    "fix": "use decimal arithmetic instead",
                }
            ],
            "verdict": "FAIL",
        }
    )
    assert _run_pipeline(tmp_path, critic) == "UNVERIFIED"


def test_l_malformed_critic_response_still_fails_closed(tmp_path: Path) -> None:
    assert _run_pipeline(tmp_path, "no json here at all") == "UNVERIFIED"
