# Phase 8D.2A -- Verified Evidence Grounding Architecture

**Design only. No production source, test, prompt or dataset file was modified, no
benchmark was run, no provider was called. Cost: $0.00.**

**Verdict: GO**, for one narrow architecture -- an *executed witness* that can only
ever **remove** blocking authority, never grant it.

---

## 1. Baseline and safety

| Check | Result |
| --- | --- |
| `HEAD` | `ec7a9618dcf6cf3946f0afaed1c7a5a827643b33` |
| `git status --porcelain` | **empty** |
| `git diff --stat` | **empty** |
| `BENCHMARK_VERSION` / `DATASET_VERSION` | `v2` / `v4` |
| `git diff f79353c -- src/engine/eval/dataset.py` | **EMPTY** |

**Judge behaviour equivalence to the restored safe engine (`53d8a42`).** All nine
measured-path files are byte-identical:

```
0  src/engine/eval/dataset.py          0  src/engine/verification/verdict.py
0  src/engine/eval/runner.py           0  src/engine/verification/pipeline.py
0  src/engine/verification/judge.py    0  src/engine/runtime/gateway.py
0  src/engine/verification/rubric.py   0  src/engine/runtime/budget.py
0  src/engine/verification/schema.py
```

`git diff 53d8a42 -- src/ tests/` shows exactly two files: `src/engine/state/db.py`
(the intentional Phase 8D.1 persistence fix) and `tests/test_eval_runner.py` (its
three regression tests). `tests/test_verification.py` is byte-identical to the safe
engine.

**Measured stability (Phase 8D.0, five runs at `53d8a42`):** 36, 35, 35, 35, 35;
mean 35.2/40; sample SD 0.447; **0 false passes in 100 broken-case observations**.

---

## 2. What actually failed in Phase 8D.1

The brief's four-way split, confirmed against the stored evidence:

**A. True root cause -- blocking severity can rest on an unchecked factual
assertion.** The critic contract is `{id, category, severity, location, fix}`: a
field for *where*, a field for *what to change*, and none for *what the code
actually does wrong*. Nothing requires a finding to exhibit the behaviour it
asserts. This is unchanged and still true at `HEAD`.

**B. Failed intervention -- asking the model for a concrete demonstration.** The
appended clause required naming "the concrete input or condition that makes the code
as supplied misbehave" before assigning CRITICAL or HIGH.

**C. Observed failure -- the model fabricated a plausible trigger.** On
`correctness-02-clean` it produced *three* defects instead of the stable two,
including a new blocking finding from the `security` lens, and both blockers named
concrete inputs. The `correctness` lens wrote: *"is_close_enough(0.1 + 0.2, 0.3)
currently returns False due to floating-point representation error"*. It returns
`True`.

**D. Safety requirement -- specificity must not confer authority.** A claim that is
concrete, quotable and false must not outrank a vague true one.

### The lesson, stated precisely

Phase 8D.1 put **the policy in the prompt**: it asked the model to decide whether
its own evidence was good enough, and to self-demote. The model was the judge of its
own evidence, so the requirement resolved to "produce evidence-shaped text".

The correction is not stronger wording. It is a change of *location*:

> **The requirement belongs in the prompt. The policy belongs in the engine.**

The prompt asks for evidence. Deterministic engine code -- never the model --
decides what that evidence is worth.

---

## 3. What "verified evidence" can realistically mean

Five classes, assessed for whether the engine can adjudicate them without a provider
call.

### Class 1 -- Executable / testable claim
*"For input X, function Y returns Z"* / *"raises E"*.

| | |
| --- | --- |
| Deterministic verification | **Yes** -- call the function and compare |
| Cost | **47 ms** measured per execution on this machine (n=12, cold temp dir); ×2 for a determinism re-check |
| Risk | Executes the code under review (§5) |
| Generality | High -- any callable whose arguments are JSON literals |
| False-positive risk | **Real**: nondeterministic functions, and a correct diagnosis carrying a sloppy example (simulated at §7 E1) |
| Should it auto-gate CRITICAL/HIGH? | **It must only ever remove authority, never grant it.** |

### Class 2 -- Static language-semantics claim
*"Python `str` slicing operates on bytes."*

