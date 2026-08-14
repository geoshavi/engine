# `.engine/state.db` schema reference

SQLite. Written by `src/engine/state/db.py`. Read-only for analysis — always query a copy.

As of run 19 the file holds 19 eval runs, 760 case results, 1999 defects, 2040 lens
results, 2040 automated-gate rows, 11 schema failures, and 2200 LLM-call metrics.

## Tables used by the eval path

### `eval_runs` — one row per benchmark run
| column | notes |
|---|---|
| `id` | PK. This is the `eval_run_id` referenced everywhere else. |
| `created_at` | timestamp |
| `git_commit_sha` | full SHA of `HEAD` at run time — **not** the working tree (see `git-safety`) |
| `benchmark_name` | `engine-review-benchmark` |
| `benchmark_version` | `v1` |
| `dataset_version` | `v1` / `v2` / `v3` — hard comparability boundary |
| `total_cases` | always 40; `len(results)`, includes error rows |
| `correct_verdicts` | counts **non-error rows only** — see the denominator trap below |
| `false_pass` | expected UNVERIFIED, got OK |
| `false_unverified` | expected OK, got UNVERIFIED |
| `category_accuracy` | **JSON string**, e.g. `{"correctness": 0.9, "security": 0.8, "quality": 0.7, "edge_case": 0.8}` |
| `average_cost`, `total_cost` | Decimal-as-text |
| `average_latency` | ms, integer |

### `eval_case_results` — one row per case per run (40 per run)
| column | notes |
|---|---|
| `id` | PK. Parent key for defects / lens results / gates / schema failures. |
| `eval_run_id` | FK → `eval_runs.id` |
| `eval_case_id` | e.g. `quality-03-broken`, `edge_case-04-clean` |
| `task_id` | `eval-<eval_run_id>-<eval_case_id>` — the join key into `agent_execution_metrics` |
| `expected_verdict` / `actual_verdict` | `OK` \| `UNVERIFIED` |
| `expected_defect_category` | `CORRECTNESS` \| `SECURITY` \| `CODE-QUALITY` \| NULL for clean cases |
| `detected_defect_categories` | **JSON array string**, e.g. `["CORRECTNESS"]` |
| `latency_ms`, `cost` | summed over the case's LLM calls |
| `passed` | 1 iff `error IS NULL` and `actual_verdict = expected_verdict` |
| `error` | NULL on success; `"<ExcType>: <msg>"` if `run_verification()` raised |

### `eval_case_defects` — one row per defect (1999 rows total)
`id`, `eval_case_result_id` (FK), `lens`, `defect_id`, `category`, `severity`,
`location`, `fix`, `created_at`.

- `lens` ∈ `correctness` \| `security` \| `code-quality` — the lens that **actually emitted**
  the defect, tagged in `judge.py`, not the model's self-reported `category`.
- `severity` ∈ `CRITICAL` \| `HIGH` \| `MEDIUM` \| `LOW`. `CRITICAL`/`HIGH` are blocking
  (`rubric.BLOCKING`).
- `category` is the model's own claim and may disagree with `lens`. Nothing enforces
  agreement — that mismatch is itself measurable.

### `eval_case_lens_results` — one row per lens per case, always 3 (2040 rows total)
`id`, `eval_case_result_id` (FK), `lens`, `call_status`, `defect_count`, `schema_valid`,
`error`, `created_at`.

- `call_status` ∈ `ok` \| `error` \| `not_run`. Only `ok` observed to date.
- Rows exist even for lenses that ran and found nothing, so "found nothing" and
  "never got called" stay distinguishable.
- `defect_count` / `schema_valid` are NULL when the merged result was unavailable (a later
  lens's exception discards earlier parsed critics).

### `eval_case_automated_gates` — one row per gate per case (2040 rows total)
`id`, `eval_case_result_id` (FK), `gate_name`, `passed`, `detail`, `created_at`.

`gate_name` ∈ `ruff` \| `mypy` \| `pytest`. Dataset snippets are authored lint- and
type-clean and ship no `test_*.py`, so all three should pass on every case. Any failure
means environment contamination, not judge behavior.

### `eval_case_schema_failures` — one row per malformed judge response (11 rows total)
`id`, `eval_case_result_id` (FK), `lens`, `error_detail`, `raw_response`, `created_at`.

Populated via callback as each lens fails, so failures from earlier lenses survive a later
lens's exception. Distribution to date: run 13 → 2, run 14 → 2, run 15 → 5, run 16 → 1,
run 17 → 1, runs 18-19 → 0.

### `runs` — one row per CLI invocation
`id`, `task_text` (`eval:engine-review-benchmark`), `provider` (`anthropic`),
`model` (`claude-haiku-4-5-20251001`), `status`, `attempts`, `created_at`, `finished_at`.

### `agent_execution_metrics` — one row per LLM call (2200 rows total)
`id`, `run_id` (→ **`runs.id`**), `task_id`, `agent_name`, `model`, `input_tokens`,
`output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `latency_ms`,
`actual_spend`, `status`, `error`, `created_at`.

`agent_name` for judge calls is `judge:<lens>`. Written for failures too.

## Unused tables

`agent_executions`, `defects`, `verification_results` are all **0 rows** — they belong to
the `engine run` generation flow, not the eval path. Ignore them in benchmark analysis.

## Join map

```
eval_runs.id
  └─→ eval_case_results.eval_run_id
        └─→ eval_case_defects.eval_case_result_id
        └─→ eval_case_lens_results.eval_case_result_id
        └─→ eval_case_automated_gates.eval_case_result_id
        └─→ eval_case_schema_failures.eval_case_result_id

runs.id ─→ agent_execution_metrics.run_id
           agent_execution_metrics.task_id LIKE 'eval-<eval_run_id>-%'
```

**`runs.id` and `eval_runs.id` are different sequences.** They happen to be numerically
aligned through run 19 because each benchmark creates exactly one of each, but that is
coincidence, not a constraint. Join metrics to an eval run through the `task_id` prefix,
never by assuming the ids match.

## The denominator trap

`_aggregate()` (`src/engine/eval/runner.py`) sets `total_cases = len(results)` — all 40,
error rows included — while `correct_verdicts` counts only rows where `error IS NULL`.
A run with k errored cases therefore reports `correct/40` with a suppressed numerator.
Run 1 is the visible instance: 40 error rows, recorded as 0/40.

Before using a run in any variance or comparison analysis, confirm:

```sql
SELECT COUNT(*) FROM eval_case_results
WHERE eval_run_id = ? AND error IS NOT NULL;   -- must be 0
```
