# Phase 8D.2B -- Refutation-Only Witness Prototype

**Prototype and deterministic validation only.** No benchmark was run, no provider
was called, no dataset file was touched. Provider cost: **$0.00**.

**Result: the prototype is accepted.** 181 tests pass, the fabricated Phase 8D.1
claim is deterministically REFUTED, and every genuine blocker in the stored-output
replay stays blocking. The replay also shows, without hedging, that this fixes one
of the two target cases and not the other -- for the reason the architecture review
predicted in advance.

---

## 1. Pre-change safety

| Check | Result |
| --- | --- |
| `HEAD` | `ec7a9618dcf6cf3946f0afaed1c7a5a827643b33` |
| `git status --porcelain` | `?? PHASE8D2A_VERIFIED_EVIDENCE_ARCHITECTURE.md` only |
| `git diff --stat` | **empty** |
| `BENCHMARK_VERSION` / `DATASET_VERSION` | `v2` / `v4` |
| `git diff f79353c -- src/engine/eval/dataset.py` | **EMPTY** |

---

## 2. Architecture used

`PHASE8D2A_VERIFIED_EVIDENCE_ARCHITECTURE.md` §6, implemented as specified. No
redesign; one classification rule was tightened during TDD (§5) after a test
demonstrated a concrete safety hole.

**The authority invariant, implemented and tested:**

> Execution may only ever **remove** blocking authority, and only when a
> deterministic observation **contradicts** the critic's own claim.

| Outcome | Meaning | Effect on severity |
| --- | --- | --- |
| `VERIFIED` | the observation matched the claim | **unchanged** |
| `REFUTED` | a clean contradiction | **demoted to MEDIUM** |
| `UNSUPPORTED` | the witness is not a checkable claim | **unchanged** |
| `INCONCLUSIVE` | checkable, but no clean observation came back | **unchanged** |
| `NO_WITNESS` | none supplied | **unchanged** |

Nothing a model writes can raise a severity. Four of the five outcomes are
no-ops, so the failure mode under non-compliance is the engine's existing
behaviour.

---

## 3. Exact implementation

### Witness shape (optional, inside a defect object)

```json
{"call": "is_close_enough", "args": [0.30000000000000004, 0.3],
 "expect": {"returns": false}}
```

`expect` is exactly one of `{"returns": <JSON literal>}` or
`{"raises": "<ExceptionName>"}`.

### Validation, before anything executes (`witness._parse`)

- `call` must be a plain identifier, not starting with `_` -- no dotted paths, no
  dunders. Rejected: `os.system`, `__import__`, `_private`, `""`, `is close enough`.
- `args` must be a list that survives a JSON round trip unchanged. This rejects
  `NaN`/`Infinity` (which `json` accepts by default and nothing else does) and
  dicts with non-string keys, which JSON silently coerces.
- `expect` must hold exactly one recognised key.

Anything else is `UNSUPPORTED` and nothing is executed.

### Execution (`witness_runner.py`, a fixed script)

The child receives one JSON spec on stdin: candidate module names **derived by
the parent from the workspace's own filenames**, one attribute name, and JSON
literals. It imports, resolves, calls, and prints one JSON observation.

Only callables the reviewed module **itself defines** are eligible
(`target.__module__ == module_name`). A name the reviewed code merely imported --
`from os import system` -- resolves to a foreign object and is refused, so a
witness can never be a way to invoke whatever the code happened to import.

`sys.path` gains the working directory only *after* every import the runner needs,
so a workspace file named `json.py` cannot shadow the runner's own dependencies.

### Classification asymmetry (`witness._classify`)

| Claim | Observation | Verdict |
| --- | --- | --- |
| `returns X` | returned `X` | VERIFIED |
| `returns X` | returned `Y != X` | **REFUTED** |
| `returns X` | raised | INCONCLUSIVE |
| `raises E` | raised `E` | VERIFIED |
| `raises E` | raised `F != E` | INCONCLUSIVE |
| `raises E` | returned anything | **REFUTED** |
| import failed / no such attribute / not callable / foreign / unrepresentable / timeout / child died | -- | INCONCLUSIVE |

The asymmetry is the safety property, and §5 explains why it was not optional.