| | |
| --- | --- |
| Deterministic verification | Only indirectly. The proposition is decidable, but it arrives as prose, and extracting it reliably is the hard part |
| Cost | Low if hand-coded per proposition |
| Risk | A hand-written table of "known false claims about Python" is a keyword matcher; the dataset was explicitly built to defeat keyword matching |
| Generality | **Poor** |
| False-positive risk | High -- prose matching misfires |
| Auto-gate? | **No.** Not a viable primary mechanism |

Important: this class **collapses into Class 1** once the claim must be instantiated
on the actual code. "Slicing splits multi-byte sequences" becomes checkable the
moment it must name a `text` and a `max_chars`. That is the whole trick.

### Class 3 -- Structural code claim
*"Branch X is unreachable"*, *"validation is missing before call Y"*.

| | |
| --- | --- |
| Deterministic verification | Partially, via AST |
| Cost | Moderate; no execution |
| Risk | Mapping prose to an AST query is the same brittle step as Class 2 |
| Generality | Medium, per-proposition |
| False-positive risk | Medium |
| Auto-gate? | **No.** A plausible later supplement, not the MVP |

### Class 4 -- Security / threat-model claim
*"An attacker can inject shell arguments."*

| | |
| --- | --- |
| Deterministic verification | **No.** Requires an attacker model and live resources the fixture does not provide |
| Cost | n/a |
| Risk | Any attempt to "verify" these would attack the host |
| Generality | n/a |
| False-positive risk | Catastrophic if a failed verification were read as "not a vulnerability" |
| Auto-gate? | **Never.** Must stay UNSUPPORTED and **keep** its severity |

Structural protection, not policy: `get_user_by_email(conn, email)` takes a live
`sqlite3.Connection`, which is not a JSON literal, so **no witness for the SQL
injection blocker can even be expressed**. `generate_reset_token()` returns a random
string, so no return-value claim about it is reproducible. Both survive by
construction (§7 D).

### Class 5 -- Style / quality claim
*"Extract this literal to a named constant."*

| | |
| --- | --- |
| Deterministic verification | **No** -- no runtime observation exists |
| Auto-gate? | **Never.** Stays UNSUPPORTED and keeps its severity |

---

## 4. Architecture options

### Option A -- Structured evidence field
Add `claim` / `evidence_type` / `probe` / `expected_observation` to the defect
object; verify only supported types.

**Schema impact: zero, verified empirically.** `enforce_critic_schema` checks only
for *missing* defect keys (`missing = DEFECT_KEYS - d.keys()`) and rejects stray keys
only at the critic's top level. An extra *per-defect* key is accepted today:

```
enforce_critic_schema({"defects":[{...,"witness":{...}}],"verdict":"FAIL"})  ->  []
enforce_critic_schema({"defects":[],"verdict":"OK","witnesses":[]})          ->  ['unexpected top-level keys']
```

So the evidence must live **inside** the defect object, and costs no schema change.
**Adopt (as the data shape).** A shape with no verifier is inert on its own.

### Option B -- Post-critic verifier over the existing free text
Extract claims from `fix` prose without another model call.

**Reject.** Reliable claim extraction from prose is the unsolved part. Regexes over
judge prose would be brittle, invisible when they silently stop matching, and
effectively fitted to observed phrasings.

### Option C -- Runtime witness contract
A blocking defect may carry an executable witness; the engine runs it in the
isolated per-case workspace.

**Adopt (as the verifier).** This is the only mechanism found that adjudicates a
fabricated claim without a provider call. A + C are complements, not rivals.

### Option D -- Static semantic guardrails
Deterministic checks for a narrow set of known language-semantic claims.

**Reject as primary.** Would not have caught the observed fabrication (`0.1 + 0.2`
is a value claim, not a semantic one), and a table of known-false propositions is
benchmark-shaped by construction. Viable later as a supplement.

### Option E -- Two-tier authority
VERIFIED may gate; UNVERIFIED is advisory; corroborated may gate.

**Adopt one direction only.** The safe direction is subtractive:

| Outcome | Effect on severity |
| --- | --- |
| **REFUTED** by execution | **demote** -- authority lost |
| VERIFIED | unchanged |
| UNSUPPORTED / inconclusive / no witness | **unchanged** (fail-closed) |

The rejected direction is *requiring* verification to grant blocking authority.
Under it, every Class 4 and Class 5 finding becomes non-blocking, and the SQL
injection case stops blocking. That is a false-pass generator and is out.

---

## 5. Security and execution safety

