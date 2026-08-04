import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from engine.api import _make_handler, review_code
from engine.state.models import VerificationResult


class _FakeProvider:
    name = "fake"

    def generate(self, *args, **kwargs):  # pragma: no cover - not expected to be called directly
        raise AssertionError("review_code must go through run_verification, not call the provider itself")


def test_review_code_refuses_unsafe_paths() -> None:
    result = review_code(
        "add two numbers", {"../evil.py": "x = 1\n"}, _FakeProvider(), "judge-model"
    )

    assert result["status"] == "UNVERIFIED"
    assert result["defects"][0]["severity"] == "CRITICAL"
    assert result["defects"][0]["category"] == "SECURITY"


def test_review_code_rejects_empty_submission() -> None:
    result = review_code("add two numbers", {"notes.txt": "not python"}, _FakeProvider(), "judge-model")

    assert result["status"] == "UNVERIFIED"
    assert result["defects"][0]["id"] == "NOCODE0"


def test_review_code_runs_verification_pipeline_on_submitted_files(monkeypatch) -> None:
    captured_workspace = {}

    def fake_run_verification(workspace, provider, judge_model, task_text):
        captured_workspace["files"] = sorted(p.name for p in workspace.rglob("*.py"))
        merged = {"defects": [], "verdict": "OK"}
        return "OK", merged, [VerificationResult("ruff", True, "ok")]

    import engine.api as api_module

    monkeypatch.setattr(api_module, "run_verification", fake_run_verification)

    result = review_code(
        "add two numbers", {"add.py": "def add(a, b):\n    return a + b\n"}, _FakeProvider(), "judge-model"
    )

    assert result["status"] == "OK"
    assert result["defects"] == []
    assert result["automated_results"] == [{"gate": "ruff", "passed": True, "detail": "ok"}]
    assert captured_workspace["files"] == ["add.py"]


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
