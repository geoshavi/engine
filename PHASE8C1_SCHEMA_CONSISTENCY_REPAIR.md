# Phase 8C.1 -- Schema Consistency Repair

**Outcome: the repair worked; it revealed that Phase 8C did not. Both were reverted.**

| | |
| --- | --- |
| Starting `HEAD` | `7078c29a6a935e1d46d9ac1f04450967f01df01c` |
| Phase 8C engine commit | `4954f4af124be01b56fbfc64434993d9e3617b63` |
| Phase 8C.1 repair commit | `da5addbcb54495fe2d2fa735159d4f29014a0a53` |
| Dataset checkpoint | `f79353c65099561854e63ed2a8b8e23aaa2c58ce` (`v2` / `v4`), unchanged throughout |

| Run | Score | `false_pass` | `false_unverified` | Schema failures |
| --- | --- | --- | --- | --- |
| Phase 8B baseline (`e967612`) | 35/40 | 0 | 5 | **0** |
| Phase 8C (`4954f4a`) | 38/40 | 0 | 2 | **7** |
| **Phase 8C.1 (`da5addb`)** | **33/40** | **2** | 5 | **1** |

---

## 1. Autopsy of the 7 Phase 8C schema failures

Read-only, from the persisted `eval_case_schema_failures.raw_response`. No provider calls.
Each raw response was re-parsed through the real `_extract_json_objects` and
`enforce_critic_schema` rather than trusting the stored error string.

| # | Case | Lens | Severities emitted | Verdict emitted | Blocker left? | Structurally valid? | Class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `security-02-clean` | security | LOW, MEDIUM | `FAIL` | none | yes | **A** |
| 2 | `security-04-clean` | correctness | -- | -- | -- | **no JSON object** | **B** |
| 3 | `quality-01-broken` | correctness | MEDIUM | `FAIL` | none | yes | **A** |
| 4 | `quality-01-broken` | security | MEDIUM | `FAIL` | none | yes | **A** |
| 5 | `quality-02-broken` | correctness | MEDIUM | `FAIL` | none | yes | **A** |
| 6 | `quality-04-broken` | code-quality | MEDIUM, MEDIUM | `FAIL` | none | yes | **A** |
| 7 | `edge_case-03-broken` | code-quality | MEDIUM | `FAIL` | none | yes | **A** |

**Class A = 6, Class B = 1.** They are *not* all identical, which is why the check was run
rather than assumed.

- **Class A (6):** a complete, structurally clean response in which every severity had
  correctly softened to MEDIUM/LOW after the reordered analysis, but a stale
  `"verdict": "FAIL"` was still emitted. The *only* schema error in each was the verdict
  mismatch.
- **Class B (1):** `security-04-clean` x correctness was **truncated** -- 2,855 characters
  ending mid-object (`"verdict": "OK"` with no closing brace). A different defect entirely:
  the longer `fix` analysis Phase 8C asks for overruns the judge's `max_tokens=800`.
  Explicitly out of scope for this phase.

---

## 2. Verdict authority -- architecture finding

`grep` over `src/` for every read of a critic's `verdict` field:

| Site | Role |
| --- | --- |
| `schema.py:42` | the consistency check itself -- **the only reader** |
| `verdict.py:14` | **writes** a value derived from severities |
| `orchestrator/manager.py` | constructs its own critic dicts for retry feedback; never judge output |

`verdict.merge()` recomputes the verdict from severities and `verdict.gate()` branches on
`_has_blocking()`, i.e. severities alone. **The model's `verdict` string has never had any
downstream authority.** The schema was failing an entire lens response closed over a field
nothing acts on -- discarding that lens's findings in the process.

**Chosen design: option A.** Severities are authoritative; the verdict string is derived.

- `schema.derive_verdict(defects)` -- new single source of truth (any CRITICAL/HIGH -> FAIL).
- `enforce_critic_schema` still requires `verdict in {"OK","FAIL"}` but no longer errors on a
  mismatch with its own severities.
- `_parse_critic` normalizes `parsed["verdict"] = derive_verdict(...)` after validation, so no
  consumer can ever observe the two disagreeing.