### What the engine already does

`verification/automated.py` already spawns subprocesses over the workspace --
`ruff check`, `mypy`, and `pytest -q` **when test files are present** -- with
`cwd=workspace`, `timeout=120`, and **the parent environment inherited**.

Two consequences:

- **In production (`engine run`), the engine already executes model-generated code.**
  If the model writes a `test_*.py`, `pytest` runs it. Execution of untrusted code is
  a pre-existing property of the production path, not something this design
  introduces.
- **In the benchmark, nothing currently executes.** Fixtures ship no test files, so
  `pytest` auto-passes and `ruff`/`mypy` are static. A witness harness would
  introduce execution to the benchmark path for the first time -- against fixtures
  that are repo-authored, reviewed and version-frozen.

### Concrete hazards, found in the benchmark's own fixtures

Scanned all 40 fixtures; 8 have side-effect surface:

| Fixture | Surface | What a witness would actually do |
| --- | --- | --- |
| `security-04-*` | `socket.getaddrinfo(host, None)` | **Real DNS resolution.** Network egress |
| `security-02-*` | `subprocess.run(["convert", ...])` | **Spawns an external process** and writes `<name>.png` |
| `security-01-*` | `sqlite3` | Needs a live connection -- witness inexpressible |
| `security-03-broken` | `random` | Nondeterministic return -- witness non-reproducible |
| `edge_case-05-clean` | `threading` | A race claim is not a single deterministic call |

(These were read for hazard analysis only. `security-02-clean` and
`security-04-clean` are not targeted and no engine behaviour is being tuned toward
them.)

### Required containment

| Hazard | Mitigation | Residual |
| --- | --- | --- |
| Arbitrary code execution | Witness is **data**, never code: a module name, an attribute name, JSON literals. No `eval`, `exec`, or `compile` of model text. A **fixed** runner script does `importlib.import_module` + `getattr` + call | Importing the reviewed module runs its top level |
| Secret exfiltration | **Scrubbed environment.** Today's gates inherit `ANTHROPIC_API_KEY`; the witness runner must pass an allowlist only | An allowlist that keeps `PATH` lets a fixture find real binaries -- deliberate, since removing `PATH` changes program behaviour and could spuriously refute a true finding |
| Hang / infinite loop | `subprocess.run(timeout=...)`, ~10 s, well under the existing 120 s gate timeout | A wedged child must be killed, not awaited |
| Destructive writes | `cwd` = a **temp copy** of the per-case workspace, outside the repo | Absolute paths and `..` still escape. Not containable without a container |
| Fork bomb / memory abuse | **None available.** `resource.setrlimit` is POSIX-only and this project runs on Windows (`win32`); no seccomp | Accepted for trusted benchmark fixtures; a real limit needs the existing `Dockerfile` path |
| Network | None in-process | Accepted; DNS from `security-04-*` is the known instance |

**Is the existing isolated workspace sufficient?** For the *benchmark*, yes with the
temp-copy, timeout and env-scrub above: fixtures are trusted, frozen and inspected.
For *production*, the honest framing is that the witness runner is **strictly more
contained than the `pytest` gate that already runs there** -- shorter timeout,
scrubbed env, temp cwd, and no model-authored code executed at all. It therefore does
not need to be disabled in production, which avoids an eval-versus-production
behavioural divergence that would undermine what the benchmark measures.

**Not recommended under any configuration:** executing model-generated Python via
`eval`/`exec`, or letting the model supply a code string.

---

## 6. Recommended minimal viable design

**Name:** *refutation-only witness verification.*

One sentence: **a blocking finding that makes a checkable claim, and is checked and
found false, stops blocking; everything else is untouched.**

The critic prompt asks for a witness on CRITICAL/HIGH findings. It is **not** told
what happens when the witness is missing or unverifiable -- that policy lives in the
engine, so omission cannot be used as a strategy.

### Witness shape (inside the defect object)

```json
{"id":"C1","category":"CORRECTNESS","severity":"HIGH",
 "location":"solution.py:2","fix":"...",
 "witness":{"call":"is_close_enough","args":[0.30000000000000004,0.3],
            "expect":{"returns":false}}}
```

`expect` is either `{"returns": <JSON literal>}` or `{"raises":"ExcType"}`.

### The ten questions

**1. What new data must the critic return?** One optional per-defect `witness`
object. Nothing else. Non-blocking findings need none.

