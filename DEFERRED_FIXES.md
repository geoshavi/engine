# Deferred Infrastructure Fixes

Fixes that are diagnosed and specified but deliberately **not applied**, because applying
them would change the measured path (`src/`) while a frozen measurement arm is open.

This file is a work queue, not evidence and not a registration. It records no run and no
result. Nothing here may be cited as a measured finding; see `BASELINE.md` for measured
results and `PHASE5_REGISTRATION.md` for the arm currently frozen.

**Rule for every entry:** an entry may be implemented only after the frozen
benchmark/dataset adjudication work it names is formally closed. Closing that work is a
separate, explicitly approved step. Implementing an entry early ends the arm.

## Status index

| Entry | Status | Resolved in |
| --- | --- | --- |
| DF-1 | **IMPLEMENTED / CLOSED** | Phase 8A |
| DF-2 | **NOT_APPLICABLE_TO_THIS_REPOSITORY / PROVENANCE_RESOLVED** | Phase 8A |

Neither resolution reclassifies a historical run and neither changes Benchmark v2 dataset
semantics. See `PHASE8A_INFRASTRUCTURE_CLEANUP.md`.

---

## DF-1 -- `mypy` gate reports empty subprocess output as `"ok"`

**Status:** **IMPLEMENTED / CLOSED** in Phase 8A. Applied to
`src/engine/verification/automated.py` at `_run`; see the *Closure* section at the end of
this entry. Everything between here and that section is the original 2026-08-17 diagnosis,
preserved unedited as the record of what was found and why.
**Was blocked on:** formal closure of Phase 5A adjudication (see `PHASE5_REGISTRATION.md`).
**Location:** `src/engine/verification/automated.py`, in `_run` (the `detail` assignment).
**Diagnosed:** 2026-08-17, by read-only inspection of `src/` and `.engine/state.db` at
`d856d72`. No run, no provider call, and no file modification was part of the diagnosis.

### Defect

`_run` derives its two return values as:

```python
passed = result.returncode == 0
detail = (result.stdout + result.stderr).strip() or "ok"
```

The `or "ok"` fallback is reachable **only when combined stdout and stderr are empty**.
`mypy` prints `Success: no issues found in ...` when it succeeds and prints diagnostics
when it fails, so empty output means the subprocess emitted nothing at all.

Therefore a stored row of `passed = 0` with `detail = "ok"` means *mypy exited non-zero
without writing a single byte*. It is a process-level failure, not a type error.

**`detail == "ok"` on a failed gate is an ambiguous sentinel for empty stdout/stderr. It
is not evidence of success**, even though it reads as though it were. That ambiguity is
the defect; the underlying subprocess failure is a separate, still-unidentified matter.

### Why the root cause is currently undiagnosable

`_run` discards `result.returncode` after computing the boolean. The exit status is the
one value that would distinguish a Windows fatal-error crash, an OS kill, and a `mypy`
internal exit 2 from one another. Because it is never stored, no historical row can be
attributed to a cause. Closing that gap is the entire point of this fix.

### Measured incidence

| | |
| --- | --- |
| `mypy` gate executions recorded in `.engine/state.db` | 1560 |
| Rows with `detail = "ok"` | 2 (~0.128%) |
| Legitimate `mypy` failures in the whole history | 0 |

Because `mypy` has never once failed legitimately, `passed = 0` and this anomaly are
currently the same event, 2 occurrences out of 2.

### The anomaly is not content-specific to `quality-04`

Both occurrences landed on the `quality-04` task, but on **different variants** whose file
contents are entirely different:

| Position in run order | Run 26 | Run 41 |
| --- | --- | --- |
| 27 of 40 (`quality-04-broken`) | `mypy` passed | **anomaly** |
| 28 of 40 (`quality-04-clean`) | **anomaly** | `mypy` passed |

The pattern is a mirror image across adjacent positions, which is the signature of a
transient failure rather than a property of either case. Supporting observations:

- A content-specific trigger would have to fire on two different file bodies.
- `ruff` produced normal output in the same workspace in the same second as each anomaly.
- The sibling case's `mypy` ran normally 4-6 seconds away in both runs.
- With 20 task ids, two independent anomalies share a task id with probability ~1/20
  (~5%). That is weak evidence, not a detected pattern.

Nothing was contaminated across cases; one subprocess died silently. Note that
`research-vault/Amendment A1.md` characterizes the run 26 occurrence as "environment
contamination". That wording is imprecise by the above, but it sits inside a registered
amendment and is **not to be edited**; it is flagged here only so the discrepancy is on
the record.

### Impact on scores, per occurrence

The anomaly pushes a case toward `UNVERIFIED` through two independent routes:

1. `automated_defects()` injects `AUTO1-mypy` / `CORRECTNESS` / `HIGH`. Present in both
   occurrences.
2. `automated_passed` becomes `False`, and `verdict.gate` returns `UNVERIFIED` on that
   alone, before any defect is examined.

