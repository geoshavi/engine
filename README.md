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
