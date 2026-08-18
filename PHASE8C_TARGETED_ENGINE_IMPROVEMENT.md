# Phase 8C -- Targeted Engine Improvement

Engine/judge only. Benchmark v2 dataset semantics frozen throughout.

| | |
| --- | --- |
| Starting `HEAD` | `e967612992375cd270e36ba7bd8a03a5ab27d2c9` |
| Dataset checkpoint | `f79353c65099561854e63ed2a8b8e23aaa2c58ce` (`v2` / `v4`) |
| Intervention commit | `4954f4af124be01b56fbfc64434993d9e3617b63` |
| Phase 8B baseline | **35/40**, `false_pass` 0, `false_unverified` 5 |
| Phase 8C result | **38/40**, `false_pass` 0, `false_unverified` 2 |

---

## 1. Five-case autopsy (read-only, no provider calls)

Performed against the Phase 8B isolated database and the frozen fixtures. Each finding
below was checked against the actual fixture source.

### `correctness-02-clean` -- expected OK, actual UNVERIFIED

Task: *"return True when the two values differ by less than 0.01 ... A difference of exactly
0.01 is not close enough."* Code: `return abs(a - b) < 0.01`.

- **Blocking lens:** `correctness`, 1 defect, `CORRECTNESS` / **HIGH**.
- **Rationale:** proposes `decimal`, rounding, or integer cents for currency.
- **Classification:** *factually true but irrelevant to task/spec* + *severity inflation*.
  The code implements the stated contract exactly, including the strict `<` boundary the
  task explicitly calls out. The finding is general engineering advice, not a spec failure.
- **Stage:** judge lens severity assignment.
- **Shared root cause:** yes -- with `security-02-clean` C1.

### `security-02-clean` -- expected OK, actual UNVERIFIED

Code uses `subprocess.run(["convert", filename, ...])` -- list form, no shell -- and rejects
`..` and `/`.

- **Blocking lenses:** `correctness` (1x HIGH), `security` (2x HIGH).
- **Rationales:** C1 -- `FileNotFoundError` if `convert` is absent. S1 -- shell
  metacharacter injection, *while stating* "Use subprocess.run() with a list (already done
  correctly)". S2 -- `'image; rm -rf /'` *"which, **while blocked by the current checks**,
  demonstrates the pattern"*.
- **Classification:** S1/S2 are *factually wrong* (no shell is invoked, so metacharacters
  are inert) **and self-retracting** -- each rationale states the mitigation is present.
  C1 is *true but irrelevant to spec* (missing-binary handling is not asked for).
- **Stage:** judge lens severity assignment.
- **Shared root cause:** yes -- S1/S2 with `security-04-clean`; C1 with `correctness-02-clean`.

### `security-04-clean` -- expected OK, actual UNVERIFIED

Code resolves all addresses, returns `None` unless `all(_is_public(a))`, then returns
`addresses[0]` -- an address it checked, satisfying the task's pinning requirement.

- **Blocking lenses:** `correctness` (1x CRITICAL, 2x HIGH), `security` (2x HIGH).
- **Rationales:** C1 concludes verbatim *"Actually, re-reading: the all() check ensures all
  addresses are public before returning addresses[0], so this is safe. **No defect here.**"*
  -- emitted at HIGH. C2 concludes *"so this is actually correct behavior for SSRF
  purposes"* -- emitted at HIGH. C3 concedes the task premise *"which is reasonable"*, then
  pivots to an IPv6-bracket formatting nitpick -- emitted at **CRITICAL**. S1/S2 claim an
  attacker DNS answer of `[private, public]` would pass validation, which **misreads
  `all()`** -- any private address returns `None`.
- **Classification:** *self-retracting blocker* (C1, C2, C3) + *factually wrong* (S1, S2) +
  *severity inflation* (C3).
- **Stage:** judge lens severity assignment.
- **Shared root cause:** yes -- with `security-02-clean` S1/S2.

### `edge_case-03-clean` -- expected OK, actual UNVERIFIED

Code: `return text[:max_chars]` on a `str`.

- **Blocking lenses:** `code-quality` (HIGH, self-labelled CORRECTNESS) and `correctness`
  (HIGH) -- the same claim twice.
- **Rationale:** slicing "can split surrogate pairs or combining characters"; recommends
  `text.encode('utf-8')[:max_chars].decode(errors='ignore')`.
- **Classification:** *factually wrong* / *static-analysis misunderstanding*. Python `str`
  slicing is by code point and cannot split a UTF-8 sequence; the **proposed fix is the
  thing that would corrupt**. The `code-quality` rationale even states the correct fact
  ("operates on Unicode code points") and then contradicts it. Also a *duplicated blocker*.
