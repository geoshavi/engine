# Phase 8D.1 -- Deterministic Factual-Failure Targeting

**Outcome: reverted, unevaluated.** The intervention was designed, implemented,
tested and committed; the single validation run crashed at case 36 of 40 on an
unrelated persistence bug, and case 36 was one of the two target cases. The
acceptance rule was therefore never applied. The persistence bug is fixed and kept;
the judge change is reverted and deferred.

---

## 1. Starting state

| | |
| --- | --- |
| Starting `HEAD` | `53d8a4273dff7964a596fb604effa3e89d55f680` |
| Dataset checkpoint | `f79353c65099561854e63ed2a8b8e23aaa2c58ce` |
| `BENCHMARK_VERSION` / `DATASET_VERSION` | `v2` / `v4` |
| Judge model | `anthropic` / `claude-haiku-4-5-20251001` |

### Pre-change safety gate

| Check | Result |
| --- | --- |
| `git rev-parse HEAD` | `53d8a427...` -- as required |
| `git status --porcelain` | **empty** |
| `git diff --stat` | **empty** |
| `git diff f79353c -- src/engine/eval/dataset.py` | **EMPTY** |

All four passed. Nothing was written before this gate cleared.

---

## 2. Stability evidence relied on

From `.engine/experiments/phase8d0-stability/PHASE8D0_V2_STABILITY_REPORT.md`,
five runs at `53d8a427`, dataset frozen:

| Statistic | Value |
| --- | --- |
| Scores | 36, 35, 35, 35, 35 |
| Mean | 35.200 / 40 |
| Sample SD | **0.4472** |
| False-pass events | **0 / 100** broken-case observations |
| Deterministic cases | 39 of 40 |

Target cases and their measured baseline rates:

| Case | Rate at `53d8a427` |
| --- | --- |
| `correctness-02-clean` | **0/5** |
| `edge_case-03-clean` | **0/5** |

Out of scope by instruction and untouched: `security-02-clean` (0/5),
`security-04-clean` (0/5), `edge_case-04-clean` (1/5).

---

## 3. Read-only autopsy -- 10 stored observations

No provider call was made for this section. Sources: the five Phase 8D.0 run
databases plus the Phase 8B baseline database, all read from copies or read-only
connections.

### 3.1 `correctness-02-clean`

**Task (verbatim).** *"Implement is_close_enough(a, b) -> bool for comparing
currency amounts: return True when the two values differ by less than 0.01, and
False otherwise. A difference of exactly 0.01 is not close enough."*

**Supplied code.** `return abs(a - b) < 0.01`

**The blocking claim, 5/5 runs, always the `correctness` lens at HIGH:**

| Run | Blocking claim (from the stored `fix` text) |
| --- | --- |
| 1 | "...only if floating-point precision is not a concern. For currency, consider using the `decimal` module or rounding: `round(abs(a - b), 2) < 0.01` to avoid floating-point representation errors that could cause incorrect comparisons near the 0.01 boundary." |
| 2 | "...consider using the `decimal` module or rounding... Alternatively, use `abs(a - b) < 0.01 - 1e-9`... or better yet, convert to cents (integers) before comparison." |
| 3 | "...consider using the `decimal` module or multiplying by 100 to work with integers... Alternatively, document that this implementation assumes inputs are already rounded to cent precision." |
| 4 | "...consider using the `decimal` module or rounding to avoid floating-point arithmetic errors." |
| 5 | (identical in substance to run 4) |

A second, non-blocking `code-quality` MEDIUM appears in all 5 runs: extract `0.01`
to a named constant. It is not the cause -- MEDIUM does not block.

**Frequency.** 5/5 in Phase 8D.0, plus 1/1 at the Phase 8B baseline: **6/6**.
Severity HIGH every time, category CORRECTNESS, lens `correctness`, location
`solution.py:2`.

**Why the claim is wrong.** The task states the predicate exactly: strictly less
than 0.01, with exactly 0.01 excluded. `abs(a - b) < 0.01` *is* that predicate. The
finding names no input at which the code returns the wrong answer for the stated
rule. What it actually proposes -- `decimal`, integer cents, rounding, a 1e-9
epsilon -- are different representations of currency, i.e. an alternate
implementation the task did not ask for. Note also that three of the five proposed
"fixes" (`round(abs(a - b), 2) < 0.01`, cents comparison, the epsilon subtraction)
would change the boundary the task explicitly pins down, so the remedy is further
from the specification than the code being flagged.

