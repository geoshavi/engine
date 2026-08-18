# Phase 5 Pre-Registration

Registered: 2026-08-14. Configuration under registration: the `src/` tree as of
`16961c1`, which is byte-identical to `77d36c3`, the commit run 37 executed at.

**The arm is identified by that source tree, not by a single SHA.** The commit that adds
this file necessarily changes `HEAD`, and so does any later commit that leaves `src/`
untouched; all of them are inside the registered configuration. The membership test is
the proving command in section 0, never SHA equality. A run leaves the configuration
only when `git diff 77d36c3 HEAD -- src/` stops returning empty.

**This file is committed before the first run of the arm it governs.** Phase 4's
registration was cited verbatim by `be990c7` but never committed and is unrecoverable
from this repository; that is recorded as Lesson 1 in the research vault. This file
exists so Phase 5 does not repeat it.

---

## 0. Why Phase 5 is a baseline measurement and not an intervention

`experiment-design` closes with: *"Read the current BASELINE.md and confirm the baseline
you are comparing against is a measured rate at the current configuration... If the
baseline does not exist yet, the first experiment is to measure it."*

At `16961c1` the baseline does not exist. Commit `77d36c3` changed
`src/engine/eval/runner.py` and `src/engine/verification/pipeline.py`, both on the
measured path, ending the c0515eb configuration cluster. The current cluster holds
**one run** (run 37).

Run 37 *is* poolable with runs executed at `16961c1`, because `src/` has not changed
since:

```
git diff 77d36c3 16961c1 -- src/     ->  empty      (verified 2026-08-14)
```

This is the SHA-differs-but-source-is-identical relationship `baseline-evidence`
requires be restated with its proving command. It is restated here.

Phase 5 therefore has two parts. **5A (this registration) measures the baseline.**
5B (an intervention) cannot be registered yet: its fields 2, 6 and 7 all depend on
rates 5A has not yet produced. Section 9 records the 5B candidates and the stored
evidence that already constrains them.

---

# PHASE 5A — Baseline characterization at `16961c1`

## 1. Hypothesis

> **H1-A:** `16961c1` is measurement-equivalent to the c0515eb cluster — its always-fail
> set is identical to the six cases measured 0/9 across runs 20-28, and its aggregate
> dispersion is consistent with the pooled σ = 0.92 carried over from the
> c0515eb / be990c7 clusters.

Falsifiable: a single case moving out of the always-fail set, or an observed SD outside
the interval in section 7, refutes it.

No intervention is applied. Nothing in `src/` is edited. This arm measures the
configuration that already exists.

## 2. Target cases

All 40 cases are measured. The nine that were not always-pass at c0515eb are named
below with their prior rate.

**The c0515eb column is a prior expectation at a *different configuration*, not a
baseline for `16961c1`.** It is recorded so that section 7's rejection rule has
something to compare against. The `16961c1` column is what 5A produces; run 37 is its
only current member.

| case | c0515eb, runs 20-28 | run 37 (n=1) | class at c0515eb |
|---|---|---|---|
| `correctness-02-clean` | 0/9 | FAIL | always-fail |
| `edge_case-03-clean`   | 0/9 | FAIL | always-fail |
| `quality-01-broken`    | 0/9 | FAIL | always-fail (false_pass) |
| `quality-03-broken`    | 0/9 | FAIL | always-fail (false_pass) |
| `security-02-clean`    | 0/9 | FAIL | always-fail |
| `security-04-clean`    | 0/9 | FAIL | always-fail |
| `edge_case-04-clean`   | 5/9 | PASS | borderline |
| `quality-02-clean`     | 4/9 | PASS | borderline |
| `quality-04-clean`     | 8/9 | PASS | borderline |
| `security-03-clean`    | 9/9 | PASS | always-pass (watched — see G4) |

The remaining 30 cases were always-pass across runs 20-28 and passed in run 37.

## 3. Control / guardrail cases

5A changes nothing, so there is no intervention to guard against. The guardrails are
integrity guardrails, and each states its consequence in advance.

| id | guardrail | threshold | consequence if breached |
|---|---|---|---|
| **G1** | `eval_case_results.error` rows | must be 0 per run | run **excluded and re-run**; never averaged in (standard rule — this is how run 1 recorded 0/40) |
| **G2** | `eval_case_automated_gates.passed` | must be 1 for all 120 rows per run | run **excluded from the arm** under an Amendment-A1-style note recording the gate, the case and the reason |
| **G3** | `eval_case_schema_failures` | ≤ 2 per run (runs 20-37 observed 0-2) | **recorded, not excluded**; >2 is flagged as a regression signal in BASELINE.md |
| **G4** | `security-03-clean` | expected PASS in 8/8 | **recorded as an adverse finding**, and 5B may not touch judge severity until it is explained |

