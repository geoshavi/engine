# Phase 8E.0 -- Safe Improvement Selection Gate

**Read-only selection. No source, test, dataset or prompt was modified; no benchmark
was run; no provider was called; nothing was committed. Cost: $0.00.**

**Result: `NO_SAFE_TARGET`.** All four stable failures classify as
`NO_SAFE_GENERAL_FIX` under the constraints in §3-§4. The recommendation is to
package at the proven 35.2/40 safe baseline.

---

## 1. Safety baseline

| Check | Result |
| --- | --- |
| `HEAD` | `0f947e401a173163d12bd735f45f74276004ad7a` |
| `git status --porcelain` | **empty** |
| `git diff f79353c -- src/engine/eval/dataset.py` | **EMPTY** |
| Production `.engine/state.db` | `771e3290…4c17d8219`, 3,092,480 B, mtime unchanged |

**Active runtime verdict path is byte-identical to the proven safe engine
`53d8a42`.** `git diff 53d8a42` is empty for `judge.py`, `pipeline.py`,
`verdict.py`, `schema.py`, `rubric.py`, `automated.py`, `dataset.py`,
`gateway.py` and `budget.py`.

### Inactive / rejected prototype code, reported separately

| Path | Status |
| --- | --- |
| `verification/witness.py`, `verification/witness_runner.py` | **INACTIVE.** `apply_witness_verification` has **no production caller** -- verified by grep. The rejected mechanism cannot execute |
| `eval/witness_log.py` + `runner.py` (+10 lines) | **ACTIVE but passive.** Diagnostics only, written after every commit, cannot reach a verdict. With the mechanism unwired it records every defect as `NO_WITNESS` |
| `state/db.py` (+35/-11) | **ACTIVE.** The Phase 8D.1 unpaired-surrogate persistence fix. Off the measured path |

Only `db.py` changes runtime behaviour relative to `53d8a42`, and only by
preventing a crash while writing diagnostics.

---

## 2. The four stable failures

Evidence: 6 stored safe-baseline observations each -- Phase 8B plus all five Phase
8D.0 runs.

### 2.1 `correctness-02-clean` -- 0/6

**Task:** *"return True when the two values differ by less than 0.01... A
difference of exactly 0.01 is not close enough."*
**Code:** `return abs(a - b) < 0.01`

| | |
| --- | --- |
| Recurring blocker | *"only if floating-point precision is not a concern. For currency, consider the `decimal` module or rounding"* |
| Frequency | **6/6**, always exactly **one** blocking defect |
| Lens / severity / category | `correctness` / HIGH / CORRECTNESS |
| Factually correct? | The premise is true (binary floats are inexact); the conclusion is not -- no input is named at which the code answers the stated rule wrongly |
| Violates the stated task? | **No.** The code *is* the stated predicate |
| Classification | **C -- implementation preference treated as defect.** Three of the proposed remedies (`round(abs(a-b),2) < 0.01`, integer cents, `< 0.01 - 1e-9`) would themselves move the boundary the task pins down |

### 2.2 `security-02-clean` -- 0/6

**Task:** *"Implement convert_to_png(filename) that shells out to an image
converter to produce filename + '.png'."*
**Code:** rejects empty / `..` / `/`, then `subprocess.run(["convert", filename,
f"{filename}.png"], check=True)` -- **list form, no `shell=True`**.

Three blocking defects, all 6/6, all `lens == category`:

| Lens | Claim | Factual? | Class |
| --- | --- | --- | --- |
| `security` HIGH | *"attacker can still inject shell metacharacters like ';', '\|', '&', '$', '`'"* | **False.** No shell is invoked; the same sentence concedes *"use subprocess.run() with a list (already done correctly)"* and still rates HIGH | **A** factual runtime misunderstanding |
| `security` HIGH | *"output filename constructed by concatenation... 'image.png; rm -rf /'"* -- while conceding *"not directly executed due to list-based subprocess call"* | **False as a vulnerability**, self-conceded | **A/B** |
| `correctness` HIGH | *"FileNotFoundError is not caught if 'convert' is not installed"* | **TRUE** | **B** unstated requirement -- the task says nothing about a missing converter, and the "expected RuntimeError" is the model's own invention |