- **Stage:** judge lens severity assignment.
- **Shared root cause:** yes -- with `edge_case-04-clean` and `security-04-clean` S1/S2.

### `edge_case-04-clean` -- expected OK, actual UNVERIFIED

Code: `if not isinstance(hour, int) or hour < 0 or hour > 23: raise ValueError`.

- **Blocking lens:** `correctness`, 1 defect, **HIGH**.
- **Rationale:** *"The current check rejects hour=23, but 23 is valid per the task
  requirement [0, 23]."*
- **Classification:** *factually wrong*. `23 > 23` is `False`, so 23 is accepted. A plain
  boundary misread.
- **Stage:** judge lens severity assignment.
- **Shared root cause:** yes -- with `edge_case-03-clean`.

---

## 2. Root-cause grouping

Three groups, smallest defensible partition. Every historical hypothesis was **checked
against Phase 8B evidence, not assumed**.

| Root cause | Cases | Historical hypothesis | Verdict on that hypothesis |
| --- | --- | --- | --- |
| **A -- self-retracting blocker.** The `fix` text withdraws the finding; `severity` was emitted three keys earlier and never revised | `security-04-clean` (C1/C2/C3), `security-02-clean` (S1/S2) | "security-04: security-contract misunderstanding after the v2 pinned-address repair" | **Partly wrong.** S1/S2 do misread the contract, but C1/C2/C3 reach the *correct* reading and still block. The dominant defect is unrevised severity, not misunderstanding |
| **B -- spec-irrelevant escalation.** Legitimate general advice rated blocking against a spec that does not ask for it | `correctness-02-clean`, `security-02-clean` C1 | "correctness-02: handling failure around explicit strict threshold semantics" | **Not supported.** The judge never misread the `<` boundary; it accepted it and objected to float arithmetic per se |
| | | "security-02: unstated-threat-model overreach / severity inflation" | **Supported**, and additionally *factually wrong* on the shell claim |
| **C -- factual misreading of language/stdlib semantics** | `edge_case-03-clean`, `edge_case-04-clean`, `security-04-clean` S1/S2 | "edge_case-03: byte-vs-character slicing confusion" | **Supported exactly** |
| | | "edge_case-04: stochastic/over-conservative critic behavior" | **Not supported as stochastic.** The rationale contains a specific, checkable false claim, not vague conservatism |

---

## 3. Intervention

**One intervention, targeting root cause A only.**

`src/engine/verification/judge.py`, `RESPONSE_INSTRUCTION` only:

```diff
 '{"defects": [{"id": "C1", "category": "CORRECTNESS|SECURITY|CODE-QUALITY", '
-'"severity": "CRITICAL|HIGH|MEDIUM|LOW", '
-'"location": "path:line or description", "fix": "what to change"}], '
+'"location": "path:line or description", "fix": "what to change", '
+'"severity": "CRITICAL|HIGH|MEDIUM|LOW"}], '
 '"verdict": "OK|FAIL"}\n'
+"Fill these keys in exactly the order shown. Put your analysis and the concrete change "
+"in \"fix\", then choose \"severity\" last so it reflects the analysis you just wrote: if "
+"what you wrote in \"fix\" concludes the supplied code already handles the case, "
+"\"severity\" is not CRITICAL or HIGH. "
```

**Rationale.** Generation is left-to-right, so a key emitted before `fix` cannot be
conditioned on the analysis written in `fix`. The judge was reaching the right conclusion
*while writing `fix`* and had no way to revise a severity it had already emitted.
`_extract_json_objects` already accommodates this same phenomenon at the object level -- it
deliberately takes the **last** complete JSON object so a model that reconsiders mid-response
is honored. This extends that accommodation from the object level to the field level.

**Why general, not benchmark-specific.** No case id, fixture string, task text or hardcoded
answer appears in production logic. The change is a property of autoregressive generation and
applies to any review the judge performs. `LENSES`, `_extract_json_objects`, `_parse_critic`,
`enforce_critic_schema`, `rubric.BLOCKING` and `verdict.merge`/`gate` are byte-identical.
It changes **when** severity is chosen, never what a chosen severity does -- CRITICAL/HIGH
still blocks unconditionally.

**Root causes B and C were deliberately left untreated.** They map almost exactly onto Phase
4's Mechanism C and Mechanism B (`be990c7`, reverted at `64518fe`), which were measured at
n=8 vs n=8 and **not supported**: mean 33.000 -> 32.625, `false_unverified` rose 5.11 -> 5.38,
none of the four always-fail clean cases moved, and `security-03-clean` fell 100% -> 37.5%.
Re-issuing that instruction would repeat a measured failure.

---

## 4. Deterministic tests

