from pathlib import Path

from engine.config import Config
from engine.orchestrator import engine as engine_module
from engine.orchestrator.planner import plan_subtasks
from engine.orchestrator.subagent import parse_files, write_files
from engine.providers.base import GenerationResult, Message
from engine.state.models import VerificationResult


def test_plan_subtasks_is_single_item_for_mvp() -> None:
    assert plan_subtasks("do the thing") == ["do the thing"]


def test_parse_files_handles_multiple_files() -> None:
    response = (
        "FILE: solution.py\n```\ndef add(a, b):\n    return a + b\n```\n\n"
        "FILE: test_solution.py\n```\nfrom solution import add\n```\n"
    )
    files = parse_files(response)
    assert set(files) == {"solution.py", "test_solution.py"}
    assert "def add" in files["solution.py"]


def test_write_files_creates_nested_directories(tmp_path: Path) -> None:
    write_files(tmp_path, {"pkg/mod.py": "x = 1\n"})
    assert (tmp_path / "pkg" / "mod.py").read_text() == "x = 1\n"


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
    ) -> GenerationResult:
        return GenerationResult(
            text=self._response_text, model=model, provider=self.name, input_tokens=1, output_tokens=1
        )


def _config(tmp_path: Path) -> Config:
    return Config(
        anthropic_api_key="fake",
        openai_api_key=None,
        google_api_key=None,
        max_retries=3,
        db_path=tmp_path / "state.db",
    )


def test_run_task_stops_at_max_retries_when_never_passing(monkeypatch, tmp_path: Path) -> None:
    attempts = []

    def fake_run_verification(workspace, provider, judge_model, task_text):
        attempts.append(1)
        merged = {
            "defects": [
                {"id": "C1", "category": "CORRECTNESS", "severity": "HIGH", "location": "x", "fix": "y"}
            ],
            "verdict": "FAIL",
        }
        return "UNVERIFIED", merged, [VerificationResult("ruff", False, "still broken")]

    monkeypatch.setattr(engine_module, "run_verification", fake_run_verification)

    result = engine_module.run_task(
        "do the thing",
        tmp_path / "workspace",
        _FakeProvider("FILE: solution.py\n```\nx = 1\n```\n"),
        _config(tmp_path),
    )

    assert result.passed is False
    assert result.attempts == 3
    assert len(attempts) == 3


def test_run_task_stops_early_once_verification_passes(monkeypatch, tmp_path: Path) -> None:
    call_count = {"n": 0}

    def fake_run_verification(workspace, provider, judge_model, task_text):
        call_count["n"] += 1
        merged = {"defects": [], "verdict": "OK"}
        return "OK", merged, [VerificationResult("ruff", True, "ok")]

    monkeypatch.setattr(engine_module, "run_verification", fake_run_verification)

    result = engine_module.run_task(
        "do the thing",
        tmp_path / "workspace",
        _FakeProvider("FILE: solution.py\n```\nx = 1\n```\n"),
        _config(tmp_path),
    )

    assert result.passed is True
    assert result.attempts == 1
    assert call_count["n"] == 1
