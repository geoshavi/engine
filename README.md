<img width="1536" height="1024" alt="Codex Image 18 Aug 2026, 01_52_58" src="https://github.com/user-attachments/assets/8828b75a-f555-48cd-bfa3-5f5f38dc1c08" />


# engine

AI agent orchestration engine: an orchestrator analyzes a task, builds a
validated execution plan, dispatches specialized sub-agents under enforced
token/spend limits, then runs their output through a multi-layer verification
pipeline (automated gates + independent LLM-judge review) before accepting it.

## Status

Working runtime: single provider (Anthropic), sequential multi-agent execution
(coding / research / testing / refactoring), bounded retry loop, automated gates
(ruff/mypy/pytest) + 3-lens LLM-judge review, deterministic verdict, SQLite run
history and per-call metrics. 77 tests.

Every LLM call in the codebase — agents and judge lenses alike — routes through
a single gateway (`runtime/gateway.py`) that enforces a token/spend budget
before the call and records usage after it. Limits are enforced at runtime, not
merely declared: exceeding them raises `BudgetExceededError` and terminates the
run rather than retrying.

Multi-provider routing, parallel sub-agents, merge control, and long-term memory
are planned for later milestones.

### Verification architecture

No LLM ever decides pass/fail directly. Each judge lens (`verification/judge.py`)
must return structured defects (`{id, category, severity, location, fix}`) as
JSON, validated against a fixed schema (`verification/schema.py`). A pure,
model-free Python function — `verification/verdict.py`'s `merge`/`gate` — is
the only code path allowed to turn automated gate results + those defects into
an `OK`/`UNVERIFIED` verdict: any CRITICAL/HIGH defect blocks, any malformed
judge response blocks (fails closed), and any failed automated gate blocks.
This separation (deterministic script owns the verdict, LLMs only supply
evidence) follows the pattern used by
[kimi-atlas](https://github.com/null0xxx/kimi-atlas)'s verification harness.

### Runtime control

Task analysis is separated from execution. `orchestrator/task_analyzer.py`
classifies the request; `orchestrator/execution_plan.py` produces a validated
plan (steps, dependencies, token/spend/agent limits); `orchestrator/manager.py`
executes it. Agents never talk to each other directly — all coordination goes
through the orchestrator.

Cost is tracked in `Decimal` (never float) against a dated price table, and
fails closed on an unknown model rather than silently costing nothing. Per-call
metrics — model, input/output/cache tokens, latency, spend, status — are written
to SQLite after every call, including failures.

Three architecture tests enforce the invariants that make the above true:
provider SDKs may only be imported inside `runtime/` and `providers/`; only
`runtime/gateway.py` may reach into `providers/`; and `providers/` may not
import `runtime/`. These fail with the offending file and the rule it broke,
so the gateway cannot be quietly bypassed by future code.

## Setup

```
python -m venv .venv
.venv/Scripts/activate     # Windows
pip install -e ".[dev]"
cp .env.example .env       # fill in ANTHROPIC_API_KEY
```

## Usage

```
engine run "write a function that checks if a string is a palindrome, with a unit test"
```

Generated code lands in `.engine/workspace/`, a run report in `.engine/report.md`,
and full run/verification history in `.engine/state.db`.

## Tests

```
pytest
```

## n8n (local workflow automation)

Runs via Docker Compose alongside `engine-api`, a small HTTP wrapper around the
same verification pipeline `engine run` uses — the difference is `engine-api`
reviews code you already wrote instead of generating new code first.

```
docker compose up -d      # start n8n (:5678) + engine-api (:8000)
docker compose down       # stop (data persists in the n8n_data / engine_review_data volumes)
```

Uses `N8N_ENCRYPTION_KEY` from `.env` (generate with `openssl rand -hex 32`);
changing it after workflows/credentials exist makes stored credentials
unreadable.

### Code-review webhook

`engine-api`'s only endpoint:

```
POST /review
{
  "task": "what this code is supposed to do",
  "files": {"solution.py": "...", "test_solution.py": "..."}
}
```

Returns `{"status": "OK" | "UNVERIFIED", "defects": [...], "automated_results": [...]}` —
same deterministic verdict, same orchestrated correctness/security/code-quality
judge lenses as `engine run`, just skipping code generation.

Import `n8n-workflows/code-review.json` into n8n (menu → *Import from File*) to get
a ready `Webhook -> Call Engine Review -> Respond to Webhook` workflow. It POSTs
whatever the webhook receives straight to `http://engine-api:8000/review` (reachable
by service name on the compose network) and echoes the JSON verdict back as the
HTTP response — call it with:

```
curl -X POST http://localhost:5678/webhook/review \
  -H "Content-Type: application/json" \
  -d '{"task": "add two numbers", "files": {"add.py": "def add(a, b):\n    return a - b\n"}}'
```

**Known limitation:** the automated gates run `pytest` on submitted files directly
in the `engine-api` container — there is no sandboxing beyond the container
boundary itself. Don't expose this webhook to the public internet without adding
auth and/or real sandboxing in front of it.