7 tests in `tests/test_verification.py`. **RED observed first** on the contract-order test:
`assert 236 < 156` (`severity` at index 156, `fix` at 236).

| Test | Role |
| --- | --- |
| `test_response_contract_emits_severity_after_the_fix_analysis` | the production change; **RED first** |
| `test_schema_accepts_defect_keys_in_the_new_contract_order` | the reorder must not create schema failures |
| `test_self_retracted_finding_scored_non_blocking_no_longer_blocks` | **positive** -- old false blocker no longer blocks |
| `test_genuine_blocking_defect_still_fails_closed_under_the_new_order` | **counterexample** -- HIGH still blocks |
| `test_critical_defect_still_fails_closed_under_the_new_order` | **counterexample** -- CRITICAL still blocks |
| `test_one_blocking_defect_among_retracted_ones_still_blocks` | **counterexample** -- a real blocker cannot hide behind retracted siblings |
| `test_reorder_does_not_touch_fail_closed_on_schema_or_gate_failure` | both non-defect fail-closed paths intact |

`ruff` clean - `mypy` clean (44 source files) - **`pytest` 157 passed**.

---

## 5. Validation run

Exactly one full 40-case run. No selective rerun, no repeat.

| | |
| --- | --- |
| `git_commit_sha` | `4954f4af124be01b56fbfc64434993d9e3617b63` (tree clean; committed **before** the run so the stamp matches what executed) |
| Isolated DB | `.engine/experiments/phase8c-intervention/state.db` |
| **Score** | **38/40 (95.0%)** |
| `false_pass` | **0** |
| `false_unverified` | **2** |
| Category accuracy | correctness **100%**, quality **100%**, edge **100%**, security 80% |
| Cases / errors | 40 scored / **0 error rows** |
| Lens calls | **120/120 `ok`** |
| Automated gates | **120/120 passed** (`ruff`/`mypy`/`pytest` 40 each), 0 failures |
| **Schema failures** | **7** -- see §7, a real regression |
| Provider failures | **0** (120/120 `status = ok`, 0 errors) |
| Provider calls | 120 |
| Tokens | 57,491 in / 18,784 out |
| Cost | **\$0.151411** (avg \$0.003785/case), vs \$0.72 conservative max |
| Elapsed | 2026-08-18T01:38:16Z -> 01:42:28Z = **252 s** |

Production `.engine/state.db` sha256 `771e3290...d8219` -- **byte-identical before and after**.

---

## 6. Before/after case table

37 of 40 cases unchanged. **3 fixed, 0 regressed.**

| Case | expected | Phase 8B | Phase 8C | change |
| --- | --- | --- | --- | --- |
| `correctness-02-clean` | OK | UNVERIFIED | **OK** | **FIXED** |
| `edge_case-03-clean` | OK | UNVERIFIED | **OK** | **FIXED** |
| `edge_case-04-clean` | OK | UNVERIFIED | **OK** | **FIXED** |
| `security-02-clean` | OK | UNVERIFIED | UNVERIFIED | unchanged |
| `security-04-clean` | OK | UNVERIFIED | UNVERIFIED | unchanged |
| all 20 `-broken` cases | UNVERIFIED | UNVERIFIED | UNVERIFIED | unchanged |
| other 15 `-clean` cases | OK | OK | OK | unchanged |

**False-pass comparison: 0 -> 0.** All 20 broken cases remained UNVERIFIED; none became OK.
`security-03-clean` -- Phase 4's unregistered adverse finding, treated here as a guardrail --
passed in both runs.

### The mechanism is visible in the emitted rationales

The fixed cases show the retraction now landing *before* severity and governing it:

- `correctness-02-clean`, `correctness` lens, now **MEDIUM**: *"However, the core logic is
  correct: `abs(a - b) < 0.01` properly returns True when difference is strictly less than
  0..."*
- `edge_case-03-clean`, all three lenses, now **LOW/MEDIUM/LOW**: *"Python's str type handles
  Unicode correctly at the character level, so `text[:max_chars]` actually works correctly for
  Unicode"* - *"which in Python 3 correctly handles multi-byte Unicode characters"* - *"The
  current implementation is actually correct"*
- `edge_case-04-clean`: no defects emitted at all.

**Honest correction to the pre-run prediction.** The review predicted `security-02-clean`
and/or `security-04-clean` would improve, because those are where the literal self-retractions
("No defect here.") appeared. **Both are still failing.** The three cases that moved were the
ones assigned to root causes B and C. The *mechanism* prediction held -- severity now follows
the analysis -- but the *case-level* prediction was wrong. This is recorded as a partly failed
prediction, not reinterpreted after the fact.

### Severity distribution shift

