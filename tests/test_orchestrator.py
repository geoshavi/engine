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
    skipped = write_files(tmp_path, {"pkg/mod.py": "x = 1\n"})
    assert (tmp_path / "pkg" / "mod.py").read_text() == "x = 1\n"
    assert skipped == []


def test_write_files_refuses_parent_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"

    skipped = write_files(workspace, {"../secret.txt": "pwned"})

    assert skipped == ["../secret.txt"]
    assert not secret.exists()


def test_write_files_refuses_absolute_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.py"

    skipped = write_files(workspace, {str(outside): "x = 1\n"})

    assert skipped == [str(outside)]
    assert not outside.exists()


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


def test_run_task_resets_workspace_between_attempts(monkeypatch, tmp_path: Path) -> None:
    responses = [
        "FILE: a.py\n```\nx = 1\n```\n",
        "FILE: b.py\n```\ny = 2\n```\n",
    ]

    class _SequencedProvider:
        name = "fake"

        def __init__(self) -> None:
            self.calls = 0

        def generate(
            self,
            messages: list[Message],
            model: str,
            system: str | None = None,
            max_tokens: int = 4096,
            temperature: float = 0.0,
        ) -> GenerationResult:
            text = responses[self.calls]
            self.calls += 1
            return GenerationResult(text=text, model=model, provider=self.name, input_tokens=1, output_tokens=1)

    workspace_snapshots: list[list[str]] = []

    def fake_run_verification(workspace, provider, judge_model, task_text):
        workspace_snapshots.append(sorted(p.name for p in workspace.iterdir()))
        if len(workspace_snapshots) == 1:
            merged = {
                "defects": [
                    {"id": "C1", "category": "CORRECTNESS", "severity": "HIGH", "location": "x", "fix": "y"}
                ],
                "verdict": "FAIL",
            }
            return "UNVERIFIED", merged, [VerificationResult("ruff", False, "bad")]
        merged = {"defects": [], "verdict": "OK"}
        return "OK", merged, [VerificationResult("ruff", True, "ok")]

    monkeypatch.setattr(engine_module, "run_verification", fake_run_verification)

    result = engine_module.run_task(
        "do the thing", tmp_path / "workspace", _SequencedProvider(), _config(tmp_path)
    )

    assert workspace_snapshots == [["a.py"], ["b.py"]]
    assert result.passed is True


def test_run_task_treats_unsafe_path_as_deterministic_failure(monkeypatch, tmp_path: Path) -> None:
    called = {"n": 0}

    def fake_run_verification(*args, **kwargs):
        called["n"] += 1
        return "OK", {"defects": [], "verdict": "OK"}, []

    monkeypatch.setattr(engine_module, "run_verification", fake_run_verification)

    provider = _FakeProvider("FILE: ../evil.py\n```\nx = 1\n```\n")
    result = engine_module.run_task(
        "do the thing", tmp_path / "workspace", provider, _config(tmp_path)
    )

    assert result.passed is False
    assert called["n"] == 0
    defects = result.verification_history[0].merged_critic["defects"]
    assert defects[0]["severity"] == "CRITICAL"
    assert defects[0]["category"] == "SECURITY"
    assert not (tmp_path / "evil.py").exists()


def test_run_task_treats_empty_generation_as_deterministic_failure(monkeypatch, tmp_path: Path) -> None:
    called = {"n": 0}

    def fake_run_verification(*args, **kwargs):
        called["n"] += 1
        return "OK", {"defects": [], "verdict": "OK"}, []

    monkeypatch.setattr(engine_module, "run_verification", fake_run_verification)

    provider = _FakeProvider("sorry, I could not produce any code for this task.")
    result = engine_module.run_task(
        "do the thing", tmp_path / "workspace", provider, _config(tmp_path)
    )

    assert result.passed is False
    assert called["n"] == 0
    defects = result.verification_history[0].merged_critic["defects"]
    assert defects[0]["severity"] == "CRITICAL"
    assert defects[0]["id"] == "NOCODE0"


def test_run_task_survives_provider_exception(monkeypatch, tmp_path: Path) -> None:
    class _ExplodingProvider:
        name = "fake"

        def generate(self, *args, **kwargs):
            raise RuntimeError("connection reset")

    result = engine_module.run_task(
        "do the thing", tmp_path / "workspace", _ExplodingProvider(), _config(tmp_path)
    )

    assert result.passed is False
    assert result.attempts == 3
    defects = result.verification_history[0].merged_critic["defects"]
    assert defects[0]["id"] == "PROVIDER0"
    assert "connection reset" in defects[0]["fix"]


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
