# Phase 8D.2C -- Witness Observability + 5-Run Validation

> **Sections 1-5 were written and committed BEFORE any provider call.** The
> decision rules below are the ones the runs are judged against; nothing in them
> is edited after results exist. Results are appended in §6 onward.

---

## 1. Pre-change safety

| Check | Result |
| --- | --- |
| `HEAD` before this phase | `fd41b4032fabe5c42eec5723dd8f7c5b7a8c5a45` |
| `git status --porcelain` | **empty** |
| `git diff --stat` | **empty** |
| `BENCHMARK_VERSION` / `DATASET_VERSION` | `v2` / `v4` |
| `git diff f79353c -- src/engine/eval/dataset.py` | **EMPTY** |
| Production `.engine/state.db` | `771e32904b9f100ebea79b8626b332cf794694872642f602b6b304b4c17d8219`, 3,092,480 B -- **not used for experiment writes**; every run is redirected with `ENGINE_DB_PATH` |

---

## 2. Historical control (fixed, not re-run)

Phase 8D.0, five runs at the safe engine `53d8a42`, same dataset checkpoint:

| Statistic | Value |
| --- | --- |
| Scores | 36, 35, 35, 35, 35 |
| Mean | 35.200 / 40 |
| Sample SD | 0.4472 |
| False-pass events | **0 / 100** broken-case observations |
| `correctness-02-clean` | 0/5 |
| `security-02-clean` | 0/5 |
| `security-04-clean` | 0/5 |
| `edge_case-03-clean` | 0/5 |
| `edge_case-04-clean` | 1/5 |

Not re-run in this phase: no comparability defect was found. This is a
descriptive before/after against a fixed historical control, **not** a
randomized controlled trial, and is reported as such.

---

## 3. Observability added (Part A)

The smallest thing that answers the attribution question, and nothing more.

**Design.** Every field is *derived* from data `run_benchmark` already produced.
`apply_witness_verification` leaves `witness`, `witness_result` and
`original_severity` on the defect dicts; those flow into `EvalCaseResult.defects`
untouched. So observability needed **no change to the witness layer, the judge,
the verdict gate, the schema, or the database.**

**Storage.** One JSON object per case in `witness-<eval_run_id>.jsonl`, written
beside the run's database. An experiment pointed at an isolated `ENGINE_DB_PATH`
therefore gets its own isolated log. **No DB migration. No schema change.**

**Per defect:** `lens`, `id`, `category`, `original_severity`,
`effective_severity`, `witness_emitted`, `witness_executed`, `witness_result`,
`blocking`, `authority_removed`.

**Per case:** `expected_verdict`, `actual_verdict`, `passed`, `error`,
`blocking_defects_before`, `blocking_defects`, `demoted`,
`witness_changed_verdict`.

`witness_changed_verdict` is the attribution primitive: *would the severities the
critics actually filed have blocked this case, and is it unblocked now?*

A sixth label, `NOT_EXECUTED`, distinguishes a witness emitted on a non-blocking
defect (never run, because only blocking defects are executed) from one never
emitted. It is not a verification outcome and is reported separately.

**Passivity.** The write happens after every database commit, outside the verdict
path, wrapped so that no failure can cost a completed run -- Phase 8D.1 lost 35
computed case results to an exception raised inside a persistence path.

### Files changed for Part A

| File | Change |
| --- | --- |
| `src/engine/eval/witness_log.py` | new, 118 lines -- pure record derivation + writer |
| `src/engine/eval/runner.py` | +10 lines: one import, one passive post-commit block |
| `tests/test_witness_log.py` | new, 17 tests |

**Behavioural path frozen at the prototype.** `git diff fd41b403` is empty for
`witness.py`, `witness_runner.py`, `judge.py`, `pipeline.py`, `verdict.py`,
`schema.py`, `rubric.py` and `dataset.py`.

### Deterministic validation (Part A)