**Reported for the record, not as a recommendation:** the third blocker is
factually correct and is not contradicted by the task. A strict adversarial
reviewer flagging an uncaught `FileNotFoundError` in code that shells out is
defensible. This case may be inherently hard to score as "clean" -- a
benchmark-design observation. **The dataset is frozen and must not be edited to
suit the engine.**

### 2.3 `security-04-clean` -- 0/6

**Task** (v2 wording, explicit): *"...The caller connects to the address you return
and does not look the host up again, so the address you return must be one you
checked."*
**Code:** resolves via `getaddrinfo`, requires **all** addresses public, returns
`addresses[0]`.

2-5 blocking defects per run, **all `lens == category`**, and -- unlike the other
three -- **the claim content changes run to run**:

| Recurring claim | Frequency | Factual? | Class |
| --- | --- | --- | --- |
| *"returns addresses[0] without verifying it's actually public"* | 4/6 | **False** -- `all(_is_public(...))` was checked, so `addresses[0]` is public. Directly contradicted by the supplied code | **A** |
| *"TOCTOU: attacker's DNS returns public at check time, private at connect time"* | 3/6 | **Excluded by the stated task**, which says the caller does not re-resolve | **D** contract misunderstanding |
| *"DNS returns [private_ipv6, public_ipv4]; validation passes"* | 4/6 | **False** -- `all()` returns None if any address is private | **A** |
| IPv6 scope-id / bracket-notation / "loses port information" | 4/6 | Speculative or spec-irrelevant | **B/C** |

### 2.4 `edge_case-03-clean` -- 0/6

**Task:** *"shortens text to at most max_chars characters, without corrupting
multi-byte Unicode characters."*
**Code:** `return text[:max_chars]`

| | |
| --- | --- |
| Recurring blocker | *"Python's string slicing can split multi-byte UTF-8 sequences / surrogate pairs, corrupting the text"* |
| Frequency | **6/6 from two lenses** -- `correctness` HIGH and `code-quality` HIGH (12 blocking findings in 6 observations) |
| Factually correct? | **No.** `str` is a sequence of code points; slicing cannot split an encoding, because no encoding is involved |
| Classification | **A -- factual runtime misunderstanding.** Its prescribed fix, `text.encode()[:max_chars].decode(...)`, is **verbatim this task's own broken fixture** |
| Note | The `code-quality` lens self-reports category `CORRECTNESS` -- the only lens/category mismatch among all four targets |

---

## 3. Fixability test

Every candidate must avoid: weakening HIGH/CRITICAL globally, changing verdict
authority, changing schema semantics, an extra LLM call, new model-supplied
evidence fields, case IDs, fixture matching, broad prompt calibration, or
generated-code execution.

### 3.1 The structural constraint

`verdict.gate` decides on **severities alone**. To change a verdict you must
change the severity set the gate sees. Within the allowed fix types that leaves
exactly one route: a deterministic filter over **data the run already produced**.
Everything else routes through the model's behaviour, i.e. a prompt change --
excluded by §0 and §4, and already falsified twice.

Note the corollary for allowed type **D**: a "task/spec grounding mechanism that
does not change severity authority" cannot change any verdict, because the gate
reads nothing but severity. Type D is empty by construction for this problem.

### 3.2 The only existing-data signal, measured

The one general, deterministic signal available in stored data is
**lens/category disagreement** -- a defect emitted by lens L whose self-reported
category is not L's dimension, contradicting that lens's own system prompt
("Ignore correctness and security -- those are reviewed separately"). It needs no
new model output, no extra call, no execution. `benchmark-analysis` names it as a
measurable property.

**Measured across all 6 stored observations:**

| Target | Blocking defects | `lens == category` | `lens != category` | After dropping mismatched |
| --- | --- | --- | --- | --- |
| `correctness-02-clean` | 1 | 1 | 0 | **still blocks** (6/6) |
| `security-02-clean` | 3 | 3 | 0 | **still blocks** (6/6) |
| `security-04-clean` | 2-5 | all | 0 | **still blocks** (6/6) |
| `edge_case-03-clean` | 2 | 1 | 1 | **still blocks** (6/6) |

**It fixes nothing.** Meanwhile it would touch **172 of 376 (45.7%)** of the
blocking defects on broken cases across five runs. Zero upside, large blast
radius. Rejected on measurement, not on speculation.

### 3.3 Engine-bug candidates (types A / E), checked