Value comparison is `==`, not a strict type match: `1` vs `1.0` and `1` vs `True`
count as agreement. The dangerous direction is a wrong REFUTED, so ambiguity is
resolved toward leaving the severity alone.

### Nondeterminism guard

Only a refutation costs anything, so only a refutation must be shown twice. A
first observation that would refute is re-executed; if the second differs, the
result is INCONCLUSIVE. Both executions share one working directory on purpose,
so state-dependent variation is visible to the guard, not just randomness.

### Demotion semantics

`severity` becomes `MEDIUM`; `original_severity` and `witness_result` are recorded
on the defect. The defect is retained in full -- no evidence is deleted. Those two
extra keys are ignored by `db.record_eval_case_defects`, which writes seven named
columns, so **no DB migration and no schema change are required**. Verified
empirically: `enforce_critic_schema` already accepts extra *per-defect* keys.

`merged["verdict"]` is recomputed from the post-demotion severities. That keeps
`verdict.merge()`'s own invariant after the engine changed a severity; it is not
Phase 8C.1's normalization, which overwrote what the *model* said.

When no blocking defect carries a witness -- the overwhelmingly common case --
`apply_witness_verification` returns the merged object unchanged and never even
copies the workspace.

---

## 4. Threat model

The child executes the code under review. In the benchmark that code is
repo-authored and frozen; in production it is model-generated, which the existing
`pytest` gate in `automated.py` **already** executes with the full environment
inherited. This runner is strictly more contained than that gate.

| Hazard | Mitigation | Residual, stated honestly |
| --- | --- | --- |
| Arbitrary code execution | Witness is data. No `eval`, `exec`, or `compile` of model text anywhere. Module names come from filenames, never from the model | Importing the reviewed module runs its top level |
| Invoking imported stdlib callables | Only callables defined in the module itself are eligible | -- |
| Secret exfiltration | Environment **allowlist** (`PATH`, `PATHEXT`, `COMSPEC`, `SYSTEMROOT`, `SYSTEMDRIVE`, `WINDIR`, `TEMP`, `TMP`, `TMPDIR`, `LANG`, `LC_ALL`) plus an engine-set `PYTHONIOENCODING`. No `*_API_KEY` reaches the child -- asserted by a test | `PATH` is kept deliberately: removing it changes what the reviewed code does and could refute a true finding for the wrong reason |
| Hang / infinite loop | `subprocess.run(timeout=10)` | -- |
| Destructive writes | `cwd` is a **temp copy** of the workspace | Absolute paths and `..` still escape. Not containable without a container |
| Fork bomb, memory abuse | **None available** | `resource.setrlimit` is POSIX-only and this project runs on Windows; there is no seccomp. Not claimed |
| Network | **None available** | Real: `security-04-*`'s fixture calls `socket.getaddrinfo`, so a witness there would perform live DNS. Not claimed to be blocked |

---

## 5. TDD -- and the safety hole a test found

**RED before implementation:** `ImportError: cannot import name 'witness'`, then a
staged red-green cycle to 28 tests.

**One test failed against the first implementation, and it mattered.**
`test_m_a_finding_whose_witness_cannot_be_expressed_stays_blocking` fed the
SQL-injection shape a best-effort witness -- a JSON dict standing in for the live
`sqlite3.Connection` the function requires. The call raised `AttributeError`, and
the first implementation read "raised when a return was claimed" as a
contradiction:

```
assert 'REFUTED' == 'INCONCLUSIVE'
```

That is precisely the acceptance criterion "security findings cannot be
accidentally softened through unsupported witnesses", failing. **Any finding whose
real entry point takes a live object could have been disarmed by a witness whose
arguments merely did not fit.** The fix is the asymmetry in §3: an exception where
a value was claimed is the *absence* of the claimed kind of observation, not a
contradiction of it. A value where an exception was claimed is a complete,
contradicting observation, and stays REFUTED -- which is exactly the
`edge_case-03-clean` shape.

### The 28 tests