| Gate | Result |
| --- | --- |
| `tests/test_witness_log.py` | **17 passed** (RED observed first: `ImportError: cannot import name 'witness_log'`) |
| witness + verification + eval + architecture + CLI + report | 123 passed |
| `ruff check .` | All checks passed |
| `mypy src` | Success, 47 source files |
| `pytest` (full) | **198 passed** |
| `git diff f79353c -- src/engine/eval/dataset.py` | **EMPTY** |

Tests cover all twelve required behaviours: each of the five statuses is
recorded; original severity preserved; effective blocking status recorded; only
`REFUTED` ever shows `authority_removed`; multiple defects keep separate
statuses; a malformed witness can never appear as a successful verification; a
failing log write changes no verdict; and a run with no witnesses is unchanged
and logs only `NO_WITNESS`.

---

## 4. Pre-registration (Part B)

**Arm.** Five full 40-case Benchmark v2 evaluations at the witness-enabled
configuration, all from one clean committed SHA, executed sequentially with no
source or config change between runs and no inspection between runs.

**Control.** The fixed Phase 8D.0 five-run result in §2.

### Decision rules

**A. Safety (primary).** `false_pass = 0` in all five runs; all **100**
broken-case observations remain `UNVERIFIED`.

**B. Target mechanism.** `edge_case-03-clean` improves from a baseline of 0/5 to
**>= 4/5**.

**C. Attribution.** That improvement is associated with `REFUTED` witness events
on that case -- `witness_changed_verdict` true -- not prompt drift with no
witness use.

**D. General safety.** No new stable clean-case regression; no global collapse in
blocking mass; schema-failure rate not materially increased; provider and gate
behaviour acceptable.

**E. Witness integrity.** Across every run, `authority_removed` is true only where
`witness_result == REFUTED`. `VERIFIED`, `UNSUPPORTED`, `INCONCLUSIVE` and
`NO_WITNESS` never remove authority.

**ACCEPT** requires all of A-E.

**`correctness-02-clean` is exploratory and is NOT an acceptance requirement.**
The architecture explicitly does not verify inference validity, and the 8D.2B
stored replay predicted this case would not be fixed: its companion finding
paired a true observation with a false inference.

### Negative outcomes, distinguished in advance

- **MECHANISM FAILURE** -- witnesses are emitted and executed, but the target does
  not improve.
- **EMISSION FAILURE** -- witnesses are rarely or never emitted, so the mechanism
  never got a chance. Reported as `PHASE_8D2C_EMISSION_FAILURE`.

The emission and execution rates in the witness log decide which. **No prompt
tuning happens inside this phase either way.**

### Revert rule

Any broken-case false pass rejects the prototype **if** the witness log shows
witness handling contributed (`witness_changed_verdict` true, or a demotion on
that case). If a false pass occurs where the log proves witness handling did not
touch the case, that is reported separately before any decision. A safety failure
is never offset by an aggregate score.

### Validity rule

Five valid runs are required, maximum seven attempts. Infrastructure-invalid
means: provider transport failure preventing completion, fewer than 40 cases
executed, a persistence crash, an OS-level crash of an automated tool, missing
case/lens rows, or experiment corruption. **Judge mistakes and schema failures
are judge behaviour, not invalidity.**

### Metrics recorded per run

Score, `false_pass`, `false_unverified`, schema failures, provider failures,
automated-gate failures, total calls, input/output tokens, cost, elapsed time;
and from the witness log: counts by status, emission rate, execution rate,
refutation rate, blocking defects demoted, and verdicts changed by refutation.
Per-case tracking for `edge_case-03-clean`, `correctness-02-clean`,
`security-02-clean`, `security-04-clean`, `edge_case-04-clean`, and all 20 broken
cases.

---

## 5. Provenance

The five runs execute from the commit recorded in §6 below, created before any
provider call so `get_git_commit_sha()` (which records `HEAD`, not the working
tree) stamps each run with the code that produced it.

---

## 6. Execution

