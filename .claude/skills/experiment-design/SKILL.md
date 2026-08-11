---
name: experiment-design
description: Designs pre-registered experiments for engine-review-benchmark — formulates a falsifiable hypothesis, names target and control cases, freezes variables, fixes primary/secondary/guardrail metrics, computes sample size against the measured noise floor, and locks acceptance/rejection criteria before any run. Use when planning a benchmark experiment, a judge or prompt change, a dataset change, or a variance measurement, and when deciding whether an observed result counts as movement.
---

# Experiment Design

Every change to this benchmark is an experiment. Design it before running it, and write
the decision rule down before the result exists.

**This skill produces a plan and nothing else.** Designing or reviewing an experiment
never runs `engine bench`, never runs tests, never runs the app, and never implements the
change being designed — writing a prompt edit into `src/engine/verification/judge.py` is a
separate step needing its own explicit approval (see `git-safety`). Finish the plan, hand
it over, stop. Execution begins only when the user says so.

Scope note: the skills in `.claude/skills/` are instructions for this assistant. They are
unrelated to `src/engine/orchestrator/agents/*.md`, which are the engine's own runtime
sub-agent prompts and are product code.

## Pre-registration template

All eight fields are filled **before the first run**. An experiment missing any field is
not ready to run.

1. **Hypothesis** — one falsifiable sentence. "Adding an explicit structural-decomposition
   inclusion criterion to the code-quality lens moves that lens's finding on
   `quality-01-broken` from MEDIUM to HIGH."
2. **Target cases** — named `eval_case_id`s, each with its *currently measured* baseline
   rate, written as `passes/runs` at the current configuration (illustrative format only:
   `quality-01-broken: 0/8`; the real denominator is however many identical-configuration
   runs actually exist). "Currently failing" is not a baseline; a rate is. If no such rate
   exists yet, measuring it is the experiment.
3. **Control / guardrail cases** — which cases must *not* move, and the threshold at which
   their movement rejects the change outright.
4. **Frozen variables** — explicit file list and config values (see `git-safety` for the
   measured-path list).
5. **Metrics** — primary, secondary, guardrail, named separately and in advance.
6. **Sample size** — N per arm, plus the minimum detectable effect that N buys.
7. **Acceptance / rejection / inconclusive criteria** — all three, stated numerically.
8. **What a negative result would look like** — if you cannot describe it, the hypothesis
   is not falsifiable yet.

## Choosing metrics

**Primary: per-case blocking rate on the named target cases.** This is far more sensitive
than aggregate accuracy, because the variance surface is only 2-3 cases wide while
accuracy averages over 40.

**Secondary: aggregate accuracy** (`correct_verdicts / 40`). Report it; never let it decide.

**Guardrail: `false_unverified` across the 20 clean cases.** Any change that adds an
inclusion criterion risks over-triggering on clean code. Pre-register a rejection
threshold here.

**Also record** the per-lens severity distribution. A prompt change manipulates severity
directly; verdicts are only a thresholded, low-resolution view of it. Measuring severity
mass shifting MEDIUM→HIGH can confirm a mechanism even when no verdict moves.

## Sample size

Pooled σ ≈ **1.25 cases** (identical-commit clusters, runs 6-9 and 10-12).
Cost is ~$0.124 and ~3.5 min per 40-case run, so N is limited by patience, not budget.

**σ ≈ 1.25 is a v2 figure.** No identical-configuration v3 cluster exists yet, so every
sample-size number below is provisional when applied to v3 and must be labelled as
carried over from v2. Re-derive them once a v3 dispersion estimate exists.

> **FLAG — SUPERSEDED 2026-08-10. Do not use the numbers below for v3 without re-deriving
> them.** Two identical-configuration v3 clusters now exist (runs 20-28, n=9, SD 0.782;
> runs 29-36, n=8, SD 1.061), giving a **measured pooled v3 σ ≈ 0.92 cases**. The paragraph
> above and every table in this section still assume σ ≈ 1.25 and are therefore too
> conservative for v3: detecting a 2-case shift needs ~4 runs per arm at σ = 0.92, not ~7.
> **This table must be re-derived from σ ≈ 0.92 before Phase 5 is registered.** See
> BASELINE.md for the measurement.

Aggregate accuracy, two-sample, α=0.05, 80% power:

| effect to detect | runs per arm |
|---|---|
| 3 cases (7.5 pp) | ~3 |
| 2 cases (5.0 pp) | ~7 |
| 1.5 cases (3.8 pp) | ~11 |

**8 runs per arm detects a ~2-case shift.** State the MDE in the plan; anything smaller is
not interpretable and must not be reported as an effect.

Per-case, for a target at baseline 0/8 (Fisher's exact, approximate):

| post-change | p | verdict |
|---|---|---|
| 3/8 | 0.20 | noise |
| 4/8 | 0.077 | not sufficient |
| **5/8** | **0.026** | **significant** |
| 6/8 | 0.007 | significant |

**≥5/8 is the threshold.** 4/8 does not clear it, however suggestive it looks.

95% CI half-width on the mean correct-count: n=3 → ±3.1 cases; n=5 → ±1.6; n=8 → ±1.0;
n=12 → ±0.8. Returns fall off sharply after 8.

## Anti-post-hoc rules

These are hard constraints, not preferences.

- **Decision rules are written before results are seen and are never edited afterward.**
  If a rule turns out to have been badly chosen, record that as a lesson for the *next*
  experiment; do not retrofit it onto this one.
- **Do not add a metric after seeing the data** and present it as the endpoint.
- **Do not re-slice until something is significant.** An inconclusive result is recorded
  as inconclusive.
- **A negative result is a result** and is recorded with the same weight as a positive
  one. Precedent: Phase 2B's objectivity hypothesis was not supported, and that is written
  into BASELINE.md as a finding.
- **One change per experiment.** Never bundle a prompt change with a dataset change —
  that is precisely what makes runs 18 and 19 non-comparable (commit `8359246` rewrote
  `quality-01` and `quality-03` between them).
- **Extension rules are pre-registered too.** "Run 4 more if the borderline set exceeds 4
  cases" is legitimate; "run 4 more because the result was almost significant" is not.

## Before proposing any experiment

Read the current BASELINE.md and confirm the baseline you are comparing against is a
*measured rate at the current configuration*, not an assumption inherited from an earlier
dataset version. If the baseline does not exist yet, the first experiment is to measure it.