| Candidate | Finding |
| --- | --- |
| `schema.py`'s out-of-enum category fail-closed | The module states its own revisit condition: *"revisit ONLY if a future run shows an out-of-enum category as the ONLY lens catching a real defect"*. **0 such failures in 6 observations. Condition NOT met** |
| Schema failure costing a clean case | **1 schema failure in 6 observations** (`security-04-clean × correctness`, a truncation). That case had 2 blocking defects anyway, so the failure did not drive the verdict |
| `judge.py` discarding earlier lenses when a later lens raises (a real defect, documented in the Phase 2.1 scope note) | **Never fired**: 0 error rows and 0 non-`ok` lens calls in all 6 observations. Cannot move any target |
| `max_tokens=800` truncation | Real, but it does not cause any of the four failures -- all four fail on genuine emitted blockers |

No engine bug on the table moves any target case.

### 3.4 Steelman: a narrow static-semantics rule (type C)

The strongest remaining idea is an AST check -- e.g. *"downgrade a SECURITY
blocker alleging shell injection when `subprocess` is called with a list and
`shell=False`."*

It fails on its own terms, measurably: `security-02-clean` carries **three**
blocking defects, and such a rule addresses at most the two shell-metacharacter
ones. The `correctness` lens's `FileNotFoundError` blocker is present **6/6** and
is factually true, so **the case would still fail**. The same holds for
`edge_case-03-clean`, where both lenses would have to be silenced. And
identifying *which* claim a defect makes requires matching its prose -- a keyword
matcher against a dataset built explicitly to defeat keyword matching.

### 3.5 Classification

| Target | Class |
| --- | --- |
| `correctness-02-clean` | **NO_SAFE_GENERAL_FIX** |
| `security-02-clean` | **NO_SAFE_GENERAL_FIX** |
| `security-04-clean` | **NO_SAFE_GENERAL_FIX** |
| `edge_case-03-clean` | **NO_SAFE_GENERAL_FIX** |

No target reaches `SAFE_CANDIDATE`; none reaches `RISKY_CANDIDATE` with a
concrete mechanism attached, because no admissible mechanism exists to attach.

---

## 4. Broken-case counterfactual -- the decisive finding

For each target, the stored blockers on its **broken twin** were compared with the
false blockers on the clean case. Word-overlap of the closest pair, against a
baseline of blockers drawn from unrelated tasks:

| Task pair | Max overlap | vs baseline (mean 0.021, max 0.087) |
| --- | --- | --- |
| `edge_case-03` | **0.286** | 13.6x the baseline mean |
| `security-04` | **0.164** | 7.8x |
| `security-02` | **0.143** | 6.8x |
| `correctness-02` | 0.065 | below the unrelated maximum |

For three of the four, **the false blocker on the clean case and a genuine blocker
on its broken twin are substantially the same claim**:

| | Clean case (must be demoted) | Broken twin (must keep blocking) |
| --- | --- | --- |
| `security-02` | *"attacker can still inject shell metacharacters"* | *"An attacker can inject arbitrary shell commands (e.g. 'image.jpg; rm -rf /')"* |
| `edge_case-03` | *"Use `text.encode()[:max_chars].decode(errors='ignore')`"* | *"Use errors='ignore' ... in decode() to handle incomplete multi-byte sequences"* |
| `security-04` | *"returns the first address without verifying it matches the host lookup"* | *"must validate that the resolved address is not in a private/internal range"* |

The only thing separating them is a **fact about the code** -- `shell=True` versus
the list form, `str` slicing versus `bytes` slicing, validated versus unvalidated.
Establishing that fact deterministically requires either executing the code
(**rejected in Phase 8D.2C: 26 false passes in 100 broken-case observations**) or
asking a model (**excluded by §3 and §4**).

**Therefore any filter strong enough to clear the clean case will, by
construction, clear its broken twin.** `security-02-broken` and
`security-04-broken` are exactly the SSRF and command-injection anchors the
benchmark exists to protect, and `edge_case-03-broken` is a genuine encoding
defect. Under §5, all three targets are downgraded on false-pass risk with no
deterministic guard available.

`correctness-02` is the one pair that is textually separable -- but separability
of *text* is not a mechanism. Its distinguishing feature is semantic (a preference
for decimal arithmetic versus a genuine `==`-instead-of-tolerance bug), and any
rule keyed on wording is prose matching.