G4 exists because of Lesson 3: `security-03-clean` was the largest per-case movement
Phase 4 produced (-62.5 pp) and was *not* a registered guardrail, so it could only be
recorded as an unregistered adverse finding rather than a triggered rejection. It is
registered here even though 5A applies no intervention.

## 4. Frozen variables

Nothing is edited. The entire measured path is frozen at `16961c1`:

```
src/engine/eval/dataset.py
src/engine/eval/runner.py
src/engine/verification/judge.py          (LENSES, RESPONSE_INSTRUCTION)
src/engine/verification/rubric.py
src/engine/verification/schema.py
src/engine/verification/verdict.py
src/engine/verification/pipeline.py
src/engine/runtime/gateway.py
src/engine/runtime/budget.py
```

Config values frozen for the arm:

- judge model `claude-haiku-4-5-20251001`, temperature `0.0`
- `DATASET_VERSION = v3`, `BENCHMARK_VERSION = v1`
- 40 cases, 3 lenses, gates `ruff` / `mypy` / `pytest`

**Standing proof obligation.** Before each run, `git status --porcelain` must be empty
and `git diff 77d36c3 <HEAD at run time> -- src/` must return empty. If the second
command ever returns output, the arm is closed at whatever N it reached and run 37 stops
being poolable.

## 5. Metrics

- **Primary — per-case pass rate across all 40 cases at n=8**, reported as the stability
  partition (always-pass / always-fail / borderline). This is the sensitive metric: the
  variance surface is 2-3 cases wide while accuracy averages over 40.
- **Secondary — aggregate `correct_verdicts / 40`**: mean and SD. Reported, never
  decisive.
- **Guardrail — G1-G4** as tabulated above.
- **Also recorded** (no decision rule attached, for 5B design input): per-lens ×
  severity defect distribution; the `false_pass` / `false_unverified` composition; and
  the per-run defect profile of `quality-01-broken`, `quality-01-clean` and
  `quality-03-broken`.

## 6. Sample size

**N = 8 at `16961c1`.** Run 37 already counts (section 0), so **7 new runs are
required.**

- cost ≈ 7 × $0.1217 ≈ **$0.85**
- wall clock ≈ 7 × 3.5 min ≈ **25 min**

What N=8 buys the *next* experiment, at σ = 0.92:

- aggregate MDE ≈ **1.3 cases**
- per-case, a target at baseline 0/8 needs **≥5/8** post-change to reach p = 0.026
- 95% CI half-width on the mean correct-count ≈ **±0.8 cases**

**Pre-registered extension rule.** If the borderline set at n=8 exceeds **5** cases,
run 4 more (to n=12) and report both n=8 and n=12. No other extension is permitted.
"Run more because the result was almost significant" is not a legitimate extension and
will not be applied.

## 7. Acceptance / rejection / inconclusive

Stated numerically, before any run.

**ACCEPT H1-A** — all three must hold:
1. the always-fail set at n=8 is exactly the six cases named in section 2;
2. the observed SD of the correct-count falls in **[0.45, 1.39]**;
3. G1, G2 and G3 all hold for at least 7 of the 8 runs.

**REJECT H1-A** — any one of:
1. the always-fail set differs from the six named cases by **≥1 case** (in either
   direction — a case leaving it or joining it);
2. the observed SD falls **outside [0.45, 1.39]**.

Consequence of rejection: `16961c1` is not behaviourally the c0515eb configuration.
The section 2 prior expectations are discarded, and 5B must be designed against the
`16961c1` rates alone.

**INCONCLUSIVE** — either:
1. G1/G2 exclusions leave **n < 7**; or
2. a run cannot be executed against a clean tree at the frozen SHA.

The SD interval is the 95% sampling interval for an observed SD at df = 7 when the true
σ is 0.92: `0.92 × sqrt(χ²(7) / 7)` evaluated at the 2.5% and 97.5% points
(χ² = 1.690 and 16.013). For the n=12 extension the corresponding interval is
**[0.54, 1.30]**.

## 8. What a negative result looks like

Concretely, any of these, and each is a *result* rather than a failure:

- `quality-01-broken` passes in ≥1 of the 8 runs — it is borderline at `16961c1`, not
  always-fail, and section 9's candidate B1 analysis is void.
- `security-03-clean` fails in ≥1 run — G4 breached with no intervention applied, which
  would mean the Phase 4 adverse finding was never fully reverted.
- observed SD = 1.6 — dispersion at `16961c1` is larger than σ = 0.92, every sample-size
  number in `experiment-design` is too optimistic for this cluster, and they must be
  re-derived again before 5B.
- the always-fail set gains a case that was borderline at c0515eb — the measured-path
  edit in `77d36c3` was not judge-neutral after all, contradicting that commit's own
  mechanism argument.

A result in which H1-A is accepted is *also* a result: it establishes the first real
baseline arm at `16961c1` and unlocks 5B.

