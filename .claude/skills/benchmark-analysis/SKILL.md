---
name: benchmark-analysis
description: Analyzes engine-review-benchmark results stored in .engine/state.db — compares eval runs, computes per-case verdict stability and variance, breaks down false_pass / false_unverified, inspects schema failures, and traces defect severity distributions per lens. Use whenever the user asks about benchmark results, run comparisons, accuracy changes, judge stability, noise floors, or what a run actually measured.
---

# Benchmark Analysis

Read and interpret `engine-review-benchmark` results from `.engine/state.db`.

Scope note: this skill is about the *benchmark's* data. It has nothing to do with
`src/engine/orchestrator/agents/*.md`, which are the engine's own runtime sub-agent
system prompts (product code). Never confuse the two.

**This skill only reads results that already exist.** It never runs `engine bench`, never
runs the app, and never runs tests — not even to fill a gap in the data. If a question
cannot be answered from the stored runs, say what is missing and what run would answer it;
executing that run is a separate action requiring explicit user approval and the
`git-safety` pre-run gate.

## Rule 1 — never open the real database

`.engine/state.db` is the only copy of the entire measurement history. Both `.engine/`
and `*.db` are in `.gitignore`, so **it is untracked, unbacked-up, and unrecoverable**.
Opening it read-write can create `-wal`/`-shm` sidecars against that file.

Always copy first, then query the copy:

```bash
cp ".engine/state.db" "<scratchpad>/state-copy.db"
```

Every query in this skill runs against the copy. Never `DELETE`, `UPDATE`, `INSERT`,
`VACUUM`, or reset run history — not even on the copy, since a mutated copy silently
produces wrong analysis.

## Rule 2 — know the schema before querying

Read `references/state-db-schema.md` for tables, columns, join keys, and stored value
formats. Two gotchas that cause silent wrong answers:

- `eval_case_results.eval_run_id` refers to `eval_runs.id`. `agent_execution_metrics.run_id`
  refers to the **separate** `runs` table. To attribute LLM-call metrics to an eval run,
  match `agent_execution_metrics.task_id` against the prefix `eval-<eval_run_id>-`.
- `category_accuracy` and `detected_defect_categories` are JSON **strings**, not native
  columns. Parse them; do not string-match them.

## Standard analyses

**Run summary / comparison** — `eval_runs`: `correct_verdicts`, `total_cases`,
`false_pass`, `false_unverified`, `average_latency`, `total_cost`, `git_commit_sha`,
`dataset_version`.

**Per-case stability partition** (the core primitive). Across a set of runs, label every
`eval_case_id` as:
- `always-pass` — `passed = 1` in every run
- `always-fail` — `passed = 0` in every run
- `borderline` — anything else

This matters because the variance surface is small. Measured on the existing
identical-commit clusters: `942f509` (runs 6-9) gave 29 always-pass / 8 always-fail /
**3 borderline**; `c125a47` (runs 10-12) gave 32 / 6 / **2 borderline**. Accuracy is not
40 independent trials — it is ~34 deterministic cases plus a handful of unstable ones.
Always report the partition alongside any accuracy number.

**Variance.** Across identical-configuration runs, report **both** the range and the
standard deviation of the correct-count. Never report a range alone as if it were a
dispersion estimate — the "±3/40" figure in BASELINE.md is a range at n=4, roughly 2.4σ,
not an SD.

Pooled σ ≈ 1.25 cases, from runs 6-9 and 10-12. **That is a v2 measurement.** v3
dispersion has not been measured — runs 18 and 19 are different configurations, so no
identical-configuration v3 cluster exists yet. Whenever σ ≈ 1.25 is applied to v3, label
it provisional and say it is carried over from v2, or the same dataset-boundary rule this
skill enforces everywhere else is being broken silently.

**Lens-level analysis.** `eval_case_lens_results` gives per-lens `call_status`,
`defect_count`, and `schema_valid` for every case. Use it to answer which lens produced a
case's blocking defect, whether a lens ran and found nothing versus never ran, and which
lens a schema failure came from. Also worth checking: rows in `eval_case_defects` where
the model's self-reported `category` disagrees with the `lens` that emitted the defect —
nothing enforces agreement, so that disagreement rate is itself measurable.

**Severity trace for one case.** Join `eval_case_results` to `eval_case_defects` and list
`lens:severity` per run for a single `eval_case_id`. This exposes the real mechanism:
verdicts flip when a single defect crosses the MEDIUM↔HIGH boundary. `edge_case-04-clean`
is the worked example — `security:MEDIUM` yields OK, `security:HIGH` yields UNVERIFIED,
on byte-identical input.

**Defect distribution.** Count `eval_case_defects` grouped by `lens` × `severity` per run.
Use this to see prompt effects directly, independent of whether any verdict moved.

**Schema failures.** Count `eval_case_schema_failures` per run. Runs 13-17 had 1-5; runs
18-19 had zero. Any non-zero value is a regression worth surfacing unprompted, because
`verdict.gate()` fails closed on schema errors and turns them into UNVERIFIED.

**Integrity checks** to run before trusting any run's numbers:
- `eval_case_lens_results.call_status` = `ok` for all 120 rows (40 cases × 3 lenses)
- all `eval_case_automated_gates.passed` = 1 (gates are `ruff`, `mypy`, `pytest`)
- zero rows with `eval_case_results.error IS NOT NULL`

## Interpretation guardrails

- **Exclude any run with ≥1 error row.** `_aggregate()` in `src/engine/eval/runner.py`
  counts `correct_verdicts` over non-error rows but reports against
  `total_cases = len(results) = 40`. A run with k errors therefore under-reports accuracy
  against a denominator of 40 — that is exactly how run 1 recorded 0/40. Such a run is
  excluded and re-run, never averaged in.
- **Never compare across dataset-version boundaries** without saying so explicitly.
  v1 = runs 1-3, v2 = runs 4-17, v3 = runs 18-19.
- **`category_accuracy` changed meaning at commit `068c48b` (run 15).** Values before and
  after are not directly comparable.
- **Runs 18 and 19 are not the same configuration.** Commit `8359246` rewrote `quality-01`
  and `quality-03` in `dataset.py`. Any 18-vs-19 delta conflates a dataset edit with noise.
- **A single-run delta below ~2 cases is not a finding.** Say so rather than narrating it
  as a change.
- When a change was genuinely verified, it was verified by a targeted observation, not by
  the accuracy column — e.g. run 14's parser fix resolving `quality-02-broken × correctness`
  after 7 failures in 8 prior runs. Look for that kind of evidence and report it.

## Output

State the runs used, the dataset version, the integrity-check result, and whether any
delta clears the noise floor. If the data cannot answer the question asked, say that
instead of producing a number with implied precision it does not have.