| Occurrence | Expected | Other defects | Score effect |
| --- | --- | --- | --- |
| Run 26, `quality-04-clean` | `OK` | only `C1` `CODE-QUALITY` `MEDIUM`, non-blocking | **decisive: -1** |
| Run 41, `quality-04-broken` | `UNVERIFIED` | three genuine `HIGH` | none |

- **Run 26 `quality-04-clean` was score-distorting.** The injected `AUTO1-mypy` `HIGH`
  was the only blocking defect present; without it the case would have returned `OK`.
  Every other recorded failure of this case carries a genuine `HIGH` (runs 5, 6, 30) or a
  schema failure (run 38), so run 26 is the only one attributable to the gate.
- **Run 41 `quality-04-broken` was invalid under the same infrastructure rule but did not
  change the outcome.** The expected verdict was `UNVERIFIED` and three independent
  genuine `HIGH` defects were present, so the verdict was over-determined. Invalidity
  follows from the rule, which is unconditional; it does not follow from impact, and the
  absence of impact does not rehabilitate the run.

### Separate, unrelated event -- not an instance of DF-1

Run 38 `quality-04-clean` returned `UNVERIFIED` with zero defects. Its `code-quality`
lens recorded `schema_valid = 0`, and `verdict.gate` fails closed on schema errors before
reaching defects or gate results. That is a **schema fail-closed event and expected
behaviour**, not a `mypy` anomaly. It is noted so the two are not conflated when the arm
is analysed: one failure of that borderline case reflects a schema failure rather than a
judge judgement.

### Fix to apply, when unblocked

Replace the ambiguous fallback so an empty-output failure identifies itself:

```python
detail = (result.stdout + result.stderr).strip() or f"(no output, exit {result.returncode})"
```

This preserves every existing message verbatim -- the fallback is reached only when there
is no output to preserve -- and makes the anomaly self-diagnosing on first recurrence.

### Constraint that makes this deferred, not merely unscheduled

`automated.py` is inside `src/`, the measured path. The Phase 5A membership test is that
`git diff 77d36c3 HEAD -- src/` returns empty. Editing this file makes that diff non-empty,
which leaves the registered configuration, ends the arm, and makes runs 37-40 unpoolable
with anything that follows.

Correct order of operations:

1. Complete and formally close Phase 5A adjudication.
2. Apply DF-1 as its own commit, touching no dataset and no judge behaviour.
3. Verify with `ruff`, `mypy`, `pytest`, plus a unit test asserting that a non-zero exit
   with empty output yields a `detail` containing the exit status and never the string
   `"ok"`.
4. Treat everything after that commit as a new arm. Do not pool across it.

Applying step 2 before step 1 is the failure mode this entry exists to prevent.

### Closure -- Phase 8A

**Status: IMPLEMENTED / CLOSED.** Applied at Benchmark v2 checkpoint
`f79353c65099561854e63ed2a8b8e23aaa2c58ce`, after Phase 5A adjudication was closed and the
Benchmark v2 dataset was frozen. The correct order of operations above was followed.

**Exact fix.** One expression in `_run`, exactly as prescribed above:

```python
detail = (
    (result.stdout + result.stderr).strip() or f"(no output, exit {result.returncode})"
)
```

`passed = result.returncode == 0` is untouched, so no verdict semantics moved. The fallback
is reachable only when combined stdout and stderr are empty, so every real gate message is
preserved byte for byte. A genuine gate failure still fails closed through
`automated_defects()` and `verdict.gate()` exactly as before -- the change makes the failure
*legible*, it does not make it survivable.

**Returncode persistence.** `eval_case_automated_gates` has columns
`(id, eval_case_result_id, gate_name, passed, detail, created_at)` and **no returncode
column**; the same is true of `verification_results`. Persisting the exit status as its own
column would require a schema migration against `.engine/state.db`, which holds the entire
run history and has no version-control backup. A migration is **not strictly necessary**:
`detail` is persisted verbatim, so carrying the exit status inside it makes the anomaly
self-diagnosing on first recurrence without touching the schema or the production database.
The production DB was opened read-only (`file:...?mode=ro`) for inspection and never
written. Should a future run make per-column querying of exit status worthwhile, that is a
separate, separately-approved migration.

**Deterministic tests** (in `tests/test_verification.py`, driving `_run` with real
subprocesses -- no mocks, no network):

| Test | Covers |
| --- | --- |
| `test_run_reports_normal_output_verbatim_on_success` | exit 0 + normal output |
| `test_run_reports_normal_output_verbatim_on_failure` | non-zero + normal error output |
| `test_run_never_reports_ok_for_a_failed_gate_that_wrote_no_output` | non-zero + empty output; asserts `detail != "ok"` |
| `test_run_preserves_the_exit_code_for_each_distinct_silent_failure` | exit 2 and exit 3 produce *distinct* details |
| `test_run_reports_empty_output_explicitly_even_when_the_gate_passed` | exit 0 + empty output |
| `test_silent_failure_detail_reaches_the_defect_fix_text` | diagnostic survives into `automated_defects()` |
| `test_silent_failure_detail_round_trips_through_the_gate_record` | write/read cycle through `eval_case_automated_gates` (temp DB) |