| Brief | Test | Asserts |
| --- | --- | --- |
| A | fabricated float witness | REFUTED, demoted, gate opens |
| B | real `<=`-vs-`<` boundary defect | VERIFIED, HIGH kept, gate closed |
| C, C2 | character slicing called byte slicing (accents, astral) | REFUTED |
| D | real encoded-byte truncation | VERIFIED, blocker kept |
| D2 | claimed exception ≠ raised exception | INCONCLUSIVE, no demotion |
| E, E2 | missing callable; attribute not callable | INCONCLUSIVE, no demotion |
| F | 9 malformed witness shapes | UNSUPPORTED, no demotion |
| Q | non-identifier / private / dotted call names | UNSUPPORTED |
| Q2 | `from os import getcwd` re-export | INCONCLUSIVE -- not executed |
| G | timeout | INCONCLUSIVE, no demotion |
| H, H2, H3 | child killed; import-time raise; unrepresentable return | INCONCLUSIVE |
| I | no witness | untouched, no `witness_result` key |
| J, J2 | siblings | only the refuted defect moves; a survivor keeps the gate closed |
| K | every blocking severity without a refutation | still UNVERIFIED |
| M | witness that cannot be formed (live connection) | INCONCLUSIVE, CRITICAL kept |
| N | state-dependent nondeterminism | INCONCLUSIVE, never REFUTED |
| O | non-blocking defects | never executed; severity never raised |
| P | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in the parent | absent in the child |
| R | ruff/mypy script defects | passed through byte for byte |
| -- | `merged["verdict"]` | consistent with its own post-demotion severities |
| L | end-to-end: refuted blocker / unwitnessed blocker / malformed critic JSON | OK / UNVERIFIED / UNVERIFIED |

### Deterministic validation

| Gate | Result |
| --- | --- |
| `tests/test_witness.py` | **28 passed** |
| verification + witness + eval + architecture | 89 passed |
| `ruff check .` | All checks passed |
| `mypy src` | Success, **46 source files** |
| `pytest` (full) | **181 passed** |
| `git diff f79353c -- src/engine/eval/dataset.py` | **EMPTY** |

---

## 6. Stored-output replay

Defects taken **exactly as past runs stored them**, with the witness the stored
claim states attached, pushed through the production witness layer. Read-only
connections; no artifact mutated; no provider call.

| # | Case | Lens | Stored severity | Witness status | After | Gate |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `correctness-02-clean` | correctness | HIGH | **REFUTED** | MEDIUM | |
| | *(Phase 8D.1 run)* | security | HIGH | VERIFIED | **HIGH** | |
| | | code-quality | MEDIUM | NO_WITNESS | MEDIUM | UNVERIFIED -> **UNVERIFIED** (still wrong) |
| 2 | `edge_case-03-clean` | correctness | HIGH | **REFUTED** | MEDIUM | |
| | | code-quality | HIGH | **REFUTED** | MEDIUM | UNVERIFIED -> **OK** (corrected) |
| 3 | `correctness-02-broken` | correctness | CRITICAL | VERIFIED | CRITICAL | |
| | | security, code-quality | CRITICAL ×2 | NO_WITNESS | CRITICAL | **UNVERIFIED** (preserved) |
| 4 | `edge_case-03-broken` | correctness | CRITICAL | VERIFIED | CRITICAL | |
| | | security, code-quality | HIGH ×2 | NO_WITNESS | HIGH | **UNVERIFIED** (preserved) |
| 5 | `security-01-broken` | security | CRITICAL | **INCONCLUSIVE** | CRITICAL | |
| | | correctness, code-quality | CRITICAL ×2 | NO_WITNESS | CRITICAL | **UNVERIFIED** (preserved) |
| 6 | `quality-04-broken` | 3 blocking, 2 non-blocking | HIGH ×3 | NO_WITNESS | HIGH ×3 | **UNVERIFIED** (preserved) |

Witness provenance, stated so the replay can be judged: case 1's `correctness`
witness is transcribed **verbatim** from the stored `fix` text
(*"is_close_enough(0.1 + 0.2, 0.3) currently returns False"*), and its `security`
witness uses that finding's own stated `a=0.29, b=0.19`. Cases 2-4 instantiate
prose claims on inputs the stored text itself names. Case 5 attempts the best
witness the claim admits. Case 6 has none, because none exists.

**Case 1 is the honest negative and is not buried.** The fabricated claim is
refuted exactly as designed -- and the case still fails, because the companion
`security` finding made a *true observation* (`is_close_enough(0.29, 0.19)` really
does return `False`) wrapped in a *false inference* (that this is wrong; 0.10 is
not less than 0.01). Execution adjudicates observations, not inferences. The
architecture review predicted this in §7 A2 before the prototype existed, and the
prototype confirms it rather than escaping it.

