# Final Project Status

Release candidate. Accuracy optimization is closed.

---

## 1. Release candidate

| | |
| --- | --- |
| Benchmark | `engine-review-benchmark` |
| `BENCHMARK_VERSION` / `DATASET_VERSION` | **v2 / v4** |
| Dataset checkpoint | `f79353c65099561854e63ed2a8b8e23aaa2c58ce` |
| Judge model | `claude-haiku-4-5-20251001` (Anthropic) |
| Runtime verdict path | byte-identical to the proven safe engine `53d8a42` |
| Whole `src/` tree vs `53d8a42` | one file, `state/db.py` (persistence hardening, off the measured path) |

---

## 2. Validated benchmark result

Five runs at one commit, dataset frozen, no configuration change between runs:

| | |
| --- | --- |
| Scores | **36, 35, 35, 35, 35** |
| Mean | **35.2 / 40 = 88.0%** |
| Sample SD | **0.447** |
| False passes | **0 / 100** broken-case observations |
| Deterministic cases | 39 of 40 |
| Cost | $0.643 for the five runs |

Recorded in `.engine/experiments/phase8d0-stability/`. This is the only benchmark
claim the project makes.

---

## 3. Remaining known failures

Four clean cases fail in every stored observation, capping this configuration at
36/40:

| Case | Rate | Why the judge blocks it |
| --- | --- | --- |
| `correctness-02-clean` | 0/5 | Rates `abs(a - b) < 0.01` HIGH and asks for `decimal`, though the code *is* the stated predicate — an implementation preference |
| `edge_case-03-clean` | 0/5 | Two lenses claim `str` slicing splits multi-byte UTF-8. It cannot: `str` slices code points. The fix it prescribes is that task's own broken fixture |
| `security-02-clean` | 0/5 | Two blockers allege shell injection against `subprocess.run([...])` with no shell, each conceding non-exploitability in its own text; a third (uncaught `FileNotFoundError`) is factually true but not required by the task |
| `security-04-clean` | 0/5 | Claims contradicted by the supplied code (an `all()` check) or excluded by the task's own wording; claim content varies run to run |

`edge_case-04-clean` is variable (1/5) and is the sole source of score variance —
it flips on a single defect crossing the MEDIUM/HIGH boundary. It is treated as a
guardrail and was never optimized.

---

## 4. Accepted infrastructure fixes

| Fix | Status |
| --- | --- |
| `automated.py` — empty-output gate failure no longer records the ambiguous `"ok"` sentinel (DF-1) | Applied, Phase 8A, 7 tests |
| `db.py` — unpaired UTF-16 surrogates in model text no longer raise `UnicodeEncodeError` during persistence | Applied, Phase 8D.1, 3 tests |

The surrogate fix is general (every model-supplied column), write-side only (no
verdict it can reach is affected), and preserves valid Unicode — astral characters
round-trip byte for byte. It was found the hard way: an emoji in a judge's text
aborted a 40-case run at case 36 and discarded 35 computed results.

---

## 5. Rejected experimental directions

Every one of these raised or promised to raise the score and was reverted on
measured evidence.

| Phase | Intervention | Measured outcome |
| --- | --- | --- |
| 4 | Source-verification + task-scope prompt | Not supported, n=8 vs n=8: mean 33.00 → 32.63 |
| 8C | Emit severity after the fix analysis | 35 → 38, but schema failures 0 → 7 and the mechanism erodes blocking margin |
| 8C.1 | Verdict normalization | **2 false passes in one run** |
| 8D.1 | Demonstrability prompt | Model fabricated a concrete trigger that was false; run crashed before evaluation |
| 8D.2 | Executed-witness verification | **26 false passes / 100**, −7.4 cases; all 26 attributed to witness demotion |

Common failure: each worked by changing what the model produces or how its output
is re-scored. The mechanism that changed behaviour most decisively also broke
safety most decisively.

The 8D.2 root cause is worth keeping: the witness contract never said whose
behaviour `expect` described. Reviewers write the **required** behaviour; the
classifier read it as the **observed** behaviour. On broken code those differ by
definition, so every correct diagnosis was refuted and demoted. The prototype's own
tests missed it because the implementer wrote the witnesses and the model did not.