### 3.2 `edge_case-03-clean`

**Task (verbatim).** *"Implement truncate(text, max_chars) -> str that shortens
text to at most max_chars characters, without corrupting multi-byte Unicode
characters."*

**Supplied code.** `return text[:max_chars]`

**The blocking claim, 5/5 runs, from *two* lenses at HIGH:**

| Run | Lens | Blocking claim |
| --- | --- | --- |
| 1 | correctness | "Use `text.encode()[:max_chars].decode(errors='ignore')`... to avoid truncating in the middle of multi-byte UTF-8 sequences, which corrupts the text" |
| 1 | code-quality | "Python's string slicing by character count can split multi-byte Unicode characters (e.g., emoji, combining marks)." |
| 2 | correctness | "...can split surrogate pairs or multi-byte sequences when the underlying bytes are truncated mid-character." |
| 2 | code-quality | "...slicing at arbitrary positions can split characters. Use `text.encode('utf-8')[:max_chars].decode('utf-8', errors='ignore')`" |
| 3 | correctness | "...can split surrogate pairs and combining characters, corrupting the output." |
| 3 | code-quality | "Python's string slicing operates on code points, not bytes, and will corrupt multi-byte UTF-8 sequences when sliced mid-character." |
| 4 | correctness | "...can split a multi-byte character in the middle when the underlying bytes are truncated, causing corruption or decoding errors." |
| 4 | code-quality | (identical to run 3) |
| 5 | correctness | "Use `text.encode('utf-8')[:max_chars].decode('utf-8', errors='ignore')`..." |
| 5 | code-quality | (identical to run 3) |

**Frequency.** 5/5 in Phase 8D.0 from both lenses, plus 1/1 at Phase 8B from both:
**6/6 per lens, 12 blocking findings in 6 observations.** Both HIGH every time.
Both self-report category CORRECTNESS -- meaning the `code-quality` lens emitted a
CORRECTNESS-labelled blocker, a lens/category disagreement the schema permits.

**Verified: the judge does treat Python `str` slicing as byte slicing.** Yes, and
run 3's `code-quality` text states both halves of the contradiction in one
sentence -- *"operates on code points, not bytes, and will corrupt multi-byte UTF-8
sequences"*. The premise is correct and the conclusion does not follow from it.

**Why the claim is wrong.** `str` in Python 3 is a sequence of code points; slicing
selects whole code points and cannot split an encoded sequence, because no encoding
is involved. `max_chars` is a character count, so slicing is also the correct unit.
The prescribed remedy, `text.encode(...)[:max_chars].decode(...)`, is **verbatim
this task's own broken fixture** -- the judge's fix converts the clean solution into
the defective one it is meant to detect. (It would also silently change the unit
from characters to bytes.)

### 3.3 Shared root cause

| | |
| --- | --- |
| **Engine stage** | Judge prompt contract -- `RESPONSE_INSTRUCTION` in `src/engine/verification/judge.py`, shared by all three lenses |
| **Shared or separate** | **Shared.** One mechanism, two surfaces |

The defect object the judge must emit is
`{id, category, severity, location, fix}`. It has a field for *where* the problem
is and a field for *what to change*, and **no field for what the code actually does
wrong**. Nothing in the contract asks the finding to exhibit the behaviour it
asserts. The justification therefore lands in `fix`, which is a prescription, so the
contract rewards proposing an alternative over demonstrating a violation -- and a
blocking severity can be assigned to an assertion that was never tested against the
code.

Both failures are that gap, in the two shapes it takes:

- `correctness-02-clean` -- an **implementation preference** (use decimal, use
  cents) escalated to HIGH with no input at which the supplied code misbehaves.
- `edge_case-03-clean` -- a **representation-level assertion** about a lower layer
  the language handles on the code's behalf, escalated to HIGH, factually false,
  with no input at which the supplied code misbehaves.