**2. Which claims can be deterministically verified?** Class 1 only: a single call,
JSON-literal arguments, and a JSON-representable return value or an exception type.

**3. What happens when verification is unsupported or inconclusive?** **Nothing.**
Severity is untouched. Malformed witness, unknown attribute, unrepresentable return,
timeout, harness error, and *disagreement between two executions* (the
nondeterminism guard) all map to UNSUPPORTED.

**4. Can an unsupported claim still be CRITICAL/HIGH?** **Yes, deliberately.** This
is the property that keeps SQL injection, weak randomness, race conditions and every
style finding blocking.

**5. How are genuine broken cases protected?** Three ways, one of them measured:
- Demotion is **per defect**, never per case.
- Measured margin: across the five stability runs, **every broken case carries at
  least 2 blocking defects in every run; the mean is 3.76**. Only `quality-01-broken`
  ever sits at the minimum of 2 -- the single case to watch. For a broken case to
  false-pass, *every* one of its blocking defects must carry a witness *and* every
  one must be refuted.
- Structural: the highest-stakes findings cannot form a witness at all (§7 D).

**6. How does it avoid the Phase 8C failure mode (blanket severity softening)?** No
key reordering, no verdict normalization, no global rule about what CRITICAL/HIGH
means. A severity changes only when a specific claim was executed and contradicted.
`rubric.BLOCKING`, `schema.enforce_critic_schema` and `verdict.gate` are untouched.

**7. How does it avoid the Phase 8D.1 failure mode (fabricated demonstrations)?**
Fabrication is now the losing move: a false witness is exactly what gets refuted.
And the failure mode under **non-compliance is the status quo** -- if the model
supplies no witness, nothing changes and nothing regresses. The design is safe when
it does not work, and only useful when it does.

**8. Production files that would change.**

| File | Change | Measured path |
| --- | --- | --- |
| `src/engine/verification/witness.py` | **new** -- validate, execute, classify, demote | new |
| `src/engine/verification/witness_runner.py` | **new** -- fixed child entrypoint, no model code | new |
| `src/engine/verification/pipeline.py` | ~8 lines: verify between `merge()` and `gate()`; recompute `merged["verdict"]` from the post-demotion severities, preserving `merge()`'s own invariant | **yes** |
| `src/engine/verification/judge.py` | prompt clause describing the optional witness | **yes** |
| `src/engine/eval/runner.py` | *optional* `on_witness_result` callback mirroring the existing `on_schema_failure` pattern, written to a per-run JSONL under `EVAL_ROOT` | **yes** |

The `runner.py` line is optional and is **recommended**: without it the validation
run yields verdicts with no way to tell whether a flip came from refutation or from
prompt-induced drift, which is precisely the gap that made Phase 8D.1 hard to read.
Dropping it reduces the change to two measured-path files.

Recomputing `merged["verdict"]` is **not** Phase 8C.1's normalization: that
overwrote the *model's* verdict string; this keeps the *engine's own* merged object
self-consistent after the engine itself changed a severity.

**9. Deterministic tests needed** (~14): witness validation rejects malformed shapes
without raising; `returns`/`raises` verified and refuted paths; unrepresentable
return -> UNSUPPORTED; timeout -> UNSUPPORTED; nondeterministic function ->
UNSUPPORTED via double execution; missing attribute -> UNSUPPORTED; **no witness ->
severity unchanged**; **UNSUPPORTED never demotes**; demotion is per defect and a
surviving sibling still blocks; automated (`ruff`/`mypy`) defects are never touched;
the env passed to the child carries no `*_API_KEY`; `gate()` semantics unchanged.

**10. DB migration required?** **No.** `db.py` has no migration mechanism at all
(no `ALTER TABLE`, no `PRAGMA user_version`), which is itself a strong argument
against needing one. `record_eval_case_defects` writes seven named columns and
ignores extra dict keys, so `witness` / `original_severity` / `witness_result` ride
along in memory and are simply not persisted. The stored `severity` is the one that
gated -- which is the correct thing to store. Persisting the verification outcome as
a column is a separate, later decision.

---

## 7. Simulation against stored outputs -- no provider calls

Executed the prototype harness against the **real frozen fixtures**, using witnesses
taken from **stored judge claims**. Scratchpad only; no repo file was touched.

### A. The actual fabricated claim from the Phase 8D.1 partial run

