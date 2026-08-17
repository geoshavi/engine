# Benchmark v1 → v2 Changelog

`BENCHMARK_VERSION` v1 → **v2**, `DATASET_VERSION` v3 → **v4**.

Implemented from two frozen decision records, both hash-verified before implementation:

| Record | SHA-256 | Bytes |
|---|---|---|
| `benchmark-v2-formal-adjudication.json` | `113919f3dc2c1c3dd445f830575e67516d85f05d97d6860744cd99fac91ab3e7` | 44,329 |
| `benchmark-v2-severity-policy-adjudication.json` | `622fcb9b236739a0b4474d2819197702d86780951375a619852d3e45054f696f` | 17,582 |

**No benchmark was run and no provider/API call was made.** Nothing was committed or pushed.

---

## Methodological scope — read before citing any v2 result

- Only **9 of 40** cases received independent blind adjudication.
- Those nine were **not selected blind**: they are exactly the nine non-VALID cases of the
  informed audit.
- The remaining **31 cases were retained from the informed audit and were never
  independently blind-validated**. That audit self-reports 40/40 of its judgments as
  compromised by prior label exposure.
- **Benchmark v2 must not be described as a fully independently validated 40-case dataset.**
  It may be described as a dataset in which nine disputed fixtures were adjudicated on two
  independent lines of evidence and the rest were carried forward unverified.

---

## Versioning and v1 preservation

Benchmark v1 remains constructible in-process. `dataset.py` now exposes `TASKS_V1` and
`CASES_V1`, built by overlaying `_V1_TASKS_CHANGED` — the pre-v2 form of the **seven** archived
v1 task definitions — onto `TASKS`. Those seven are `correctness-02`, `quality-01`,
`quality-02`, `quality-03`, `quality-04`, `quality-05` and `security-04`. Of the 20 tasks, the
remaining **13 untouched tasks** are shared between the v1 and v2 representations as the same
objects.

`BENCHMARK_V1_VERSION = "v1"` and `BENCHMARK_V1_DATASET_VERSION = "v3"` record the identity
historical runs were stamped with. Runs recorded under v1/v3 are **not comparable** with v2/v4
runs, which carry **6 task-text restatements**; **3 fixture-changed tasks** — `quality-01`,
`quality-03` and `security-04`; and **1 expected-category correction** — `quality-05-broken`.

### Object sharing — a non-blocking hardening consideration

The earlier claim that object sharing means the archive "cannot silently drift" **overstated the
guarantee** and is corrected here. Precisely:

- 13 unchanged task objects are currently shared between the v1 and v2 representations.
- Nested file dictionaries may also be shared in some reconstructed cases — `replace()` copies
  only the fields it overrides, so `broken_files` / `clean_files` can remain the same dict
  objects across both representations.
- `EvalTask` and `EvalCase` are `frozen=True`, which blocks attribute rebinding but **does not**
  freeze dict contents.
- Current source and tests contain **no mutating consumer** of those dictionaries: the only
  access path is `_write_case_files(workspace, case.files)`, which reads.
- **Therefore no live drift defect exists today.** Object sharing keeps the two views identical;
  it does **not** guarantee immutability against a future mutating consumer, which would corrupt
  both views at once.

Recorded as a hardening consideration only. No hardening is implemented in this version.

No structural change to `EvalCase`, `EvalTask`, `_build_cases`, or `validate_dataset` was
required. The one import added is `dataclasses.replace`.

---

## Changed cases

**Thirteen of forty cases changed.** Six task specifications were restated, and each propagates
to **both** members of a clean/broken pair because `task_text` is shared by construction — that
is why six restatements touch twelve cases. `quality-05-broken`'s category change is the
thirteenth.

### 1. `correctness-02-broken` + `correctness-02-clean` — CLARIFY_TASK

| | |
|---|---|
| **v1 task** | "…returns True if two floats are close enough to be considered equal for currency comparison (**within 0.01**)." |
| **v2 task** | "…for comparing currency amounts: return True when the two values **differ by less than 0.01**, and False otherwise. **A difference of exactly 0.01 is not close enough.**" |
| **Fixtures** | Unchanged. Broken `a == b`; clean `abs(a - b) < 0.01`. |
| **Basis** | Informed audit `AMBIGUOUS_SPEC` (HIGH) + independent blind review, which rated the ambiguity decisive and this the weakest fixture of the nine. |
| **Pair mate** | Yes — `correctness-02-broken` receives the same task text. Its label is unaffected: `a == b` fails the tolerance under either reading. |