| | CRITICAL | HIGH | MEDIUM | LOW | total | blocking share |
| --- | --- | --- | --- | --- | --- | --- |
| Phase 8B | 40 | 48 | 17 | 3 | 108 | 81.5% |
| Phase 8C | 43 | 29 | 15 | 6 | 93 | 77.4% |

**HIGH fell 40% while CRITICAL held flat (40 -> 43).** This is not blanket softening: the
most severe band was untouched, which is what "no broad suppression" should look like.

---

## 7. Regression found: schema failures 0 -> 7

**This is a real regression and is not being minimized.**

| Case | Lens | `error_detail` |
| --- | --- | --- |
| `security-02-clean` | security | `verdict: is 'FAIL' but expected 'OK' given the defects` |
| `quality-01-broken` | correctness | same |
| `quality-01-broken` | security | same |
| `quality-02-broken` | correctness | same |
| `quality-04-broken` | code-quality | same |
| `edge_case-03-broken` | code-quality | same |
| `security-04-clean` | correctness | `response did not contain a JSON object` |

Six of seven are the same, directly attributable failure: the model now softens severities
to MEDIUM/LOW after writing its analysis, but still emits `"verdict": "FAIL"` at the end, so
`enforce_critic_schema`'s consistency rule rejects the response. The intervention moved
`severity` but left `verdict` upstream of that decision.

**Did fail-closed schema handling inflate the score?** Checked explicitly, case by case:
**no.** Every affected broken case also carried genuine surviving blocking defects from other
lenses (`quality-01-broken` 1 blocking, `quality-02-broken` 1, `quality-04-broken` 2,
`edge_case-03-broken` 2 CRITICAL), so each would have been UNVERIFIED on defect evidence alone.
No case's verdict depended on the schema path. Both affected clean cases were failing anyway.

Per `baseline-evidence`, schema failures are **recorded, not disqualifying**; the run stands.
But a non-zero count is a regression signal and is flagged as the highest-priority next fix.

---

## 8. Acceptance rule

| Condition | Result |
| --- | --- |
| `false_pass` remains 0 | **PASS** (0 -> 0) |
| No previously correct broken case became OK | **PASS** (20/20 still UNVERIFIED) |
| No new unjustified regression | **PASS with a flagged caveat** -- 7 schema failures are a genuine regression, but no case verdict was wrong because of them and no broken case was rescued by the fail-closed path (§7) |
| At least one of the five corrected | **PASS** (3 of 5) |
| Attributable to a general engine change | **PASS** -- prompt-contract ordering; no case id, fixture string or hardcoded answer in production logic |

**Acceptance rule passes.**

### Statistical honesty

- **n = 1 in each arm.** +3 cases (35 -> 38) cannot be given a confidence interval from two
  single runs. The pooled sigma ~ 0.92 is a **v3** figure carried over from clusters
  `c0515eb`/`be990c7`; **`v2`/`v4` has no measured noise floor at all**, and `4954f4a` opens
  yet another configuration cluster holding one run.
- What raises this above the accuracy column: **two of the three fixed cases
  (`correctness-02-clean`, `edge_case-03-clean`) were 0/9 always-fail** across runs 20-28 at
  v3. Cases that never once passed in nine runs flipping together is a stronger signal than
  the delta itself -- and the mechanism is **directly observable in the emitted rationales**
  (§6), which is the class of evidence this project prefers over aggregate movement.
- `edge_case-04-clean` was historically **borderline** (55.6%, then 37.5%); its flip is well
  inside noise and should not be counted as evidence.
- **This is one run. It is not proof.** Replication at this configuration is required before
  the effect size is quoted as measured.

---

## 9. Remaining failures

- `security-02-clean` -- root causes A + B + C combined; one HIGH `correctness` blocker
  survived ("validation rejects '/' and '..'"), plus a schema failure on the security lens.
- `security-04-clean` -- 4 blocking defects survived (1 `code-quality` HIGH, 3 `security`
  HIGH), plus the `correctness` lens returned no JSON object at all.

Both remain in the historical always-fail set. Neither was addressed by this intervention,
and root causes B and C remain open by design.

---

## 10. Dataset freeze confirmation

- `git diff f79353c -- src/engine/eval/dataset.py` -> **EMPTY**, verified before the change,
  after the change, and after the run.
- No task, fixture, expected verdict, expected category, rubric or P1/P2/P3 policy was
  touched. No case id or benchmark-specific exception exists in production logic.
- Production `.engine/state.db` never opened for writing; sha256 identical before and after.
- Files changed across Phase 8C: `src/engine/verification/judge.py` (RESPONSE_INSTRUCTION
  only) and `tests/test_verification.py`, plus this document.
- Not pushed. No PR. No previous commit amended.