| Witness | Claimed | Actual | Result |
| --- | --- | --- | --- |
| `is_close_enough(0.1+0.2, 0.3)` | returns `False` | returns `True` | **REFUTED** |
| `is_close_enough(0.29, 0.19)` | returns `False` | returns `False` | **VERIFIED** |

The first is the load-bearing fabrication, caught deterministically at 47 ms.

**The second is the design's most important negative result and is not glossed
over.** The `security` lens's companion finding made a *true observation* wrapped in
a *false inference*: `is_close_enough(0.29, 0.19)` really does return `False`, and
that is the correct answer, because 0.10 is not less than 0.01. Execution
adjudicates the observation; it cannot adjudicate the inference, because the only
oracle for "what should this return" is the task prose.

**Consequence, stated plainly: witness verification narrows the fabrication surface;
it does not close it.** It catches false claims about what the code does. It does
not catch true claims about what the code does, paired with a false claim about what
the task requires.

### B. `edge_case-03-clean` -- the stored claim is prose, so the witness space was enumerated

Every input the stored claims name as corruptible, against `return text[:max_chars]`:

| Witness | Claimed | Actual | Result |
| --- | --- | --- | --- |
| `truncate("café naïve", 4)` | raises `UnicodeDecodeError` | returns `"café"` | **REFUTED** |
| `truncate("👋👋👋", 2)` | raises `UnicodeDecodeError` | returns `"👋👋"` | **REFUTED** |
| `truncate("éclair", 3)` (combining acute) | raises `UnicodeDecodeError` | returns `"éc"` | **REFUTED** |
| `truncate("日本語テキスト", 3)` | raises `UnicodeDecodeError` | returns `"日本語"` | **REFUTED** |

Both blocking findings on this case assert corruption. **No instantiation of that
claim survives execution.**

### C. Genuine defects -- blocking authority preserved

| Case | Witness | Claimed | Actual | Result |
| --- | --- | --- | --- | --- |
| `correctness-02-broken` (float) | `is_close_enough(1.0, 1.005)` | returns `False` | returns `False` | **VERIFIED** |
| `edge_case-03-broken` (bytes) | `truncate("héllo", 2)` | raises `UnicodeDecodeError` | raises `UnicodeDecodeError` | **VERIFIED** |
| `edge_case-04-broken` (boundary) | `is_business_hours(17)` | returns `True` | returns `True` | **VERIFIED** |
| `correctness-01-broken` (off-by-one) | `paginate([1..6], 1, 2)` | returns `[3, 4]` | returns `[3, 4]` | **VERIFIED** |

### D. Non-executable classes -- UNSUPPORTED by construction, never demoted

| Case | Why no witness exists |
| --- | --- |
| `security-01-broken` (SQL injection, 3× CRITICAL) | `get_user_by_email(conn, email)` requires a live `sqlite3.Connection` -- **not expressible as a JSON literal** |
| `security-03-broken` (weak randomness) | `generate_reset_token()` returns a random string -- **no reproducible return claim**; the double-execution guard classifies it UNSUPPORTED |
| `edge_case-05-broken` (race) | A concurrency defect is not a single deterministic call |
| `quality-04-broken` (named constant) | No runtime observation corresponds to the claim |

These are protected by the **shape of the contract**, not by a policy exception --
a materially stronger guarantee.

### E. Counterexample -- correct diagnosis, sloppy witness

| Witness | Claimed | Actual | Result |
| --- | --- | --- | --- |
| `is_close_enough(1.0, 1.0)` on `correctness-02-broken` | returns `False` | returns `True` | **REFUTED** |

`a == b` really is broken, but this particular input happens to behave correctly, so
the finding would be demoted. **This is the design's false-pass vector, and it is
real.** It is bounded, not eliminated: the case carries three CRITICAL findings, so
all three would have to carry witnesses and all three be refuted. Across the five
stability runs no broken case ever had fewer than two blocking defects.

### Would the design fix the targets? Honest answer

| Case | Blockers at baseline | Assessment |
| --- | --- | --- |
| `edge_case-03-clean` | 2 (both assert corruption) | **Likely flips** -- every enumerated witness refutes. Conditional on the model supplying witnesses |
| `correctness-02-clean` | 1 at baseline (prose only); 2 in the 8D.1 run | **Uncertain.** The fabricated blocker refutes; the A2-pattern companion does not |