---

# 9. Phase 5B candidates — NOT REGISTERED

Recorded now so that 5A's data is read against pre-existing expectations rather than
fresh ones. Neither candidate may be run under this registration.

## B1 — `quality-01-broken` severity calibration ⚠️ REFUTED IN ADVANCE

`quality-01-broken` and `quality-03-broken` are the *only* two false_pass cases, in
**18/18 runs 20-37**. B1 targets the first.

The obvious intervention — make CODE-QUALITY MEDIUM findings blocking, or push this
finding to HIGH — is **refuted by stored data before any run**:

| case | code-quality defects, runs 20-37 (18 runs) |
|---|---|
| `quality-01-broken` | MEDIUM ×18, LOW ×18 |
| `quality-01-clean`  | MEDIUM ×18 |

The broken side's MEDIUM is the discriminating one (the manual accumulation loop, i.e.
the authored decomposition axis). But the **clean side carries a MEDIUM in every single
run too** — it is the `list[dict[str, object]]` return annotation, and that annotation
is **identical in both variants**.

So a blunt severity move flips `quality-01-broken` to UNVERIFIED (removing 1 false_pass)
*and* `quality-01-clean` to UNVERIFIED (adding 1 false_unverified). **Net accuracy
change: zero.**

Blast radius is worse than that. In run 37 the code-quality lens emitted **9 MEDIUM
findings across clean cases**. A blunt boundary move could drive `false_unverified` from
4 toward 13 — an order of magnitude larger than anything Phase 4 produced.

**Therefore:** B1 is not registrable as stated. If pursued at all, the intervention must
target the decomposition finding specifically rather than the MEDIUM class, and
`quality-01-clean` must be a pre-registered *rejection* guardrail, not a watched case.

### Incidental dataset finding (not an experiment, no change proposed)

`quality-01-clean`'s persistent MEDIUM is raised against a property present identically
in the broken and clean variants. That is precisely the *non-discriminating defect* class
dataset v3 set out to remove — and it survived the v3 cleanup in `quality-01`. Recorded
as a finding. It cannot be bundled with a judge change: one change per experiment.

## B2 — `quality-03-broken` detection gap

Stronger evidence, harder intervention.

Since commit `8359246` isolated `quality-03` to the naming axis, the code-quality lens
has emitted **zero defects** on `quality-03-broken` across **19 consecutive runs
(19-37)**. `call_status = ok` and `defect_count = 0` in every one: the lens runs, and
finds nothing. Before `8359246` it emitted 1-2 defects per run across runs 3-18.

This is a **detection** failure, not a severity failure. No severity calibration can
reach it.

**This updates a recorded interpretation.** BASELINE.md's Phase 2B note describes
`quality-03`'s misleading-naming defect as "detected by the pipeline but not reliably
reaching blocking severity". That was accurate for the pre-`8359246` form of the case,
which the note was written from (runs 3-19). It is no longer accurate for the isolated
v3 form: the defect is not detected at all. This should be appended to BASELINE.md as a
superseding note — not a rewrite — once 5A confirms the pattern holds at `16961c1`.

B2 is registrable after 5A. Its intervention would add an inclusion criterion to the
code-quality lens, and Phase 4 demonstrated that judge-instruction changes have a wide
blast radius, so its registration must carry `security-03-clean`, all four always-fail
clean cases, and `quality-01-clean` as pre-registered guardrails.

## Recommended order

1. **5A** — establish the baseline. Registrable and runnable now.
2. **B2** — the detection gap, registered against 5A's measured rates.
3. The `quality-01-clean` dataset finding, as its own separate change, never bundled.

B1 is not recommended: its ceiling is zero net accuracy and its downside is up to nine
newly-blocked clean cases.

---

# 10. Anti-post-hoc commitments

- This file is committed **before** the first run of the 5A arm.
- The decision rules in sections 6 and 7 are frozen. They will not be edited once
  results exist. If one proves badly chosen, that is recorded as a lesson for the next
  experiment and applied there.
- No metric will be added after seeing the data and presented as an endpoint.
- The result will not be re-sliced until something is significant. An inconclusive
  result is recorded as inconclusive.
- A negative result is recorded with the same weight as a positive one — precedent:
  Phase 2B's objectivity hypothesis and Phase 4's H1, both recorded as unsupported.
- One change per experiment. 5A changes nothing; 5B will change exactly one thing.

# 11. Pre-run gate (executed immediately before each run)

1. `git status --porcelain` → empty
2. `git rev-parse HEAD` → record alongside the run
3. `git diff 77d36c3 HEAD -- src/` → empty (keeps run 37 poolable)
4. confirm step 3 returned empty — that, and not SHA equality, is what places the run
   inside the registered configuration (see the header)

Running the benchmark is a mutating operation and requires explicit user approval in the
turn it is run. This registration does not constitute that approval.