---

## 7. Acceptance

| Criterion | Result |
| --- | --- |
| Fabricated executable witness can be REFUTED | **Yes** -- replay case 1, test A |
| Genuine executable witness remains blocking | **Yes** -- replay cases 3, 4; tests B, D |
| Unsupported findings remain unchanged | **Yes** -- replay cases 5, 6; tests F, I, M, Q |
| Security findings cannot be softened through unsupported witnesses | **Yes** -- and this is the criterion that failed first and forced the §5 fix |
| No arbitrary generated code execution | **Yes** -- no `eval`/`exec`/`compile` of model text; module names from filenames |
| No dataset change | **Yes** -- diff vs `f79353c` EMPTY |
| No DB migration | **Yes** -- none required |
| Full deterministic suite passes | **Yes** -- 181 passed |

---

## 8. Files changed and scope

| File | Status | Lines |
| --- | --- | --- |
| `src/engine/verification/witness.py` | new | 250 |
| `src/engine/verification/witness_runner.py` | new | 75 |
| `src/engine/verification/pipeline.py` | edited | +5 / -1 |
| `src/engine/verification/judge.py` | edited | +6 |
| `tests/test_witness.py` | new | 523 |

Two measured-path files touched. `dataset.py`, `runner.py`, `rubric.py`,
`schema.py`, `verdict.py`, `gateway.py` and `budget.py` are unchanged.

**Prompt change**, appended to `RESPONSE_INSTRUCTION`: the witness is offered as
optional, only the constrained data form is described, the model is told to leave
it out when the defect does not fit ("many do not"), and it is **never** told that
supplying one makes a finding more authoritative -- the policy lives in the engine
precisely so omission cannot be used as a strategy.

### Runtime

Measured on this machine with the production module:

| Path | Cost |
| --- | --- |
| VERIFIED / UNSUPPORTED / INCONCLUSIVE (1 execution) | **49 ms** |
| REFUTED (2 executions, determinism guard) | **93 ms** |
| No blocking defect carries a witness | **0 ms** -- early return, no workspace copy |

Worst case, all 86 blocking defects in a 40-case run witnessed and refuted:
**~8 s on a ~220 s run (+3.6%)**. Provider calls: **unchanged**.

---

## 9. Limitations

1. **A true observation with a false inference is not caught** (replay case 1).
   Execution can adjudicate what the code does, never what the task requires --
   there is no deterministic oracle for the prose task. This is the mechanism's
   ceiling, not a bug to be fixed later.
2. **The benefit depends on the model actually emitting witnesses**, which is
   unmeasured. Non-emission is benign (status quo), but it would mean no signal.
3. **A correct diagnosis with a sloppy witness is demoted.** Bounded, not
   eliminated: every broken case carries ≥2 blocking defects in every stability
   run (mean 3.76), and `quality-01-broken` is the single case that ever sits at
   the minimum of 2.
4. **No observability persistence.** `original_severity` and `witness_result` live
   in the merged object but are not stored, so a benchmark run could not yet
   attribute a flip to refutation. Deliberately deferred rather than built
   speculatively -- it should be added when a run is pre-registered and the use
   case actually exists.
5. **Sandboxing is what Windows allows and no more**: timeout, temp cwd, env
   allowlist. No memory or CPU limit, no network isolation.
6. **Only single-call claims.** Concurrency, multi-step state, and anything
   needing a live object are out of reach by construction.

---

## 10. Next step

A pre-registered Phase 8D.2C experiment, **n = 5 per arm** at the current
configuration:

- **Primary:** per-case rate on `edge_case-03-clean` (the replay says it should
  move) and `correctness-02-clean` (the replay says it should not).
- **Secondary:** aggregate accuracy against the measured 35.2 ± 0.447 baseline.
- **Guardrails, all pre-registered:** all 20 broken cases stay UNVERIFIED;
  schema-failure count (the witness lengthens each defect against
  `max_tokens=800`); blocking-defect mass; and **witness emission rate**, which
  decides whether a null result means "the mechanism failed" or "the model never
  used it".
- Add witness-result persistence first, so the run can attribute what it measures.

Nothing about `security-02-clean` or `security-04-clean` is in scope.