Neither is asserted as an expected result. Both are hypotheses for a pre-registered
run.

---

## 8. GO / NO-GO

| Criterion | Verdict |
| --- | --- |
| General, not benchmark-ID-specific | **Pass.** The contract is "callable + JSON literals + expected observation". No case id, fixture string, filename, constant or language feature appears in it |
| Deterministic verification for a meaningful class | **Pass.** Class 1, demonstrated on 11 real fixtures |
| Cannot turn fabricated evidence into authority | **Pass.** Verification is subtractive only; nothing a model writes can *raise* severity |
| Preserves genuine blocker safety | **Pass, with a bounded residual.** Absence never demotes; measured margin ≥2 blockers per broken case; §7 E is the residual |
| No arbitrary LLM-generated code execution | **Pass.** The witness is data. The reviewed code is executed -- trusted in the benchmark, and already executed by the existing `pytest` gate in production |
| No extra paid LLM call per finding | **Pass.** $0.00. 47 ms of local CPU |
| Not a large invasive subsystem | **Pass.** 2 new files (~150 LOC), 2-3 edited, ~14 tests, no DB migration, no schema change |

**PHASE_8D2A_ARCHITECTURE_GO.**

The counter-case, recorded fairly: the mechanism's benefit is **unmeasured and
conditional on model compliance**, and §7 A2 shows it cannot catch a false inference
attached to a true observation. If a prototype run shows the model simply omits
witnesses, the correct read is that the approach is dead -- not that the prompt needs
more pressure. **The simpler alternative, if this is not pursued, is to stop here and
accept 36/40 as this configuration's ceiling**, which the Phase 8D.0 evidence already
establishes as an honest description of the engine rather than a defect to be tuned
away.

---

## 9. Implementation scope

| Dimension | Estimate |
| --- | --- |
| New files | 2 -- `verification/witness.py` (~110 LOC), `verification/witness_runner.py` (~40 LOC) |
| Edited files | 2 required (`pipeline.py` ~8 lines, `judge.py` prompt), 1 optional (`runner.py` ~10 lines for observability) |
| Measured-path files touched | 2, or 3 with observability |
| Tests | ~14 deterministic, no provider needed |
| DB / schema impact | **None.** No migration, no `enforce_critic_schema` change (verified empirically) |
| Runtime overhead | ≤86 blocking defects per run × 2 executions × 47 ms ≈ **8 s on a ~220 s run (+3.7%)**, and only for findings that carry a witness |
| Provider-call impact | **Zero additional calls.** Slightly longer critic responses, within the existing `max_tokens=800` |
| Cost to reach a prototype | **$0.00** before the benchmark run |

### Risks, ranked

1. **Non-compliance.** The model may not emit witnesses. Failure mode is benign
   (status quo), but the phase would produce no signal. Mitigate by pre-registering
   *witness emission rate* as a measured quantity, not just verdicts.
2. **Sloppy witness on a genuine defect** (§7 E). Bounded by the ≥2-blocker margin;
   `quality-01-broken` is the named watch case. Guardrail: all 20 broken cases must
   remain UNVERIFIED.
3. **True observation, false inference** (§7 A2). Not addressed by this design.
   Requires an oracle for the task, which does not exist deterministically.
4. **Nondeterministic fixtures** spuriously refuting. Mitigated by the
   double-execution guard; costs one extra 47 ms run per witness.
5. **`max_tokens=800` pressure.** A witness lengthens each defect. The truncation
   already observed on `security-04-clean` (largest fixture, 1 of 5 runs) could
   become more frequent, and truncation fails closed to UNVERIFIED. Pre-register
   schema-failure count as a guardrail.
6. **Execution reaching the network or spawning processes** (§5). Real, present in
   `security-02-*` and `security-04-*`. Contained but not eliminated on Windows.
7. **Observability gap** if the optional `runner.py` change is dropped.

---

## 10. Recommended next step

A pre-registered Phase 8D.2B prototype: implement the MVP behind the gates, then one
experiment with **n = 5 per arm** at the current configuration, primary metric the
per-case rate on `edge_case-03-clean` and `correctness-02-clean`, secondary the
aggregate, and guardrails on all 20 broken cases, schema-failure count, blocking-mass
and witness-emission rate. Nothing about `security-02-clean` or `security-04-clean`
is in scope.
