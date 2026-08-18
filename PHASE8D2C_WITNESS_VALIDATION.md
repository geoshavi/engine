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