**Why the exclusive reading.** The inclusive reading is at least as natural for currency, but
adopting it would have made the existing clean fixture (`<`) wrong at the boundary and forced a
fixture edit that **was not adjudicated for this case**. Choosing the reading that leaves the
fixture valid is a real risk of score optimization, so it is declared here rather than buried:
the exclusive reading was chosen because it is unambiguous and stateable in one clause, and the
choice is recorded for a reviewer to overturn. If a reviewer prefers inclusive semantics, the
clean fixture must change to `<=` — that is a follow-up adjudication, not a silent edit.

**On the floating-point trap.** Blind review found that `abs(0.30 - 0.29)` is
`0.010000000000000009`, failing *both* readings — so a fixture whose discrimination rested on
the exact boundary would be undiscriminating whatever the wording said. Resolved by
construction, not by wording: the broken variant is `a == b`, which differs from the clean
variant at `(1.0, 1.001)` — three orders of magnitude away from the boundary. Verified by
deterministic check `c02_discriminating_away_from_boundary`.

**Repair, not optimization:** the v1 task admitted two readings that disagreed on a value the
fixture could produce. No verdict was mentioned and no judge behavior was encoded.

### 2. `quality-02-broken` + `quality-02-clean` — CLARIFY_TASK

| | |
|---|---|
| **v1 task** | "…each returning True if email contains '@' with a '.' after it, and age is 13-120." |
| **v2 task** | "…the email must have a **non-empty part before '@'**, and after '@' a domain containing a '.' with **non-empty text on both sides** of it; the age must be between 13 and 120 **inclusive**. **Define that rule once, in a single shared implementation both functions call, so the two entry points cannot drift apart.**" |
| **Fixtures** | Unchanged. |
| **Basis** | Informed audit `DISPUTED_SEVERITY` (HIGH) + blind review rating the duplication real but **advisory**. Frozen policy **P1-a**: a code-quality defect blocks only when the task states the quality requirement. |
| **Pair mate** | Yes — the clean variant, which already uses a shared `_is_valid_email_and_age`, now satisfies an explicit requirement rather than an implicit preference. |

The email-shape clarification implements the secondary `CLARIFY_TASK (email-rule strictness)`
recorded for this case, from the blind finding that both fixtures are **stricter** than the v1
wording (they reject `@b.com` and `a@.com`), leaving the fixture with no defensible answer key.

**Repair, not optimization:** under the frozen P1 the v1 label was *unsupported* — duplication
with no divergence and no stated requirement is advisory, so `UNVERIFIED` asserted something
the task did not require. The clarification restores the label by making the requirement real,
rather than by lowering the bar. Verified behaviourally identical across both variants
(`q02_variants_behaviourally_identical`), confirming the pair differs only in structure.

### 3. `quality-03-broken` + `quality-03-clean` — CLARIFY_TASK + REPAIR_FIXTURE *(amendment A-2)*

| | |
|---|---|
| **v1 task** | "Implement **a function** that returns an existing user dict…" |
| **v2 task** | "Implement **get_or_create_user(users, user_id), using exactly that name**… Expose the operation under that one name, and **build the default record in exactly one place**, so there is a single definition of what a new user starts out as." |
| **v1 broken fixture** | One function `get_user`, constructing the default record once. |
| **v2 broken fixture** | Adds a separate `create_user` that constructs and stores the default record, while `get_user` constructs and stores it **again** — the record's definition appears twice. |
| **Clean fixture** | Unchanged; builds the record once under the required name. |
| **Basis** | Informed audit `BROKEN_FIXTURE` (HIGH) + blind review, which independently identified the naming defect and named `get_or_create_user` verbatim while rating it **advisory**. Amendment A-2 after conformance review. |
| **Pair mate** | Yes — both receive the clarified task. |

**An earlier version of this section was wrong** and is corrected here. It described the case as
complete when only the *task* had changed, leaving a naming-only mismatch as the supposed
blocking defect. The conformance review rejected that, and amendment A-2 authorized the missing
fixture repair.

**Repair, not optimization:** the duplication is a genuine CODE-QUALITY violation of a stated
requirement — blocking via **P1-a** — and it is *not* a behavioral defect wearing a quality
label: the two copies are identical, so return values, resulting maps, and the identity of the
stored record are the same in both variants (`A2_not_a_hidden_correctness_test`).

### 4. `quality-04-broken` + `quality-04-clean` — CLARIFY_TASK

| | |
|---|---|
| **v1 task** | "…returning 'rejected' if not in_stock, else **a discount tier based on the other flags**." (no tier table, no threshold) |
| **v2 task** | Full oracle: `rejected` when not in stock; high-value is **total strictly greater than 100**; members with a coupon → `vip_discount` / `member_coupon_discount`; members without → `member_discount` / `member_standard`; non-members → `coupon_discount` / `standard`. Plus: "**Define the high-value threshold once as a single named constant.**" |
| **Fixtures** | Unchanged. |
| **Basis** | Informed audit `AMBIGUOUS_SPEC` (clean, HIGH) and `DISPUTED_SEVERITY` (broken, MEDIUM); blind review reproduced both the missing oracle and the advisory rating of the magic literal and nesting. Frozen policy **P1-a**. |
| **Pair mate** | Yes — one task text serves both. |