**Safety is strictly improved, not weakened.** Previously `verdict:"OK"` alongside a CRITICAL
finding produced a schema error, which **threw that finding away** and blocked only via the
schema path. Under the repair the finding is retained and blocks on its own merit through
`merge()`/`gate()`. An LLM-supplied string cannot override structured severity evidence in
either direction. Malformed JSON, invalid severity, invalid category, missing keys, stray
top-level keys and a non-`OK|FAIL` verdict all still fail closed, unchanged.

---

## 3. TDD evidence

12 new tests covering all nine required scenarios. **RED observed first** on the five that
required the change (`assert ["verdict: is 'OK' but expected 'FAIL' given the defects"] == []`);
the four fail-closed guards passed before and after, as they should.

| Scenario | Test | Result |
| --- | --- | --- |
| 1. MEDIUM/LOW + verdict FAIL | `test_stale_fail_verdict_after_softening_is_accepted_and_normalized` | effective OK |
| 2. No defects + verdict FAIL | `test_no_defects_with_fail_verdict_is_accepted_and_normalized` | effective OK |
| 3. HIGH + verdict OK | `test_high_defect_with_ok_verdict_still_blocks` | **UNVERIFIED** |
| 4. CRITICAL + verdict OK | `test_critical_defect_with_ok_verdict_still_blocks` | **UNVERIFIED** |
| 5. MEDIUM+HIGH+LOW + verdict OK | `test_mixed_medium_and_high_with_ok_verdict_still_blocks` | **UNVERIFIED** |
| 6. Already-consistent pairs | `test_already_consistent_responses_are_unchanged` | unchanged |
| 7. Malformed JSON | `test_malformed_json_still_fails_closed` | fails closed |
| 8. Invalid severity/category/keys | `test_invalid_severity_and_category_still_fail_closed` | fails closed |
| 9. Non-verdict errors not normalized away | `test_non_verdict_schema_errors_are_not_normalized_away` | fails closed |

One **existing** test, `test_enforce_critic_schema_rejects_inconsistent_verdict`, explicitly
encoded the retired rule. It was re-pointed at the safety property it existed to protect --
that a CRITICAL still blocks end to end -- which is a stricter assertion than the
error-message check it replaced. No other test was modified.

`ruff` clean - `mypy` clean (44 source files) - **`pytest` 168 passed**
- `git diff f79353c -- src/engine/eval/dataset.py` **EMPTY**.

---

## 4. Validation run

One run, at `da5addb`, clean tree, isolated DB `.engine/experiments/phase8c1-repair/state.db`.

| | |
| --- | --- |
| `git_commit_sha` | `da5addbcb54495fe2d2fa735159d4f29014a0a53` |
| Score | **33/40 (82.5%)** |
| `false_pass` | **2** |
| `false_unverified` | 5 |
| **Schema failures** | **1** (down from 7) |
| Error rows | 0 |
| Lens calls | 120/120 `ok` |
| Provider failures | 0 |
| Automated gates | **119/120** -- one failure, see §6 |
| Calls / tokens | 120 / 57,558 in, 18,860 out |
| Cost | **\$0.149221** (avg \$0.003731/case) vs \$0.72 conservative max |
| Elapsed | 2026-08-18T01:55:46Z -> 02:00:12Z = **266 s** |

Production `.engine/state.db` sha256 `771e3290...d8219` -- **byte-identical before and after**.

### The repair achieved its stated goal

**Schema failures 7 -> 1.** All 6 Class A eliminated. The surviving 1 is the Class B
truncation on `security-04-clean` x correctness, which was deliberately not targeted.

### But `false_pass` went 0 -> 2

| Case | 8B | 8C | 8C.1 |
| --- | --- | --- | --- |
| `quality-01-broken` | UNVERIFIED | UNVERIFIED | **OK -- false pass** |
| `quality-04-broken` | UNVERIFIED | UNVERIFIED | **OK -- false pass** |

Every lens on both cases emitted only MEDIUM/LOW. On `quality-04-broken` the `correctness`
lens **found the real bug** -- *"The non-member with coupon case does not check the high-value
threshold. According to the task, non-members should get 'coupon_discount'..."* -- and rated
it **LOW**.

### Status of the five original clean failures

