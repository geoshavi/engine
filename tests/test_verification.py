import json
from decimal import Decimal
from pathlib import Path

from engine.providers.base import GenerationResult, Message
from engine.runtime.budget import BudgetController
from engine.runtime.gateway import LLMGateway
from engine.state.models import VerificationResult
from engine.verification import pipeline, verdict
from engine.verification.automated import automated_defects, run_automated_gates
from engine.verification.judge import _parse_critic, run_judge_gates
from engine.verification.schema import enforce_critic_schema


def test_automated_gates_pass_on_clean_code(tmp_path: Path) -> None:
    (tmp_path / "solution.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    results = run_automated_gates(tmp_path)

    by_gate = {r.gate_name: r for r in results}
    assert by_gate["ruff"].passed
    assert by_gate["pytest"].passed  # no test files present -> auto-pass


def test_automated_gates_skip_when_no_python_files(tmp_path: Path) -> None:
    results = run_automated_gates(tmp_path)
    assert len(results) == 1
    assert results[0].passed


def test_automated_defects_only_for_failed_gates() -> None:
    results = [
        VerificationResult("ruff", True, "ok"),
        VerificationResult("mypy", False, "type error on line 4"),
    ]
    defects = automated_defects(results)
    assert len(defects) == 1
    assert defects[0]["category"] == "CORRECTNESS"
    assert defects[0]["severity"] == "HIGH"
    assert "type error on line 4" in defects[0]["fix"]


def test_enforce_critic_schema_accepts_well_formed_critic() -> None:
    critic = {"defects": [], "verdict": "OK"}
    assert enforce_critic_schema(critic) == []


def test_enforce_critic_schema_rejects_inconsistent_verdict() -> None:
    critic = {
        "defects": [
            {"id": "C1", "category": "CORRECTNESS", "severity": "CRITICAL", "location": "x", "fix": "y"}
        ],
        "verdict": "OK",
    }
    errors = enforce_critic_schema(critic)
    assert any("verdict" in e for e in errors)


def test_enforce_critic_schema_rejects_non_dict() -> None:
    assert enforce_critic_schema("not a dict") != []


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


def _gateway(response_text: str) -> LLMGateway:
    return LLMGateway(_FakeProvider(response_text))


def _budget() -> BudgetController:
    return BudgetController(max_tokens=100_000, planned_budget=Decimal("1.00"))


def _ok_critic_json() -> str:
    return json.dumps({"defects": [], "verdict": "OK"})


def test_parse_critic_accepts_valid_json() -> None:
    critic, errors = _parse_critic(_ok_critic_json())
    assert errors == []
    assert critic["verdict"] == "OK"


def test_parse_critic_rejects_non_json_text() -> None:
    critic, errors = _parse_critic("looks fine to me, no issues")
    assert critic == {}
    assert errors


def test_run_judge_gates_returns_one_critic_per_lens() -> None:
    critics, schema_errors = run_judge_gates(
        _gateway(_ok_critic_json()),
        _budget(),
        "claude-haiku-4-5-20251001",
        "do the thing",
        "print('hi')",
        run_id=1,
        task_id="task-1",
        conn=None,
    )
    assert schema_errors == []
    assert len(critics) == 3


def test_run_judge_gates_tags_each_defect_with_the_lens_that_produced_it() -> None:
    """Every lens call in this test gets the identical canned response (the
    fake provider ignores which lens/system prompt it was called with), and
    that response's defect always claims category "SECURITY" regardless of
    which lens is calling. If tagging fell back to trusting the model's own
    "category" field instead of the lens that actually made the call, every
    tagged defect here would incorrectly read "security" -- proving the tag
    must come from run_judge_gates' own loop variable, not from the parsed
    JSON.
    """
    response_text = json.dumps(
        {
            "defects": [
                {"id": "X1", "category": "SECURITY", "severity": "LOW", "location": "x", "fix": "y"}
            ],
            "verdict": "OK",
        }
    )
    critics, schema_errors = run_judge_gates(
        _gateway(response_text),
        _budget(),
        "claude-haiku-4-5-20251001",
        "do the thing",
        "print('hi')",
        run_id=1,
        task_id="task-1",
        conn=None,
    )
    assert schema_errors == []
    lenses_seen = {d["lens"] for critic in critics for d in critic["defects"]}
    assert lenses_seen == {"correctness", "security", "code-quality"}


class _SequencedFakeProvider:
    """Returns responses in call order rather than keying off the lens's
    system prompt text -- lets a test target exactly one lens via LENSES'
    stable dict iteration order (correctness, security, code-quality)
    without coupling to lens prompt wording.
    """

    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._calls = 0

    def generate(
        self,
        messages: list[Message],
        model: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
    ) -> GenerationResult:
        text = self._responses[self._calls]
        self._calls += 1
        return GenerationResult(
            text=text, model=model, provider=self.name, input_tokens=1, output_tokens=1
        )


def test_run_judge_gates_invokes_on_schema_failure_only_for_the_failing_lens() -> None:
    responses = [_ok_critic_json(), "not json at all", _ok_critic_json()]
    gateway = LLMGateway(_SequencedFakeProvider(responses))
    captured: list[tuple[str, str, list[str]]] = []

    critics, schema_errors = run_judge_gates(
        gateway,
        _budget(),
        "claude-haiku-4-5-20251001",
        "do the thing",
        "print('hi')",
        run_id=1,
        task_id="task-1",
        conn=None,
        on_schema_failure=lambda lens, text, errs: captured.append((lens, text, errs)),
    )

    assert len(critics) == 2  # only the 2 well-formed lenses
    assert len(captured) == 1
    lens, raw_response, errors = captured[0]
    assert lens == "security"
    assert raw_response == "not json at all"
    assert errors
    assert any(e.startswith("judge:security:") for e in schema_errors)


def test_run_judge_gates_on_schema_failure_gets_empty_string_not_none_for_empty_response() -> None:
    responses = [_ok_critic_json(), _ok_critic_json(), ""]
    gateway = LLMGateway(_SequencedFakeProvider(responses))
    captured: list[tuple[str, str, list[str]]] = []

    run_judge_gates(
        gateway,
        _budget(),
        "claude-haiku-4-5-20251001",
        "do the thing",
        "print('hi')",
        run_id=1,
        task_id="task-1",
        conn=None,
        on_schema_failure=lambda lens, text, errs: captured.append((lens, text, errs)),
    )

    assert len(captured) == 1
    lens, raw_response, _errors = captured[0]
    assert lens == "code-quality"
    assert raw_response == ""
    assert raw_response is not None


def test_run_judge_gates_without_callback_behaves_exactly_as_before() -> None:
    """on_schema_failure defaults to None -- every existing caller (api.py,
    orchestrator/engine.py) omits it, so this proves the default path is
    unaffected: no crash, same return shape, schema failures still recorded
    in schema_errors (just not individually diagnosed).
    """
    responses = [_ok_critic_json(), "not json at all", _ok_critic_json()]
    gateway = LLMGateway(_SequencedFakeProvider(responses))

    critics, schema_errors = run_judge_gates(
        gateway,
        _budget(),
        "claude-haiku-4-5-20251001",
        "do the thing",
        "print('hi')",
        run_id=1,
        task_id="task-1",
        conn=None,
    )

    assert len(critics) == 2
    assert any(e.startswith("judge:security:") for e in schema_errors)


def test_pipeline_run_verification_forwards_on_schema_failure_unchanged(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        pipeline, "run_automated_gates", lambda workspace: [VerificationResult("ruff", True, "ok")]
    )
    monkeypatch.setattr(pipeline, "automated_defects", lambda results: [])
    received = {}

    def fake_run_judge_gates(gateway, budget, model, task, code, **kwargs):
        received["on_schema_failure"] = kwargs.get("on_schema_failure")
        return [], []

    monkeypatch.setattr(pipeline, "run_judge_gates", fake_run_judge_gates)

    def sentinel(lens: str, text: str, errors: list[str]) -> None:
        return None

    pipeline.run_verification(
        tmp_path,
        _gateway(""),
        _budget(),
        "fake-model",
        "task",
        run_id=1,
        task_id="task-1",
        conn=None,
        on_schema_failure=sentinel,
    )

    assert received["on_schema_failure"] is sentinel


def test_verdict_merge_fails_when_any_blocking_defect_present() -> None:
    critics = [
        {"defects": [], "verdict": "OK"},
        {
            "defects": [
                {"id": "S1", "category": "SECURITY", "severity": "CRITICAL", "location": "x", "fix": "y"}
            ],
            "verdict": "FAIL",
        },
    ]
    merged = verdict.merge(critics, [])
    assert merged["verdict"] == "FAIL"
    assert len(merged["defects"]) == 1


def test_verdict_gate_fails_closed_on_schema_errors() -> None:
    merged = {"defects": [], "verdict": "OK"}
    assert verdict.gate(merged, automated_passed=True, schema_errors=["bad json"]) == "UNVERIFIED"


def test_verdict_gate_fails_when_automated_gates_failed() -> None:
    merged = {"defects": [], "verdict": "OK"}
    assert verdict.gate(merged, automated_passed=False, schema_errors=[]) == "UNVERIFIED"


def test_verdict_gate_passes_when_everything_clean() -> None:
    merged = {"defects": [], "verdict": "OK"}
    assert verdict.gate(merged, automated_passed=True, schema_errors=[]) == "OK"


def test_pipeline_run_verification_fails_when_judges_report_blocking_defects(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        pipeline, "run_automated_gates", lambda workspace: [VerificationResult("ruff", True, "ok")]
    )
    monkeypatch.setattr(pipeline, "automated_defects", lambda results: [])
    monkeypatch.setattr(
        pipeline,
        "run_judge_gates",
        lambda gateway, budget, model, task, code, **kwargs: (
            [
                {"defects": [], "verdict": "OK"},
                {
                    "defects": [
                        {
                            "id": "C1",
                            "category": "CORRECTNESS",
                            "severity": "HIGH",
                            "location": "solution.py:1",
                            "fix": "fix the bug",
                        }
                    ],
                    "verdict": "FAIL",
                },
                {"defects": [], "verdict": "OK"},
            ],
            [],
        ),
    )

    status, merged, automated_results = pipeline.run_verification(
        tmp_path,
        _gateway(""),
        _budget(),
        "fake-model",
        "task",
        run_id=1,
        task_id="task-1",
        conn=None,
    )

    assert status == "UNVERIFIED"
    assert len(merged["defects"]) == 1
    assert len(automated_results) == 1


def test_build_retry_feedback_includes_defect_fix_text() -> None:
    merged = {
        "defects": [
            {
                "id": "C1",
                "category": "CORRECTNESS",
                "severity": "HIGH",
                "location": "solution.py:3",
                "fix": "handle the empty-string case",
            }
        ],
        "verdict": "FAIL",
    }
    feedback = pipeline.build_retry_feedback(merged)
    assert "handle the empty-string case" in feedback
    assert "solution.py:3" in feedback


def test_build_retry_feedback_empty_when_no_defects() -> None:
    assert pipeline.build_retry_feedback({"defects": [], "verdict": "OK"}) == ""