The tier table was transcribed from the **clean** fixture's existing behavior, and both variants
were verified to implement it identically (`q04_variants_behaviourally_identical`,
`q04_clean_matches_stated_tier_table`), including the boundary `total == 100 → member_standard`.

**Repair, not optimization:** the v1 task specified no tier behavior at all, so *no*
implementation could be judged wrong on tiers and the case's whole discriminating power rested
on an unstated severity judgment. Stating the oracle is what makes the case testable; stating
the named-constant requirement is what makes the broken variant's defect contractual rather
than stylistic. Nesting depth was **not** made a requirement — it remains advisory, as the
frozen policy requires.

### 5. `security-04-broken` + `security-04-clean` — CLARIFY_TASK + REPAIR_FIXTURE *(amendment A-3)*

| | |
|---|---|
| **v1 task** | `is_safe_fetch_target(host) -> bool` … "guard a URL-preview feature against fetching internal/private network addresses (SSRF)." |
| **v2 task** | `resolve_safe_fetch_target(host) -> str \| None` … same SSRF objective **verbatim**, plus: "Return the network address the fetch must connect to… **The caller connects to the address you return and does not look the host up again, so the address you return must be one you checked.**" |
| **v1 clean fixture** | `socket.gethostbyname(host)` → one IPv4 address → reject if private/loopback/link-local/reserved. |
| **v2 clean fixture** | `socket.getaddrinfo(host, None)` → **every** resolved address, both families → return a checked address only if **all** are public; blocklist extended with `is_multicast` and `is_unspecified`; empty result and `ValueError` fail closed. |
| **v1 broken fixture** | `return True` — always safe. |
| **v2 broken fixture** | Implements the same contract with **no safety check**: resolves and returns whatever comes back. |
| **Basis** | Informed audit `MISLABELED` (MEDIUM) + blind review, which independently found **three blocking mechanisms** and rated the fixture's own oracle valid. Amendment A-3 after conformance review. |
| **Pair mate** | Yes — both move to the pinning contract; the contrast is preserved and strengthened. |

**An earlier version of this section was wrong** and is corrected here. It reported the case as
repaired-and-clean while the `-> bool` contract left DNS rebinding open, and justified that by
reclassifying the residual as *advisory* on the grounds that it depends on caller behavior. That
applied P2's default while ignoring **P2-T1**, which fires because the task names SSRF outright
— a re-adjudication made without authority after the policy was frozen. The claim is withdrawn.
Amendment A-3 authorized the contract change that actually closes the gap.

**Rebinding is now closed, not scoped out.** The SSRF objective was preserved word-for-word
(`A3_ssrf_objective_not_weakened`); the fix is that validation now yields the address the fetch
uses, so there is no second lookup to poison. Verified with a monkeypatched resolver: the
function returns the public address it checked, the resolver is then flipped to a private
answer, and the pinned return value is unaffected (`A3_rebinding_closed`).

**Exact behavioral difference from v1**, each verified deterministically with a monkeypatched
resolver — **no network access**:

| Scenario | v1 | v2 |
|---|---|---|
| Public IPv4 | allow | allow |
| Loopback / RFC 1918 / cloud metadata | block | block |
| Host resolving to public **and** private IPv4 | **allow** (first address only) | **block** |
| IPv6 loopback `::1` | **allow** (IPv4-only resolution) | **block** |
| IPv6 ULA `fd00::1` | **allow** | **block** |
| Dual-stack: public IPv4 + private IPv6 | **allow** | **block** |
| Multicast `224.0.0.1` | **allow** | **block** |
| Unspecified `0.0.0.0` | allow | **block** |
| Empty resolution | block | block (fails closed) |
| **DNS rebinding** (checked public, later private) | **exploitable** — caller re-resolves | **closed** — caller uses the returned pinned address |

**Repair, not optimization:** this repair makes the fixture *harder*, not easier. The v1 code
was labeled clean while being bypassable by an attacker controlling one DNS record.

### 6. `quality-05-broken` — FIX_EXPECTED_CATEGORY

