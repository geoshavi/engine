"""HTTP entrypoint for reviewing code a developer already wrote (as opposed to
`orchestrator.engine.run_task`, which generates new code). Skips the coder
sub-agent entirely and runs the same deterministic verification pipeline
(automated gates + orchestrated multi-lens LLM judges) directly against the
submitted files. Built for n8n (or any HTTP-capable automation) to call.
"""

import json
import shutil
import uuid
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine.config import Config, load_config
from engine.orchestrator.agents.common import write_files
from engine.providers.base import Provider
from engine.providers.registry import DEFAULT_MODELS, build_provider
from engine.verification.pipeline import run_verification

REVIEW_ROOT = Path(".engine/review")


def _unsafe_path_result(skipped_paths: list[str]) -> dict:
    return {
        "status": "UNVERIFIED",
        "defects": [
            {
                "id": f"PATH{i}",
                "category": "SECURITY",
                "severity": "CRITICAL",
                "location": path,
                "fix": "Submit only relative paths. '..' traversal and absolute paths are not allowed.",
            }
            for i, path in enumerate(skipped_paths)
        ],
        "automated_results": [],
    }


def _no_code_result() -> dict:
    return {
        "status": "UNVERIFIED",
        "defects": [
            {
                "id": "NOCODE0",
                "category": "CORRECTNESS",
                "severity": "CRITICAL",
                "location": "submission",
                "fix": "No files were submitted to review.",
            }
        ],
        "automated_results": [],
    }


def review_code(task: str, files: dict[str, str], provider: Provider, judge_model: str) -> dict:
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    workspace = REVIEW_ROOT / uuid.uuid4().hex
    workspace.mkdir(parents=True)
    try:
        skipped = write_files(workspace, files)
        if skipped:
            return _unsafe_path_result(skipped)
        if not any(workspace.rglob("*.py")):
            return _no_code_result()

        status, merged, automated_results = run_verification(workspace, provider, judge_model, task)
        return {
            "status": status,
            "defects": merged.get("defects", []),
            "automated_results": [
                {"gate": r.gate_name, "passed": r.passed, "detail": r.detail} for r in automated_results
            ],
        }
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _make_handler(
    review: Callable[[str, dict[str, str]], dict],
) -> type[BaseHTTPRequestHandler]:
    class ReviewHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/review":
                self._send_json(404, {"error": "not found"})
                return

            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid JSON body"})
                return

            task = body.get("task")
            files = body.get("files")
            if not isinstance(task, str) or not task.strip():
                self._send_json(400, {"error": "'task' (string) is required"})
                return
            if not isinstance(files, dict) or not files:
                self._send_json(400, {"error": "'files' (non-empty object of path -> content) is required"})
                return
            if not all(isinstance(v, str) for v in files.values()):
                self._send_json(400, {"error": "'files' values must all be strings"})
                return

            try:
                result = review(task, files)
            except Exception as exc:  # noqa: BLE001 - a provider/network failure must not drop the connection
                self._send_json(502, {"error": f"review failed: {type(exc).__name__}: {exc}"})
                return
            self._send_json(200, result)

        def _send_json(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format_: str, *args: object) -> None:  # quiet stdlib access logging
            pass

    return ReviewHandler


def serve(config: Config | None = None, port: int = 8000, provider_name: str = "anthropic") -> None:
    config = config or load_config()
    provider = build_provider(provider_name, config)
    judge_model = DEFAULT_MODELS[provider_name]["judge"]

    handler = _make_handler(lambda task, files: review_code(task, files, provider, judge_model))
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    server.serve_forever()