---

## 5. Ranking -- safest to most dangerous to attempt

Ranked on generality, deterministic verifiability, false-pass risk,
implementation size, regression surface, evidence strength, and whether the same
mechanism has already failed. **Not** on which would yield a benchmark point
fastest.

**1. `correctness-02-clean` -- least dangerous, still no mechanism.**
Single blocking defect (lowest bar of the four); claim textually distinct from its
broken twin; concept (an implementation preference is not a defect) is fully
general. But: no deterministic signal separates preference from defect; Phase
8D.1's demonstrability prompt is banned and failed; Phase 8D.2C refuted its
blocker and the case *still* failed, because a second lens produced a true
observation carrying a false inference.

**2. `edge_case-03-clean`.**
The claim is unambiguously false about Python semantics and the concept is general
-- the most tractable-looking of the four. But two lenses must both be silenced,
its false blocker is the **most textually similar** to its broken twin's genuine
blocker (0.286, 13.6x baseline), and the one mechanism that ever moved it was
executed witnesses, which produced 26 false passes.

**3. `security-02-clean`.**
Three blockers must all fall, and one of them is **factually true and not excluded
by the task**. Two rest on self-conceded non-exploitability -- Phase 8C territory,
explicitly banned. Its broken twin is the command-injection anchor.

**4. `security-04-clean` -- most dangerous.**
The blocker *content* is unstable run to run (2-5 defects, different claims), so
there is no single recurring claim to target; the claims are SSRF threat-model
assertions; and its broken twin is the SSRF anchor with 9 blocking defects. §8
forbids selecting a security case on threat-model wording alone, and no narrow
general mechanism with stored broken-case safety evidence exists here.

---

## 6. Selection

**`NO_SAFE_TARGET`.**

No target is selected. The constraint set in §3-§4 is not arbitrary -- it encodes
what the last four phases actually measured:

| Phase | Mechanism | Outcome |
| --- | --- | --- |
| 8C | severity reordering | +3 cases, bought with false-pass exposure -- reverted |
| 8C.1 | verdict normalization | 2 false passes in one run -- reverted |
| 8D.1 | demonstrability prompt | fabricated evidence; crashed before evaluation -- reverted |
| 8D.2 | executed witnesses | **26/100 false passes**, -7.4 cases -- rejected |
| 4 | source-verification + task-scope prompt | not supported at n=8 vs n=8 -- reverted |

Five interventions, five reversions. Every one worked by changing what the *model*
produces or how its output is *re-scored*, and the one that changed behaviour most
decisively also broke safety most decisively. What remains permitted --
deterministic filters over existing data -- has been measured here and moves none
of the four.

### Recommendation: package at the safe baseline

**35.2 / 40 (SD 0.447), 0/100 broken-case false passes, 39 of 40 cases
deterministic.** That is an honest description of this configuration, and the
ceiling of 36/40 is set by four clean-case failures whose causes are now
characterised in detail rather than merely observed.

Two of those four are arguably not pure judge errors: `security-02-clean` carries
a factually correct blocker the task never excludes, and `security-04-clean`'s
fixture invites IPv6 and ordering arguments the task does not settle. Recording
that is worth more than another intervention. **It is not a licence to edit the
dataset** -- doing so would tune the benchmark to the engine and destroy
comparability with every prior run.

### Work that remains legitimate, and is not accuracy work

- **Remove the inactive witness prototype** (`verification/witness.py`,
  `witness_runner.py`) or state explicitly that it is retained as a recorded
  experiment. Unreferenced production code is a maintenance hazard.
- **Fix the `judge.py` lens-discard defect** -- a later lens's exception discards
  earlier lenses' critics. It has never fired, so it is a robustness fix with no
  accuracy claim attached, and must not be validated by an accuracy run.
- **`max_tokens=800` truncation on the largest fixture** is real and measured;
  raising it is a cost/behaviour trade, not a fix, and would need its own
  pre-registration.

Each is a code change verified by the automated gates, exactly as `CLAUDE.md`
requires -- **not** by the accuracy column.

---

## 7. Status

**`PHASE_8E0_NO_SAFE_TARGET`**

No implementation. No benchmark. No provider call. Nothing committed. $0.00.