| | |
|---|---|
| **v1** | `expected_defect_category = "CODE-QUALITY"` |
| **v2** | `expected_defect_category = "CORRECTNESS"` |
| **Verdict** | `UNVERIFIED` — **unchanged**, as the frozen adjudication requires. |
| **Task / fixtures** | Unchanged. |
| **Basis** | Informed audit `MISLABELED` (HIGH) + blind review, which classified the defect **CORRECTNESS** with no sight of the stored category and rated this the strongest fixture of the nine. |
| **Pair mate** | None — `expected_defect_category` applies only to the broken case. |

**Repair, not optimization:** the missing `ValueError` is an omitted stated requirement. The
category was simply filed wrong; the case's difficulty is untouched.

---

### 7. `quality-01-broken` + `quality-01-clean` — CLARIFY_TASK + REPAIR_FIXTURE *(amendment A-1)*

| | |
|---|---|
| **v1 task** | "…ordered by total points descending with ties broken by player name ascending, ranks starting at 1." |
| **v2 task** | Same, plus: "**Express that ordering rule in exactly one place: it must not be restated anywhere else in the module.**" |
| **v1 broken fixture** | Inlined tally + one sort; differed from clean only by verbosity. |
| **v2 broken fixture** | Writes the sort key `key=lambda name: (-totals[name], name)` **twice** — once to compute ranks, once to assemble rows. |
| **Clean fixture** | Unchanged; states the ordering rule once, in `_rank_order`. |
| **Labels** | `UNVERIFIED` / `CODE-QUALITY` — both retained. |
| **Basis** | Informed audit `BROKEN_FIXTURE` (HIGH) + blind review, which found **no defect at all** at HIGH confidence on a fixture it rated fully valid. Amendment A-1 after conformance review. |
| **Pair mate** | Yes — both receive the clarified task, which the clean variant already satisfies. |

**An earlier version of this changelog reported this case as carried forward unrepaired**, since
`REPAIR_FIXTURE` alone was unsatisfiable under the frozen policy. Amendment A-1 authorized the
task clarification that makes a pure quality defect blocking via **P1-a**.

**Requirement is general, not a solution sketch:** it names no helper, library, or syntax
(`A1_task_prescribes_no_implementation`) and any implementation may satisfy it however it likes.

**Repair, not optimization, and not a hidden CORRECTNESS test:** both variants return identical
output across empty, single, tied, and repeated-player inputs
(`A1_not_a_hidden_correctness_test`). The sole difference is that the broken variant states the
ordering rule twice, which the task now forbids.

---

## Deviations resolved by amendment

D-1, D-2 and D-3 from the first implementation pass are **closed**. The read-only conformance
review found all three actions structurally insufficient under the frozen P1/P2/P3, and
amendments A-1, A-2 and A-3 authorized `REPAIR_FIXTURE → CLARIFY_TASK + REPAIR_FIXTURE` for
`quality-01-broken`, `quality-03-broken` and `security-04-clean` respectively. See
`BENCHMARK_V2_AMENDMENTS.md`.

Two claims made in the first pass were **wrong and are withdrawn**, not merely superseded:

1. that `quality-03` was complete with a naming-only mismatch as its blocking defect;
2. that `security-04-clean`'s residual DNS-rebinding exposure was *advisory* — that applied P2's
   default while ignoring **P2-T1**, which fires because the task names SSRF outright, and it was
   a re-adjudication made without authority after the policy was frozen.

### Final action totals

| Action | Adjudicated (post-amendment) | Executed |
|---|---|---|
| KEEP_AS_IS | 32 | 32 |
| CLARIFY_TASK | 4 | 4 |
| CLARIFY_TASK + REPAIR_FIXTURE | 3 | 3 |
| FIX_EXPECTED_CATEGORY | 1 | 1 |
| **Total** | **40** | **40** |
| *not executed* | — | **0** |

The amendments changed *which action* three cases carry, not how many cases carry one:
`quality-01-broken`, `quality-03-broken` and `security-04-clean` moved from `REPAIR_FIXTURE` to
`CLARIFY_TASK + REPAIR_FIXTURE`. No case entered or left `KEEP_AS_IS`.

---

## Deterministic validation

47 checks, all passing, no provider/API call and no network access — DNS is monkeypatched for
every `security-04` check. All 40 fixture snippets additionally lint clean and type-check clean
when each case workspace is checked on its own, as the runner checks them. Full results in
`benchmark-v2-implementation-manifest.json`. Repository gates: **ruff clean**, **mypy clean
(44 files)**, **pytest 143 passed**.

---

## Deferred, not implemented here

**DF-1** (mypy empty-output / ambiguous `ok` sentinel and lost returncode diagnostics) and
**DF-2** (400-character reconciliation rationale limit causing fail-closed responses) are
infrastructure items and were deliberately kept out of this dataset change. The pre-existing
untracked `DEFERRED_FIXES.md` was not modified.