All five runs executed sequentially from the clean committed tree at
**`15dd2e1a28d69aa062ea068caab8aec45b4896d9`**, in one uninterrupted command, each
into its own isolated database under
`.engine/experiments/phase8d2c-witness-validation/run<N>/`. No inspection and no
change between runs. 2026-08-18 07:48:31Z -> 08:12:50Z.

**All five runs are VALID.** Zero error rows, 120/120 lens calls `ok`, 120/120
automated gates passed, zero provider failures in every run. Nothing in §4's
invalidity list occurred. The CLI exited 1 on every run because it gates on
`false_pass != 0` -- that is the result, not an infrastructure fault.

---

## 7. Five-run results

| Run | SHA | Score | `false_pass` | `false_unverified` | Schema | Gate fail | Provider fail | Calls | In tok | Out tok | Cost | Elapsed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `15dd2e1a` | **28/40** | **5** | 7 | 2 | 0 | 0 | 120 | 61,811 | 23,222 | $0.177921 | 275 s |
| 2 | `15dd2e1a` | **28/40** | **5** | 7 | 3 | 0 | 0 | 120 | 61,811 | 23,381 | $0.178716 | 296 s |
| 3 | `15dd2e1a` | **28/40** | **5** | 7 | 3 | 0 | 0 | 120 | 61,811 | 23,852 | $0.181071 | 317 s |
| 4 | `15dd2e1a` | **27/40** | **6** | 7 | 2 | 0 | 0 | 120 | 61,811 | 23,659 | $0.180106 | 283 s |
| 5 | `15dd2e1a` | **28/40** | **5** | 7 | 4 | 0 | 0 | 120 | 61,811 | 23,802 | $0.180821 | 286 s |

| Statistic | Witness arm | 8D.0 control |
| --- | --- | --- |
| Scores | 28, 28, 28, 27, 28 | 36, 35, 35, 35, 35 |
| Mean | **27.800 / 40 (69.5%)** | 35.200 / 40 (88.0%) |
| Median | 28 | 35 |
| Sample SD | 0.4472 | 0.4472 |
| Min / max / range | 27 / 28 / 1 | 35 / 36 / 1 |
| **False passes** | **26 / 100** | **0 / 100** |
| Mean `false_unverified` | 7.0 | 4.8 |
| Schema failures (total) | **14** | 1 |
| Total cost | $0.898635 | $0.643430 |

**Delta: -7.400 cases.** At the measured SD of 0.447 that is roughly 16 sigma.
This is a descriptive comparison against a fixed historical control, not a
randomized trial -- but no reading of the noise floor accommodates it.

Category accuracy (mean, witness arm vs control): correctness **0.58 vs 0.90**,
security **0.70 vs 0.80**, quality **0.70 vs 1.00**, edge **0.80 vs 0.82**.

---

## 8. Safety -- the decisive result

**26 of 100 broken-case observations returned `OK`.** The control was 0/100.

| Broken case | Runs that false-passed |
| --- | --- |
| `correctness-01-broken` | 1, 2, 3, 4, 5 |
| `correctness-04-broken` | 1, 2, 3, 4, 5 |
| `correctness-05-broken` | 1, 2, 3, 4, 5 |
| `edge_case-04-broken` | 1, 2, 3, 4, 5 |
| `quality-05-broken` | 1, 2, 3, 4, 5 |
| `correctness-02-broken` | 4 |

### Attribution: every one was caused by witness demotion

| | |
| --- | --- |
| False passes with `witness_changed_verdict = true` | **26** |
| False passes not caused by witness handling | **0** |

In all 26, every blocking defect on the case carried a witness, every one was
`REFUTED`, and `blocking_defects` went to **0**. Example, `edge_case-04-broken`,
identical in all five runs:

```
correctness:CRITICAL->REFUTED->MEDIUM   correctness:CRITICAL->REFUTED->MEDIUM
security:HIGH->REFUTED->MEDIUM          security:HIGH->REFUTED->MEDIUM
code-quality:CRITICAL->REFUTED->MEDIUM  code-quality:CRITICAL->REFUTED->MEDIUM
blocking_defects_before=6  ->  blocking_defects=0
```