Neither is a severity-ordering problem (Phase 8C) or a verdict-consistency problem
(Phase 8C.1). In all 12 blocking findings the model's `verdict` string agreed with
its own severities, and no finding retracted itself in its `fix` text.

---

## 4. Intervention

One change, `RESPONSE_INSTRUCTION` only, appended:

> Before assigning CRITICAL or HIGH, name in the fix field the concrete input or
> condition that makes the code as supplied misbehave: what it produces there, and
> why that result is wrong or unsafe. A finding you cannot trigger that way --
> because you would have written the code differently, or because of a lower-level
> representation the language already handles on the code's behalf -- is at most
> MEDIUM. Where the trigger is real, give the finding the severity it deserves.

Properties, against the brief's requirements:

| Requirement | How it is met |
| --- | --- |
| Applies to arbitrary review tasks | No case id, fixture string, filename, constant, language feature or task keyword appears in it |
| Requires an actual task-visible defect | The trigger must be *named*, not asserted |
| Preserves genuine float-boundary bugs | A real boundary bug has a nameable input (`a=1.00, b=1.01`) |
| Preserves genuine encoding/byte bugs | Real byte truncation has a nameable input that raises or corrupts |
| Preserves security behaviour | "wrong **or unsafe**" keeps vulnerabilities blocking without needing the task to forbid them |
| Preserves false-pass safety | Broken fixtures all have nameable triggers; the final sentence blocks one-way softening |
| Not "be less strict" | It is a conditional evidence requirement, and the last sentence explicitly refuses a blanket downgrade |

**Deliberately not Phase 4.** Commit `be990c7` (reverted at `64518fe`) appended a
source-verification plus unstated-requirement rule to the same constant and was
**not supported** at n=8 vs n=8: mean 33.000 -> 32.625, `false_unverified` 5.11 ->
5.38, no always-fail clean case moved, and `security-03-clean` fell 100% -> 37.5%.
That wording told the model to check its finding and to ignore unstated
requirements. This one demands a triggering input instead -- a different
mechanism, and roughly a third shorter. Phase 8C's severity reordering and Phase
8C.1's verdict normalization are **not** reintroduced; the JSON key order,
`enforce_critic_schema`, `rubric.BLOCKING` and `verdict.merge`/`gate` are untouched.

---

## 5. TDD evidence

9 tests added to `tests/test_verification.py`.

**Observed RED before the production change** -- 2 contract tests, failing on the
prompt actually transmitted to each lens, not on the module constant:

```
FAILED test_every_lens_is_told_a_blocking_severity_needs_a_named_trigger
  assert 'concrete input or condition' in '...never invent a more specific
  label. return {"defects": [], "verdict": "ok"} if you find nothing to flag.'
FAILED test_the_trigger_requirement_does_not_soften_a_demonstrated_defect
2 failed, 7 passed
```

**Stated plainly: the other 7 pass before *and* after.** They are preservation
guards, not RED-first tests -- their purpose is to prove `verdict.gate()` semantics
did not move. Presenting them as TDD RED would be false.

| Test | Class | Requirement |
| --- | --- | --- |
| strict tolerance flagged only as a representation preference | positive, float | non-blocking -> OK |
| `<=` where the task requires `<` | **negative, float** | HIGH -> **UNVERIFIED** |
| character-count slicing miscalled byte slicing | positive, string | non-blocking -> OK |
| encoded-byte truncation splitting a sequence | **negative, string** | HIGH -> **UNVERIFIED** |
| CRITICAL security finding | retained | **UNVERIFIED** |
| blocker among non-blocking siblings | retained | **UNVERIFIED** |
| malformed critic response | retained | fails closed -> **UNVERIFIED** |

**Limit, stated up front: deterministic tests cannot show the model complies.**
They show the requirement reaches all three lenses and that gate semantics are
unchanged. Only a benchmark run can show compliance -- which is exactly what did
not survive.

### Deterministic validation before the run

| Gate | Result |
| --- | --- |
| targeted new tests | 9 passed |
| `ruff check .` | All checks passed |
| `mypy src` | Success, 44 source files |
| `pytest` (full) | **159 passed** |
| `git diff f79353c -- src/engine/eval/dataset.py` | **EMPTY** |