| Case | 8B | 8C | 8C.1 |
| --- | --- | --- | --- |
| `correctness-02-clean` | UNVERIFIED | OK | **UNVERIFIED** (regressed back) |
| `edge_case-03-clean` | UNVERIFIED | OK | **UNVERIFIED** (regressed back) |
| `edge_case-04-clean` | UNVERIFIED | OK | OK (held) |
| `security-02-clean` | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| `security-04-clean` | UNVERIFIED | UNVERIFIED | UNVERIFIED |

Two of Phase 8C's three gains did not reproduce one run later at a configuration that changed
nothing about severity assignment. That is direct evidence that the 35 -> 38 movement was
substantially variance, not a measured effect.

---

## 5. Correction to a Phase 8C conclusion

Phase 8C's artifact asked "did fail-closed schema handling inflate the score?" and answered
**no**, on the grounds that every affected broken case also carried surviving blocking defects
from other lenses. That was true of that run's rows, but the inference drawn from it was wrong.

Re-reading the Phase 8C responses: on `quality-01-broken`, **two of three lenses had already
softened to all-MEDIUM** and reached UNVERIFIED only through the schema error; on
`quality-04-broken` the `code-quality` lens had too. Both cases were one lens away from a false
pass, held up by the schema accident rather than by detection. In Phase 8C.1 the last lens
softened as well, and the false pass surfaced.

**Phase 8C.1 did not introduce the false passes. It removed the accident that was hiding
them.** The severity-reordering intervention erodes blocking margin on broken cases too, and
Phase 8C's headline `false_pass = 0` depended on that concealment.

---

## 6. Incidental: DF-1 recurred and diagnosed itself

`edge_case-05-clean` x `mypy` recorded:

```
(no output, exit 3221225477)
```

`3221225477` = `0xC0000005` = **STATUS_ACCESS_VIOLATION** -- the `mypy` subprocess crashed.
Under the pre-Phase-8A code this would have been stored as `detail = "ok"` on a failed gate,
exactly the ambiguous sentinel DF-1 described, and `DEFERRED_FIXES.md` recorded the root cause
as *"currently undiagnosable"* because the return code was discarded. **First recurrence since
the fix, and it identified its own cause immediately.**

Consequence for this run: `edge_case-05-clean`'s UNVERIFIED is an **infrastructure failure, not
judge behaviour** (per the schema reference, a gate failure means environment contamination).
It does not affect either false pass.

---

## 7. Acceptance rule

| Condition | Result |
| --- | --- |
| `false_pass = 0` | **FAIL** -- 2 |
| All 20 broken cases remain UNVERIFIED | **FAIL** -- `quality-01-broken`, `quality-04-broken` scored OK |
| Stale verdict/severity schema failures eliminated | **PASS** -- 6 of 6 gone, 7 -> 1 |
| No new unjustified regression | **FAIL** -- false passes are the failure mode the benchmark exists to catch |
| Phase 8C improvement substantially preserved | **FAIL** -- 2 of 3 gains did not reproduce |

**Acceptance fails.** Not because the repair was wrong -- it did exactly what it was
specified to do -- but because it exposed that the Phase 8C intervention it was repairing is
unsafe.

---

## 8. Revert

Both commits were reverted, on the reasoning that reverting only `da5addb` would restore a
state that *both* discards valid findings on ~7 responses per run **and** retains Phase 8C's
latent false-pass exposure, hidden again rather than fixed. `e967612` is the only state with
no known safety defect.

Verified after the revert: `git diff e967612 -- src/` and `git diff e967612 -- tests/` both
return **empty** -- byte-identical to the Phase 8B baseline engine.

`ruff` clean - `mypy` clean (44 source files) - **`pytest` 150 passed**.

---

## 9. Dataset freeze and safety confirmations

- `git diff f79353c -- src/engine/eval/dataset.py` -> **EMPTY**, before the change, after the
  change, and after the revert.
- No task, fixture, label, expected verdict, expected category or P1/P2/P3 policy touched. No
  case id or benchmark-specific exception in production logic at any point.
- Production `.engine/state.db` never opened for writing; sha256 identical before and after.
- Not pushed. No PR. No previous commit amended.
- Cost of this phase: **\$0.149221**, one run.
