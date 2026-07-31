from pathlib import Path

from engine.providers.base import GenerationResult, Message
from engine.state.models import VerificationResult
from engine.verification import pipeline
from engine.verification.automated import run_automated_gates
from engine.verification.judge import _parse_verdict, run_judge_gates


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


def test_parse_verdict() -> None:
    assert _parse_verdict("VERDICT: PASS\nlooks good") is True
    assert _parse_verdict("VERDICT: FAIL\nbug on line 3") is False
    assert _parse_verdict("") is False


class _FakeProvider:
    name = "fake"

    def __init__(self, verdict_text: str) -> None:
        self._verdict_text = verdict_text

    def generate(
        self,
        messages: list[Message],
        model: str,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> GenerationResult:
        return GenerationResult(
            text=self._verdict_text, model=model, provider=self.name, input_tokens=1, output_tokens=1
        )


def test_run_judge_gates_returns_one_result_per_lens() -> None:
    provider = _FakeProvider("VERDICT: PASS\nfine")
    results = run_judge_gates(provider, "fake-model", "do the thing", "print('hi')")
    assert len(results) == 3
    assert all(r.passed for r in results)
    assert {r.gate_name for r in results} == {"judge:correctness", "judge:security", "judge:style"}


def test_pipeline_majority_vote_fails_overall_when_two_lenses_fail(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        pipeline, "run_automated_gates", lambda workspace: [VerificationResult("ruff", True, "ok")]
    )
    monkeypatch.setattr(
        pipeline,
        "run_judge_gates",
        lambda provider, model, task, code: [
            VerificationResult("judge:correctness", False, "bug"),
            VerificationResult("judge:security", False, "unsafe"),
            VerificationResult("judge:style", True, "fine"),
        ],
    )

    passed, results = pipeline.run_verification(tmp_path, _FakeProvider(""), "fake-model", "task")

    assert passed is False
    assert len(results) == 4


def test_build_retry_feedback_lists_only_failures() -> None:
    results = [
        VerificationResult("ruff", True, "ok"),
        VerificationResult("mypy", False, "type error on line 4"),
    ]
    feedback = pipeline.build_retry_feedback(results)
    assert "mypy" in feedback
    assert "type error on line 4" in feedback
    assert "ruff" not in feedback