The §16 revert rule is triggered without ambiguity.

---

## 9. Witness metrics

| Run | Defects | Emitted | Executed | NO_WITNESS | VERIFIED | REFUTED | UNSUPPORTED | INCONCLUSIVE | NOT_EXECUTED | Demoted | Verdicts changed | Blocking before | Blocking after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 120 | 82 | 80 | 38 | 23 | 30 | 15 | 12 | 2 | 30 | 6 | 98 | 68 |
| 2 | 117 | 80 | 78 | 37 | 24 | 30 | 12 | 12 | 2 | 30 | 6 | 95 | 65 |
| 3 | 117 | 79 | 77 | 38 | 20 | 31 | 14 | 12 | 2 | 31 | 6 | 93 | 62 |
| 4 | 120 | 80 | 78 | 40 | 23 | 30 | 13 | 12 | 2 | 30 | 7 | 97 | 67 |
| 5 | 113 | 77 | 75 | 36 | 21 | 31 | 13 | 10 | 2 | 31 | 6 | 90 | 59 |

| Rate (5 runs pooled) | Value |
| --- | --- |
| Witness **emission** | 398 / 587 defects = **67.8%**; **84.1% of blocking defects** |
| Witness **execution** | 388 / 398 emitted = **97.5%** |
| Witness **refutation** | 152 / 388 executed = **39.2%** |
| Blocking mass | 473 -> **321** (**-32.1%**); control 428 |
| Case verdicts changed by witness | **31** |

**This is not an emission failure.** The model adopted the contract immediately
and at scale: 84% of blocking findings carried a witness and 97.5% of those were
executable. The mechanism ran exactly as designed and did the wrong thing.

### Where refutation landed

| REFUTED events | Count |
| --- | --- |
| On **broken** cases (harmful) | **137** |
| On **clean** cases (the intended use) | **15** |

Nine harmful refutations for every intended one. Of the 31 verdicts witness
verification changed, **26 were broken-case false passes** and 5 were
`edge_case-04-clean` correctly unblocked.

### Witness integrity: the invariant held

**Zero violations across all five runs.** `authority_removed` is true only where
`witness_result == REFUTED`. `VERIFIED`, `UNSUPPORTED`, `INCONCLUSIVE` and
`NO_WITNESS` never removed authority, in 587 defect observations. The
implementation does exactly what it was specified to do. **The specification is
what is wrong.**

---

## 10. Root cause

The `expect` field is ambiguous about whose behaviour it describes, and the model
resolved that ambiguity the opposite way from the classifier.

The prompt asked for "one call that shows it" with
`expect: {"returns": <JSON value>}`. A reviewer describing a defect writes the
**required** behaviour, not the **observed** one. The stored `fix` text makes the
model's frame explicit -- every one of these is a prescription:

> `edge_case-04-broken`: *"Change `9 <= hour <= 17` to `9 <= hour < 17` to exclude
> hour 17"* · *"Add validation to raise ValueError if hour is outside [0, 23]"*
>
> `quality-05-broken`: *"Add validation to raise ValueError if age < 0 or
> base_price < 0"*
>
> `correctness-01-broken`: *"Change `start = page * page_size` to
> `start = (page - 1) * page_size`"*

So the witness for a **missing-validation** defect is
`{"raises": "ValueError"}` -- and the buggy code, by definition, returns instead
of raising. The classifier reads "returned when a raise was claimed" as a clean
contradiction and demotes. The witness for a **wrong-value** defect states the
correct return, and the buggy code returns the wrong one -- contradiction again.

**On broken code, required behaviour and observed behaviour differ by
definition.** A contract that invites the model to state required behaviour and a
classifier that reads it as observed behaviour will therefore refute exactly the
true positives it exists to protect. That is the entire failure, and it explains
the 9:1 ratio precisely.

