# Benchmark v2 — Formal Amendment Record A-1 / A-2 / A-3

Authorized after the read-only implementation-conformance review returned
`FORMAL_AMENDMENT_REQUIRED`. Scope is these three cases only.

## What was NOT changed

- **P1, P2 and P3 are untouched.** No blocking condition, trigger, default, or verdict
  semantic was added, removed, reworded, or reinterpreted. The amendments change *case
  actions*, never the policy those actions are judged against.
- **No unrelated case was reopened.** The 31 `KEEP_AS_IS` cases, `correctness-02`,
  `quality-02`, `quality-04` and `quality-05-broken` are exactly as adjudicated.
- **No score or run outcome informed any amendment.** No benchmark has been run under v2, no
  provider call was made, and `.engine/state.db` was never opened. Each amendment was derived
  from the frozen records plus the fixture source alone. Two of the three make the dataset
  *harder*, which is the opposite of what score optimization would produce.

## Why these became necessary only after implementation-conformance review

The formal adjudication assigned actions **before** the severity policy was frozen, and the
policy adjudication fixed P1/P2/P3 **without** re-deriving whether each earlier action was still
executable under them. Implementation was the first step that had to satisfy both records at
once, and that is where three actions turned out to be structurally insufficient — not wrong
about the defect, but unable to reach a defensible label using the action as written.

This is the intended function of a conformance gate: it caught the gap before the dataset was
declared ready, not after runs had been spent against it.

---

## A-1 — `quality-01-broken`

**`REPAIR_FIXTURE` → `CLARIFY_TASK + REPAIR_FIXTURE`**

Retained: `expected_verdict = UNVERIFIED`, `expected_defect_category = CODE-QUALITY`.

**Why insufficient as written.** Under frozen P3, `UNVERIFIED` asserts a defect earning
CRITICAL/HIGH. Under frozen P1 a pure CODE-QUALITY defect reaches that only via **P1-a** (a
stated quality requirement) or **P1-b** (present behavioral consequence). `quality-01` had no
adjudicated `CLARIFY_TASK`, so P1-a was unavailable; and every P1-b candidate produces output
violating the stated leaderboard contract, which **P1-c** then routes to CORRECTNESS — needing a
category change also not adjudicated. `REPAIR_FIXTURE` alone was therefore unsatisfiable.

**Implemented.** Task gains one general clause: *"Express that ordering rule in exactly one
place: it must not be restated anywhere else in the module."* It names no helper, library, or
syntax — verified by `A1_task_prescribes_no_implementation`. The broken fixture now writes the
sort key `key=lambda name: (-totals[name], name)` **twice** (once to compute ranks, once to
assemble rows); the clean fixture states it once inside `_rank_order`.

**Not a hidden CORRECTNESS test:** both variants return byte-identical output across five
probe inputs including empty, single, tied, and repeated-player cases
(`A1_not_a_hidden_correctness_test`). The only difference is that the ordering rule is stated
twice, which the task now forbids.

---

## A-2 — `quality-03-broken`

**`REPAIR_FIXTURE` → `CLARIFY_TASK + REPAIR_FIXTURE`**

**Why insufficient as written.** The prior working-tree implementation changed only the task, so
that the pre-existing `get_user` naming mismatch became contractual. The review found — and I
agree — that this is a *material action change*, not an implementation detail: the fixture was
never repaired, and a naming-only mismatch is not an acceptable blocking defect.

**Implemented.** Task states two general requirements: expose the operation under the single
name `get_or_create_user`, **and** *"build the default record in exactly one place, so there is
a single definition of what a new user starts out as."* The broken fixture now carries a real
duplication defect beyond the name: it defines a separate `create_user` that constructs and
stores the default record, while `get_user` constructs and stores it again — the record's
definition appears **twice** (`A2_broken_duplicates_record_construction`). The clean fixture
builds it once.

**Not a behavioral defect mislabeled as quality:** the two copies are identical, so
get-or-create semantics are unchanged — verified equal return values, equal resulting maps, and
identity (`is`) of the stored record in both variants (`A2_not_a_hidden_correctness_test`).

---

## A-3 — `security-04-clean`

**`REPAIR_FIXTURE` → `CLARIFY_TASK + REPAIR_FIXTURE`**

Retained: `expected_verdict = OK`.

**Why insufficient as written.** The task explicitly names SSRF, so **P2-T1** fires and a known
SSRF bypass is blocking. DNS rebinding cannot be closed inside a `-> bool` contract, because a
boolean cannot carry the vetted address — the caller must resolve again, and the second answer
can differ. The frozen formal adjudication said exactly this: blocking, *"with the caveat that
the remedy requires changing the function's contract."* A contract change is a task change,
which `REPAIR_FIXTURE` alone did not authorize.

**This also corrects an error of mine.** The first implementation reclassified the residual
rebinding exposure as *advisory* on the grounds that it depends on caller behavior. That applied
P2's default while ignoring the trigger that actually fires, and it was a re-adjudication I had
no authority to make after the policy was frozen. The claim is withdrawn and the changelog text
is corrected.

**Implemented.** The SSRF objective is preserved verbatim — *"guard a URL-preview feature
against fetching internal/private network addresses (SSRF)"* — and was **not** narrowed to
exclude rebinding (`A3_ssrf_objective_not_weakened`). The contract becomes:

> `resolve_safe_fetch_target(host) -> str | None` … *"Return the network address the fetch must
> connect to, or None when the host has no safe address. The caller connects to the address you
> return and does not look the host up again, so the address you return must be one you
> checked."*

The clean fixture resolves via `getaddrinfo` (both families), rejects unless **every** resolved
address is public — excluding private, loopback, link-local, reserved, multicast and
unspecified — and returns a checked address, failing closed on resolution error or empty result.

**Rebinding verified closed** by a monkeypatched resolver, no network: the function returns the
public address it checked; the resolver is then flipped to a private answer; the pinned return
value is unaffected and the caller has no reason to consult DNS again
(`A3_rebinding_closed`, `A3_returned_address_was_checked`).

**Contrast preserved:** the broken variant implements the same contract with no safety check at
all — it resolves and returns whatever comes back — so it still fails the stated guard
(`A3_broken_preserves_contrast`).

---

## `correctness-02` — no amendment

The clarification stands as implemented: *"differ by less than 0.01… a difference of exactly
0.01 is not close enough."* No fixture or test repair was added.

---

## Deterministic validation

47 checks, all passing. No benchmark, no provider/API call, no network — DNS is monkeypatched
for every `security-04` check. Repository gates: ruff clean, mypy clean (44 files), pytest 143
passed. All 40 fixture snippets additionally lint clean and type-check clean when each case
workspace is checked on its own, as the runner checks them.

Benchmark v1 remains reconstructible: `CASES_V1` rebuilds 40 cases and validates clean, with the
pre-amendment forms of `quality-01`, `quality-03` and `security-04` archived
(`v1_q01_broken_is_original`, `v1_q03_broken_is_original`, `v1_s04_is_original`).
