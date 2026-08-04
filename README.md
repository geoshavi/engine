# engine

AI agent orchestration engine: an orchestrator agent spawns coding sub-agents,
then runs their output through a multi-layer verification pipeline (automated
gates + independent LLM-judge review) before accepting it.

## Status

MVP: single provider (Anthropic), sequential single sub-agent, bounded retry
loop, automated gates (ruff/mypy/pytest) + 3-lens LLM-judge review, SQLite run
history. Multi-provider routing, parallel sub-agents, and experiment-based
model selection are stubbed out for later milestones (see `routing/`).

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