The three empty-output tests were written first and observed to fail with
`AssertionError: assert 'ok' != 'ok'` before the fix was applied. No existing test encoded
the old behaviour, so **no test was updated or weakened** -- all seven are additions.

**Historical runs reclassified: NO.** Runs 26 and 41 remain exactly what they were. Run 26
`quality-04-clean` remains score-distorting and run 41 `quality-04-broken` remains invalid
under the same infrastructure rule; run 38 remains a separate schema fail-closed event, not
an instance of DF-1. This fix changes what future gate failures *record about themselves*.
It recovers no information that was not written down at the time, and no past row's meaning
changes. `research-vault/Amendment A1.md` remains unedited.

**Benchmark v2 dataset semantics changed: NO.** `git diff f79353c -- src/engine/eval/dataset.py`
is empty.

**Arm boundary.** `automated.py` is inside `src/`, so step 4 of the plan above still
applies: treat everything after the Phase 8A commit as a new arm and do not pool across it.

---

## DF-2 -- reconciliation rationale 400-character validation limit

**Status:** **NOT_APPLICABLE_TO_THIS_REPOSITORY / PROVENANCE_RESOLVED.**
**No production code change is required, and none was made.**

DF-2 was carried into Phase 8A from the deferred list recorded in
`BENCHMARK_V2_CHANGELOG.md` and `benchmark-v2-implementation-manifest.json` as
*"400-character reconciliation rationale limit causing fail-closed responses"*, with
supporting evidence from Step 6.4R V2: 186 reconciliation responses, 179 accepted, 7
rejected for rationales exceeding a frozen 400-character bound, all 7 provider-complete
(`end_turn`) rather than truncated.

### Provenance finding

An exhaustive search of this repository -- at `f79353c` and across its **entire** git
history -- found no code the entry could apply to.

| Search | Result |
| --- | --- |
| `git grep -i "rationale"` (tracked) | only `graphify-out/.graphify_analysis.json`, whose `*_rationale_*` strings are research-graph node ids generated by `tools/research_graph.py` for source comments -- unrelated |
| `git grep -i "reconcil"` (tracked) | 2 hits, both prose lines *listing DF-2 as deferred* |
| `git log --all -S"rationale"`, `-S"reconcil"` | `f79353c` only -- i.e. those same prose lines. No commit ever added such code |
| `git grep "\b400\b"` | HTTP status codes in `src/engine/api.py`, `BENCHMARK_MAX_TOKENS = 400_000`, and an Anthropic 400-response comment. No character bound |
| `git grep -E "len\([^)]*\)\s*[<>]"` (`*.py`) | `execution_plan.py` (`max_agents`), `research_graph.py` (cell count). No string-length validation anywhere |
| `git grep -E "\[:\s*[0-9]+\]"` (`*.py`) | `automated.py` `detail[:2000]`, `research_graph.py` `commit_sha[:7]`. Neither is a rationale bound |
| `git grep "2400"`, `max_tokens` in `src/` | no 2400-token budget exists; judge lens calls are `max_tokens=800` (`JUDGE_MAX_OUTPUT_TOKENS`) |
| `.engine/state.db` table list (read-only) | `agent_execution_metrics, agent_executions, defects, eval_case_automated_gates, eval_case_defects, eval_case_lens_results, eval_case_results, eval_case_schema_failures, eval_runs, runs, verification_results` -- no reconciliation table |

There is no reconciliation subsystem, no rationale field, no 400-character validator and no
2400-token reconciliation response budget in the current engine codebase, and none has ever
been committed to it.

### What this does and does not claim

**It does not claim the Step 6.4R issue was unreal.** The 7-of-186 rejection evidence stands
as recorded. The finding is narrower and purely about location: **the implementation that
imposed that bound lived outside this repository** -- in the exploratory Step 6.4R tooling --
and is not part of the engine codebase this file governs. DF-2 is therefore an
experiment-local issue, not a pending production-repository infrastructure defect.

### Why nothing was built

Implementing DF-2 here would have required *creating* a reconciliation response validator
in order to relax a limit inside it. That is fabricating infrastructure for a use case that
does not exist in this codebase, which `CLAUDE.md`'s *Simplicity first* and *Surgical
changes* rules forbid outright, and it would have widened the measured surface immediately
before the first clean Benchmark v2 baseline. The correct resolution of a work-queue entry
whose target is absent is to resolve its provenance, not to manufacture the target.

If reconciliation tooling is ever brought into this repository, the 400-character bound must
be reconsidered **at that point**, against the then-current response budget and the stored
V2 evidence -- not against any benchmark score.

**Deterministic tests:** none, and none are possible -- there is no code path to test. The
finding is a provenance result, established by the read-only searches tabulated above.

**Historical runs reclassified: NO.** Step 6.4R's 7 rejected responses remain historical
facts and are not re-adjudicated here.

**Benchmark v2 dataset semantics changed: NO.** No file under `src/` was modified for DF-2.
