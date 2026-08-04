import json
import threading
import urllib.error
import urllib.request
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path

from engine.api import _make_handler, _review_budget, review_code
from engine.config import Config
from engine.runtime.budget import BudgetController
from engine.runtime.gateway import LLMGateway
from engine.state.models import VerificationResult


class _FakeProvider:
    name = "fake"

    def generate(self, *args, **kwargs):  # pragma: no cover - not expected to be called directly
        raise AssertionError("review_code must go through run_verification, not call the provider itself")


def _gateway() -> LLMGateway:
    return LLMGateway(_FakeProvider())


def _budget() -> BudgetController:
    return BudgetController(max_tokens=100_000, planned_budget=Decimal("1.00"))


def test_review_budget_uses_the_review_specific_lower_ceiling_not_the_generation_run_default() -> None:
    config = Config(
        anthropic_api_key="key",
        openai_api_key=None,
        google_api_key=None,
        max_retries=3,
        db_path=Path("unused"),
        max_tokens=100_000,
        timeout_seconds=600.0,
        max_agents=10,
        planned_budget=Decimal("1.00"),
        review_max_tokens=10_000,
        review_planned_budget=Decimal("0.10"),
    )

    budget = _review_budget(config)

    assert budget.max_tokens == config.review_max_tokens
    assert budget.planned_budget == config.review_planned_budget
    assert budget.max_tokens < config.max_tokens
    assert budget.planned_budget < config.planned_budget


def test_review_code_refuses_unsafe_paths() -> None:
    result = review_code(
        "add two numbers", {"../evil.py": "x = 1\n"}, _gateway(), _budget(), "judge-model"
    )

    assert result["status"] == "UNVERIFIED"
    assert result["defects"][0]["severity"] == "CRITICAL"
    assert result["defects"][0]["category"] == "SECURITY"


def test_review_code_rejects_empty_submission() -> None:
    result = review_code(
        "add two numbers", {"notes.txt": "not python"}, _gateway(), _budget(), "judge-model"
    )

    assert result["status"] == "UNVERIFIED"
    assert result["defects"][0]["id"] == "NOCODE0"


def test_review_code_runs_verification_pipeline_on_submitted_files(monkeypatch) -> None:
    captured_workspace = {}
    captured_context = {}

    def fake_run_verification(workspace, gateway, budget, judge_model, task_text, **kwargs):
        captured_workspace["files"] = sorted(p.name for p in workspace.rglob("*.py"))
        captured_context.update(kwargs)
        merged = {"defects": [], "verdict": "OK"}
        return "OK", merged, [VerificationResult("ruff", True, "ok")]

    import engine.api as api_module

    monkeypatch.setattr(api_module, "run_verification", fake_run_verification)

    result = review_code(
        "add two numbers",
        {"add.py": "def add(a, b):\n    return a + b\n"},
        _gateway(),
        _budget(),
        "judge-model",
    )

    assert result["status"] == "OK"
    assert result["defects"] == []
    assert result["automated_results"] == [{"gate": "ruff", "passed": True, "detail": "ok"}]
    assert captured_workspace["files"] == ["add.py"]
    # Stateless by design: no run_id, and conn is None so the Gateway skips
    # writing metrics for review requests -- see api.py's module docstring.
    assert captured_context["run_id"] is None
    assert captured_context["conn"] is None
    assert captured_context["task_id"]


def _run_server(review):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(review))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _post(port: int, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/review",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_server_returns_error_response_instead_of_dropping_connection_on_provider_failure() -> None:
    def exploding_review(task, files):
        raise RuntimeError("credit balance is too low")

    server, thread = _run_server(exploding_review)
    try:
        port = server.server_address[1]
        status, body = _post(port, {"task": "do it", "files": {"a.py": "x = 1\n"}})
        assert status == 502
        assert "credit balance is too low" in body["error"]
    finally:
        server.shutdown()
        thread.join()


def test_server_rejects_missing_fields() -> None:
    server, thread = _run_server(lambda task, files: {"status": "OK"})
    try:
        port = server.server_address[1]
        status, body = _post(port, {"task": "do it"})
        assert status == 400
        assert "files" in body["error"]
    finally:
        server.shutdown()
        thread.join()