The `raises`-direction rule is the sharpest instance. It was added in Phase 8D.2B
because it was needed to refute `edge_case-03-clean` ("claims it raises, actually
returns"). It is the same rule that produces these false passes.

### Why deterministic testing could not have caught this

**In Phase 8D.2B I authored every witness myself, and always encoded observed
behaviour.** The 28 unit tests and the six-case stored replay therefore validated
*my* reading of the contract, not the model's. No deterministic test can
establish how a model will fill an ambiguous field -- only a live run can. The
replay's apparent success on `edge_case-03-clean` was an artifact of who wrote the
witnesses.

---

## 11. Other guardrails

**New stable clean-case regressions** -- three cases that were 5/5 in the control
are 0/5 here, and the log shows witness handling touched none of them
(`witness_changed_verdict = false` in every run):

| Case | Control | Witness arm | Cause |
| --- | --- | --- | --- |
| `quality-01-clean` | 5/5 | **0/5** | new blocking findings, no witness involved |
| `quality-02-clean` | 5/5 | **0/5** | new blocking findings (witnesses INCONCLUSIVE, no demotion) |
| `security-05-clean` | 5/5 | **0/5** | new blocking findings / schema fail-closed |

This is **prompt drift**, a second and independent harm: adding the witness clause
to `RESPONSE_INSTRUCTION` changed judge behaviour on cases the mechanism never
touched.

**Schema failures rose 1 -> 14** across five runs (2, 3, 3, 2, 4 vs 1, 0, 0, 0, 0).
`edge_case-02-broken x correctness` truncated mid-JSON in **all five runs**, which
is the `max_tokens=800` pressure Phase 8D.2A registered as risk #5: a witness
lengthens every defect object. Truncation fails closed, so it costs clean cases.

**Blocking mass collapsed** 473 -> 321 (-32.1%), against a control of 428.

### Per-case matrix -- every case not 5/5

| Case | r1 | r2 | r3 | r4 | r5 | Pass | Control |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `correctness-01-broken` | F | F | F | F | F | **0/5** | 5/5 |
| `correctness-04-broken` | F | F | F | F | F | **0/5** | 5/5 |
| `correctness-05-broken` | F | F | F | F | F | **0/5** | 5/5 |
| `edge_case-04-broken` | F | F | F | F | F | **0/5** | 5/5 |
| `quality-05-broken` | F | F | F | F | F | **0/5** | 5/5 |
| `correctness-02-broken` | P | P | P | F | P | 4/5 | 5/5 |
| `quality-01-clean` | F | F | F | F | F | **0/5** | 5/5 |
| `quality-02-clean` | F | F | F | F | F | **0/5** | 5/5 |
| `security-05-clean` | F | F | F | F | F | **0/5** | 5/5 |
| `correctness-02-clean` | F | F | F | F | F | 0/5 | 0/5 |
| `edge_case-03-clean` | F | F | F | F | F | 0/5 | 0/5 |
| `security-02-clean` | F | F | F | F | F | 0/5 | 0/5 |
| `security-04-clean` | F | F | F | F | F | 0/5 | 0/5 |
| `edge_case-04-clean` | P | P | P | P | P | **5/5** | 1/5 |

27 of 40 cases at 5/5, against 35 of 40 in the control.

---

## 12. Target cases

### `edge_case-03-clean` -- primary target: **0/5, unchanged**

Not an emission problem. Witnesses were emitted and executed on this case in every
run, and the `correctness` and `code-quality` blockers were refuted in four of
five. It kept failing because the **`security` lens's HIGH was `VERIFIED` in all
five runs** and one surviving blocker closes the gate:

```
run1: correctness:HIGH->VERIFIED  security:HIGH->VERIFIED   code-quality:HIGH->REFUTED
run2: correctness:HIGH->REFUTED   security:HIGH->VERIFIED   code-quality:HIGH->REFUTED
run3: correctness:HIGH->REFUTED   security:HIGH->VERIFIED   code-quality:HIGH->REFUTED
run4: correctness:HIGH->VERIFIED  correctness:HIGH->REFUTED security:HIGH->VERIFIED  code-quality:HIGH->REFUTED
run5: correctness:HIGH->REFUTED   security:HIGH->VERIFIED   code-quality:HIGH->REFUTED
```

The security lens found a witness whose observation genuinely holds on the clean
code -- the §7 A2 pattern from the architecture review, a true observation
carrying a false inference, now confirmed on the primary target as well.

### `correctness-02-clean` -- exploratory: **0/5**

As predicted and not an acceptance requirement. Its `security` blocker was
`VERIFIED` in all five runs; the same pattern.

### `edge_case-04-clean` -- **1/5 -> 5/5**

The one case the mechanism helped, and it worked exactly as designed: the
`correctness` HIGH was refuted in every run and `witness_changed_verdict` is true
in every run. It is worth one case; the same mechanism cost 26 false passes.

---

## 13. Decision: REJECT

| Criterion | Required | Observed | |
| --- | --- | --- | --- |
| **A. Safety** | `false_pass = 0`, 100/100 UNVERIFIED | **26/100 false passes** | **FAIL** |
| **B. Target** | `edge_case-03-clean` >= 4/5 | **0/5** | **FAIL** |
| **C. Attribution** | improvement caused by REFUTED events | no improvement to attribute | **FAIL** |
| **D. General safety** | no new stable regression, no blocker collapse, schema stable | 3 new 0/5 clean cases; blocking mass -32.1%; schema 1 -> 14 | **FAIL** |
| **E. Witness integrity** | only REFUTED removes authority | 0 violations in 587 observations | **PASS** |

**PHASE_8D2C_REJECTED.** Not an emission failure: the contract was adopted at 84%
of blocking defects and 97.5% of those executed. The mechanism worked and was
wrong.

### Safety confirmations

| | |
| --- | --- |
| Production `.engine/state.db` | `771e3290…4c17d8219`, 3,092,480 B, mtime unchanged -- **byte-identical before and after** |
| Dataset freeze | `git diff f79353c -- src/engine/eval/dataset.py` -> **EMPTY** |
| Repository | `HEAD` `15dd2e1a` throughout; `git status --porcelain` empty; nothing pushed |
| Cost | **$0.898635** for five runs; $0.00 for Part A |

---

## 14. What survives, and what to do next

**Kept.** The observability layer -- it is what made this phase readable. It
attributed all 26 false passes in one query, separated mechanism failure from
emission failure, and proved the authority invariant held. It has no behavioural
effect and stays.

**Reverted.** The witness mechanism's behavioural wiring: the `pipeline.py` call
and the `judge.py` prompt clause. That restores the safe engine's behaviour
exactly. The prototype modules and their tests remain in the tree as the recorded
experiment.

**The lesson worth carrying forward.** Two phases have now failed at the same
joint: 8D.1 asked the model for evidence and got fabricated evidence; 8D.2B/C
asked for checkable evidence and got evidence about the *wrong subject*. In both,
the engine's reading of a field and the model's reading of it diverged, and only a
live run exposed it. Any successor must pin down whose behaviour a field describes
-- observed or required -- and must be validated against witnesses the model
wrote, never ones the implementer wrote.

**Not recommended as a quick fix.** Splitting `expect` into `observed` and
`required` is the obvious repair, and it would very likely reduce these false
passes. It should not be attempted as a patch inside a rejected design: the same
prompt clause independently caused three clean-case regressions and a 14x rise in
schema failures through token pressure, neither of which the split addresses. A
successor needs its own pre-registration and its own noise-floor comparison.

**A cheaper alternative deserves consideration first.** The measured evidence says
the safe engine's 35.2/40 ceiling is set by four deterministic clean-case failures
whose causes are now well characterised, and that two successive attempts to move
them through the judge contract have made things worse -- by 2.4 cases and by 7.4
cases respectively. Accepting 36/40 as an honest description of this configuration
remains a legitimate outcome.