`ruff format --check` reports 29 files repo-wide including both files touched here.
Verified pre-existing: the same two files fail it at `53d8a42` as well. `ruff check`
is the project's gate (`verification/automated.py`); reformatting would be an
out-of-scope drive-by edit and was not done.

**Provenance commit:** `12c05483c5ec012d58047696ed1c904474dac908`, created before
the run so `get_git_commit_sha()` (which records `HEAD`, not the working tree)
stamps the run with the code that produced it.

---

## 6. Validation run -- crashed at case 36 of 40

One run, from the clean committed tree at `12c0548`, into an isolated database.

```
UnicodeEncodeError: 'utf-8' codec can't encode character '\ud83d'
  in position 269: surrogates not allowed
  at db.record_eval_case_defects  (src/engine/state/db.py:491)
  via run_benchmark               (src/engine/eval/runner.py:330)
```

**Mechanism.** `json.loads` accepts an unpaired UTF-16 surrogate -- a model
escaping an emoji as a surrogate pair and running out of tokens mid-pair emits
exactly that -- and yields a `str` Python carries happily. `sqlite3` then encodes
its bound parameters to UTF-8, where a lone surrogate is not representable, and
raises. Nothing caught it, so it propagated out of `run_benchmark` and killed the
process. Reproduced in two lines.

**The crash landed on `edge_case-03-clean`** -- case 36, the dataset's
Unicode-truncation task, and one of the two targets. Quoting a concrete emoji input
is the natural thing to write there, and the new clause asks precisely for a
concrete input. The bug is pre-existing and latent; the intervention raised the
probability of tripping it.

| | |
| --- | --- |
| Cases computed and recorded | **35 / 40** |
| Cases lost | 5 -- `edge_case-03-clean`, `edge_case-04-broken/clean`, `edge_case-05-broken/clean` |
| Error rows | 0 |
| Lens calls | 105/105 `ok` |
| Automated gates | 105/105 passed |
| Schema failures | 1 (`correctness` lens, "response did not contain a JSON object") |
| Provider failures | 0 |
| LLM calls | 105 -- 54,640 in / 18,659 out |
| **Cost** | **$0.147935** |
| Elapsed | 4 min 11 s (06:54:44Z -> 06:58:55Z) |

`total_cases` / `correct_verdicts` in the `eval_runs` row are 0: `_aggregate()`
never ran.

### Target-case status: before and after

| Case | Baseline | Intervention run | |
| --- | --- | --- | --- |
| `correctness-02-clean` | 0/5 FAIL | **FAIL** | still failing |
| `edge_case-03-clean` | 0/5 FAIL | **not recorded** | crashed on this case |
| `security-02-clean` | 0/5 FAIL | FAIL | untargeted, unchanged |
| `security-04-clean` | 0/5 FAIL | FAIL | untargeted, unchanged |
| `edge_case-04-clean` | 1/5 | not recorded | untargeted |

**The acceptance rule cannot be applied.** It requires at least one target to flip.
One target is known not to have flipped; the other has no result.

### False-pass safety, as far as the run got

| | |
| --- | --- |
| Broken cases recorded | 18 of 20 |
| Recorded broken cases returning OK | **0** |
| `edge_case-04-broken`, `edge_case-05-broken` | not reached |

No false pass in anything observed. This is not proof of the guardrail across the
full set, because two broken cases never ran.

### Diagnostic observations -- explicitly not results

These come from a truncated run inspected after the fact. They are recorded because
they are informative for the next phase, and they are **not** experimental
findings.

**1. Blocking severity mass did not move.** Over the 35 case ids recorded in both
arms:

| Arm | Defects | Blocking (CRITICAL/HIGH) |
| --- | --- | --- |
| Baseline runs 1-5 | 91, 94, 91, 95, 92 (mean 92.6) | 70, 70, 70, 72, 70 (**mean 70.4**) |
| Intervention | 88 | **70** |

**2. The demonstrability requirement can be satisfied by a fabricated
demonstration.** This is the phase's most useful observation. On
`correctness-02-clean` the intervention produced *three* defects instead of the
baseline's stable two, including a **new blocking finding from the `security`
lens**, and both blockers now do name a concrete input -- exactly the form the
clause demanded:

