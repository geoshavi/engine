---
name: baseline-evidence
description: Governs how BASELINE.md is read and extended for engine-review-benchmark — treats it as an append-mostly evidence log, separates measured results from interpretation, enforces dataset-version comparability boundaries, forbids treating a single noisy run as proof, and specifies the reproducibility fields every recorded run must carry. Use when reading BASELINE.md, citing a past result, recording a new run or experiment, or making a claim about what the benchmark has shown.
---

# Baseline Evidence

`BASELINE.md` is the project's evidence log. It is the reason past runs still mean
something. Treat it accordingly.

## Append-mostly

New runs are appended. Existing rows are historical record.

Correcting an existing row is allowed only when it is factually wrong about what happened,
and the correction must say **what was wrong and why** — never a silent edit. Never delete
a row. Never rewrite a past interpretation to match a newer belief; add the newer belief
and note that it supersedes the old one, as the Phase 2B note does.

Editing `BASELINE.md` requires explicit approval like any other tracked file
(see `git-safety`).

## Measured vs. interpreted

**The table is measurement.** Run number, date, commit SHA, dataset version, accuracy,
`false_pass`, `false_unverified`, cost — all read directly from `.engine/state.db`.

**The Notes section is interpretation.** Mechanisms, hypotheses, conclusions.

Never promote an interpretation into the table. Never state an interpretation without
naming the runs that support it and how many there were. When citing BASELINE.md, make
clear which of the two you are quoting.

The "what changed" column is a description of the *intervention*, not evidence of its
*effect*. Reading it as though it were an effect is the specific error the log is built to
prevent.

## Dataset-version boundaries are hard walls

- **v1** — runs 1-3
- **v2** — runs 4-17
- **v3** — runs 18-19

Scores are not comparable across these boundaries. v3 in particular removed
non-discriminating defects, so part of v1/v2's `false_unverified` count was structural
rather than judge error — a v3 accuracy change cannot be read as a pure judge-behavior
delta relative to earlier runs.

Two further boundaries inside v2:

- `category_accuracy` changed meaning at commit `068c48b` (run 15). Values before and
  after are not directly comparable.
- Runs 18 and 19 are **different configurations**: commit `8359246` rewrote `quality-01`
  and `quality-03` in `dataset.py`. Any 18-vs-19 delta conflates a dataset edit with noise.

State the boundary explicitly whenever a comparison approaches one.

## Never treat a single run as proof

The noise floor is real and measured: identical-commit runs 6-9 span 29-32/40, pooled
σ ≈ 1.25 cases. Most single-run deltas in the table fall inside it and demonstrate nothing
on their own.

That figure comes from **v2** clusters. No identical-configuration v3 cluster exists yet,
so applying it to v3 crosses the same dataset boundary this skill enforces above — allowed
as a provisional stand-in, but only when labelled as carried over from v2.

When reporting any delta, state three things together: **the number of runs, the noise
floor, and whether the delta clears it.** If it does not clear it, say so plainly rather
than narrating the direction of the change.

Where a change genuinely *was* verified, it was verified by a targeted observation, not by
the accuracy column:

- Run 14's parser fix resolved `quality-02-broken × correctness` after 7 failures in
  8 prior runs.
- Run 16's placement experiment resolved 4 of 5 known verdict/severity schema failures.

Look for that shape of evidence — a specific, repeated, mechanism-level observation — and
prefer it over aggregate movement.

## Recording a new run or experiment

Every appended row carries: **run number, date, commit SHA, dataset version, accuracy
(correct/total), `false_pass`, `false_unverified`, total cost, and what changed.**

For a multi-run experiment additionally record: **N, the dispersion estimate (SD, not just
range), the per-case stability partition, and the pre-registered decision rule** — the rule
as it was written *before* the runs, unedited.

Before appending, verify the run's integrity against the stored data — via a scratchpad
copy of `.engine/state.db`, never by opening the live file (see `benchmark-analysis`).
Two checks, with different consequences:

- **Error rows are disqualifying.** A run with ≥1 `eval_case_results.error` is recorded as
  excluded, with the reason, and never averaged into a result. Its accuracy figure is
  understated by construction.
- **Schema failures are recorded, not disqualifying.** Runs 13-17 each had 1-5 and are
  legitimately in the table. Note the count in the row and flag any non-zero value as a
  regression signal, but do not exclude the run on that basis alone.

If a run's SHA differs from a comparison run's SHA but the code is identical, say so and
give the command that proves it, e.g. `git diff <a> <b> -- src/` returning empty.