---

## 6. Active architecture

- **Orchestrator** — `task_analyzer` classifies, `execution_plan` produces a
  validated plan with token/spend/agent limits, `manager` executes it. Agents never
  talk to each other.
- **Gateway** — every LLM call routes through `runtime/gateway.py`, which enforces
  the budget before the call and records usage after it. Three architecture tests
  make the boundary unbypassable.
- **Verification** — three judge lenses (correctness, security, code-quality) return
  structured defects validated against a fixed schema; a pure Python
  `merge`/`gate` is the only code allowed to decide `OK` / `UNVERIFIED`. Any
  CRITICAL/HIGH defect blocks, a malformed response blocks, a failed automated gate
  blocks.
- **Persistence** — SQLite run history, per-call metrics, per-case eval results,
  defects, lens results, gate results and schema failures.

No LLM decides pass/fail anywhere in this system.

---

## 7. Known limitations

- The benchmark is **project-specific**, not an industry-standard external suite.
  It makes changes to this engine falsifiable; it does not rank this engine
  against others.
- Ceiling of 36/40 at this configuration, for the four cases in §3.
- Judge lens calls are capped at `max_tokens=800`. The largest fixture occasionally
  truncates, which fails closed to `UNVERIFIED`. **Not changed in this phase** —
  raising it trades cost and cross-run comparability for an unmeasured gain.
- Single provider (Anthropic), sequential sub-agent execution.
- The n8n `/review` webhook runs `pytest` on submitted files inside the container
  with no sandboxing beyond the container boundary. Do not expose it publicly.
- Five stability runs is a small sample; SD 0.447 is likely an underestimate of
  long-run dispersion, since four of five scores were identical. The stronger
  finding is the per-case matrix: 39 of 40 cases deterministic.

---

## 8. Intentionally deferred

| Item | Why |
| --- | --- |
| **DF-3** — a failing judge lens discards critics already collected | Never fired in 4,680 recorded lens calls. Repair would change what `gate()` sees when a lens fails — a verdict-semantics decision, and the current behaviour is the fail-closed direction. Needs its own pre-registered phase (`DEFERRED_FIXES.md`) |
| `max_tokens` tuning | Cost and comparability trade-off; needs its own pre-registration |
| Multi-provider routing, parallel sub-agents, merge control, long-term memory | Planned milestones, never started |
| Header/architecture image | `docs/assets/architecture-overview.png` is referenced only in a README comment. **No image file exists in the repository**; the placeholder is deliberate, not an oversight |

---

## 9. Why score chasing was stopped

Phase 8E.0 was a read-only gate that asked whether any of the four stable failures
could be fixed **without** weakening HIGH/CRITICAL, changing verdict authority or
schema semantics, adding an LLM call, asking the model for new evidence fields,
matching case IDs or fixtures, broad prompt calibration, or executing generated
code. It returned **`NO_SAFE_TARGET`**, on measurement rather than opinion:

- `verdict.gate` decides on severities alone, so changing a verdict requires
  changing the severity set — and within the permitted fix types the only route is
  a deterministic filter over existing data.
- The one such filter available (lens/category disagreement) leaves **all four
  targets still blocking in all six stored observations**, while touching 45.7% of
  the blocking defects on broken cases. Zero upside, large blast radius.
- For three of the four, the false blocker on the clean case and a genuine blocker
  on its **broken twin** are substantially the same claim (word overlap 0.29 /
  0.16 / 0.14 against an unrelated-task baseline of 0.02). The only separator is a
  fact about the code, and reading that deterministically means executing it —
  already rejected at 26 false passes — or asking a model, which is excluded.
  **Any filter strong enough to clear the clean case clears its broken twin.**

Five interventions, five reversions, and a measured impossibility argument for the
remainder. Stopping is the finding, not a failure to try: the engine ships at
88.0% with zero false passes rather than at a higher number bought with silent
acceptance of broken code.