> `correctness` HIGH: *"Example: is_close_enough(0.1 + 0.2, 0.3) currently returns
> False due to floating-point representation error (0.1 + 0.2 =
> 0.30000000000000004), but should return True..."*

> `security` HIGH: *"With currency amounts like a=0.29, b=0.19, abs(a - b) may not
> equal exactly 0.10 due to floating-point rounding errors..."*

The first example is simply false: `0.1 + 0.2` and `0.3` differ by about 5.6e-17,
so the supplied code returns `True`, not `False`. The model met the letter of the
requirement by inventing a trigger rather than by retracting a finding it could not
trigger. A rule that demands evidence gets evidence-shaped text; it does not get
verified evidence. Any successor should assume this failure mode and design against
it.

---

## 7. Safety confirmations

**Production database not mutated.**

| | Before | After |
| --- | --- | --- |
| sha256 | `771e32904b9f100ebea79b8626b332cf794694872642f602b6b304b4c17d8219` | **identical** |
| size | 3,092,480 B | **identical** |

The run wrote only to
`.engine/experiments/phase8d1-factual-grounding/state.db` via `ENGINE_DB_PATH`.

**Dataset frozen.** `git diff f79353c -- src/engine/eval/dataset.py` -> **EMPTY**,
before the change, before the run, and after the revert.

**Scope.** No benchmark task, fixture, label, expected verdict or expected category
was touched. `security-02-clean`, `security-04-clean` and `edge_case-04-clean` were
read for context only and never optimized against.

**Cost of the phase.** $0.147935, one crashed run. No second run was made.

---

## 8. Decision

**Reverted.** Not because the acceptance rule failed, but because it could not be
evaluated -- the crash destroyed one target's result and the other target had not
moved.

| Commit | |
| --- | --- |
| `12c0548` | Phase 8D.1 factual-grounding intervention |
| `bee3a0a` | Harden defect persistence against unpaired surrogates -- **kept** |
| `c46be45` | Revert "Phase 8D.1 factual-grounding intervention" |

The persistence fix is kept and the judge change is reverted, so the measured path
returns to the safe engine while the crash that blocked this phase cannot recur.
Verified: `git diff 53d8a42 -- src/` shows `src/engine/state/db.py` and nothing
else; all nine measured-path files are byte-identical to `53d8a42`.

`bee3a0a` adds `_sqlite_safe()` (`backslashreplace` at the write boundary) to both
defect writers and the schema-failure writer, with 3 tests -- both surrogate tests
observed RED with the exact production error, and a counterexample proving a
well-formed astral character round-trips byte for byte. `ruff` clean, `mypy` clean,
162 passed.

**Not carried forward as evidence.** The 35 recorded cases were seen after the
fact, so re-running the same intervention would not be blind and the truncated
results cannot serve as an experimental arm. The hypothesis needs a fresh
pre-registration.

### What survives this phase

1. The autopsy: 6/6 deterministic observations per target, a shared root cause
   located in the defect contract, and the finding that the judge's prescribed fix
   for `edge_case-03-clean` is that task's own broken fixture.
2. A closed infrastructure bug that could have silently truncated any future run.
3. The observation that a demonstrability requirement invites fabricated
   demonstrations, and that blocking severity mass did not move.

### Recommended next phase

**8D.2 -- re-registered factual grounding, blind, on top of `bee3a0a`.** Suggested
changes to the design, given what was learned:

- Register **n = 5 per arm**, not 1. The measured SD of 0.447 makes the aggregate
  cheap to read, but the primary metric is the per-case rate, where 0/5 -> 5/5 is
  the only unambiguous signal available at this N.
- Add a pre-registered guardrail on **defect count and blocking mass**, not only on
  verdicts. This run showed a blocking finding being *added* to a target case while
  the aggregate blocking mass held constant -- invisible to a verdict-only metric.
- Treat "did the finding's named trigger actually hold?" as a measured quantity.
  The fabricated `0.1 + 0.2` example is checkable by hand and would have been the
  clearest signal in this run had it completed.
- Consider addressing the contract gap directly -- a required field for the
  observed wrong behaviour, separate from `fix` -- rather than instructing around
  it. That is a larger change touching `schema.py` and the DB, and it should be its
  own phase with its own fail-closed analysis, since a new required key raises
  schema-failure exposure.
