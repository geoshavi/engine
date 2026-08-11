"""Export the benchmark's research lineage as an Obsidian-compatible vault.

Read-only by construction: `.engine/state.db` is copied to a temporary file and
opened `mode=ro` on the copy, so the live measurement history can never gain a
`-wal`/`-shm` sidecar or be mutated. `BASELINE.md` is read, never written.

Deterministic: no wall-clock timestamps are emitted, every query is ordered, and
notes are overwritten in place -- rerunning produces byte-identical output.

This tool is deliberately outside `src/`. It is not part of the measured
benchmark path and must never be imported by the engine.

Usage:  python tools/research_graph.py
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / ".engine" / "state.db"
BASELINE_PATH = REPO_ROOT / "BASELINE.md"
VAULT_DIR = REPO_ROOT / "research-vault"

# --- Chain of hub notes, in lineage order -----------------------------------

CHAIN: tuple[str, ...] = (
    "Architecture Overview",
    "Experiments Overview",
    "Registrations Overview",
    "Baselines Overview",
    "Run Records Overview",
    "Results Overview",
    "Decisions Overview",
    "Lessons Learned Overview",
)

# --- Phase 4 provenance ------------------------------------------------------
# Transcribed from BASELINE.md's Notes section. These are narrative facts that
# live in prose and commit messages rather than in any queryable table, so they
# are declared here rather than parsed. BASELINE.md remains the source of truth;
# if it and this block ever disagree, BASELINE.md wins.

COMMIT_NOTES: dict[str, tuple[str, str]] = {
    "c0515eb": (
        "Phase 4 baseline commit",
        (
            "Frozen configuration for the Phase 4 baseline arm. Added the benchmark "
            "safety and analysis agent skills only -- no engine, judge, or dataset change."
        ),
    ),
    "be990c7": (
        "Phase 4 intervention commit",
        (
            "Appended a source-verification and task-scope constraint to "
            "`RESPONSE_INSTRUCTION`, the instruction shared by all three judge lenses. "
            "LENSES, the JSON contract, the parser, `rubric.BLOCKING`, `verdict.gate`, "
            "and the dataset were unchanged."
        ),
    ),
    "64518fe": (
        "Phase 4 revert commit",
        (
            "Reverted be990c7, restoring `RESPONSE_INSTRUCTION` to its frozen c0515eb "
            "state. `git diff c0515eb 64518fe -- src/` returns empty, so the source tree "
            "is byte-identical to c0515eb despite the differing SHA."
        ),
    ),
}

BASELINE_ARM: tuple[int, ...] = (20, 21, 22, 23, 24, 25, 27, 28)
INTERVENTION_ARM: tuple[int, ...] = tuple(range(29, 37))

EXCLUDED_RUNS: dict[int, str] = {
    26: (
        "Excluded from the Phase 4 baseline arm under registered Amendment A1. Its "
        "`quality-04-clean` case recorded `eval_case_automated_gates.passed = 0` for the "
        "`mypy` gate while `detail` still read `ok` -- a silent gate failure indicating "
        "environment contamination rather than judge behaviour. The run has zero "
        "`eval_case_results.error` rows, so it is NOT disqualified under the standard "
        "error-row rule; this exclusion is narrower and specific to the Phase 4 arm."
    ),
}

ENGINE_RUN_ID = 38

# --- Data carriers -----------------------------------------------------------


@dataclass(frozen=True)
class EvalRun:
    """One row of `eval_runs`, enriched with derived counts and the BASELINE note."""

    run_id: int
    created_at: str
    commit_sha: str
    dataset_version: str
    total_cases: int
    correct_verdicts: int
    false_pass: int
    false_unverified: int
    total_cost: str
    error_rows: int
    schema_failures: int
    what_changed: str

    @property
    def short_sha(self) -> str:
        return self.commit_sha[:7]


@dataclass(frozen=True)
class EngineRun:
    """One row of `runs` -- a live engine execution, not a benchmark measurement."""

    run_id: int
    task_text: str
    provider: str
    model: str
    status: str
    attempts: int
    defect_count: int
    gate_rows: int


# --- Reading (never writing) -------------------------------------------------


def parse_baseline_notes(baseline_path: Path) -> dict[int, str]:
    """Pull the `what changed` column out of BASELINE.md's run table."""
    notes: dict[int, str] = {}
    if not baseline_path.exists():
        return notes
    for line in baseline_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 9 or not cells[0].isdigit():
            continue
        notes[int(cells[0])] = cells[8]
    return notes


def load_eval_runs(conn: sqlite3.Connection, notes: dict[int, str]) -> list[EvalRun]:
    errors = dict(
        conn.execute(
            "SELECT eval_run_id, COUNT(*) FROM eval_case_results "
            "WHERE error IS NOT NULL GROUP BY eval_run_id"
        ).fetchall()
    )
    schema_failures = dict(
        conn.execute(
            "SELECT r.eval_run_id, COUNT(*) FROM eval_case_schema_failures f "
            "JOIN eval_case_results r ON r.id = f.eval_case_result_id "
            "GROUP BY r.eval_run_id"
        ).fetchall()
    )
    rows = conn.execute(
        "SELECT id, created_at, git_commit_sha, dataset_version, total_cases, "
        "correct_verdicts, false_pass, false_unverified, total_cost "
        "FROM eval_runs WHERE id BETWEEN 1 AND 36 ORDER BY id"
    ).fetchall()
    return [
        EvalRun(
            run_id=row[0],
            created_at=str(row[1]),
            commit_sha=str(row[2] or ""),
            dataset_version=str(row[3] or "unknown"),
            total_cases=int(row[4] or 0),
            correct_verdicts=int(row[5] or 0),
            false_pass=int(row[6] or 0),
            false_unverified=int(row[7] or 0),
            total_cost=str(row[8] or "0"),
            error_rows=int(errors.get(row[0], 0)),
            schema_failures=int(schema_failures.get(row[0], 0)),
            what_changed=notes.get(row[0], "(not recorded in BASELINE.md)"),
        )
        for row in rows
    ]


def load_engine_run(conn: sqlite3.Connection, run_id: int) -> EngineRun | None:
    row = conn.execute(
        "SELECT id, task_text, provider, model, status, attempts FROM runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    defects = conn.execute("SELECT COUNT(*) FROM defects WHERE run_id = ?", (run_id,)).fetchone()
    gates = conn.execute(
        "SELECT COUNT(*) FROM verification_results WHERE run_id = ?", (run_id,)
    ).fetchone()
    return EngineRun(
        run_id=int(row[0]),
        task_text=str(row[1] or ""),
        provider=str(row[2] or ""),
        model=str(row[3] or ""),
        status=str(row[4] or ""),
        attempts=int(row[5] or 0),
        defect_count=int(defects[0]) if defects else 0,
        gate_rows=int(gates[0]) if gates else 0,
    )


# --- Note rendering ----------------------------------------------------------


def link(name: str) -> str:
    return f"[[{name}]]"


def frontmatter(note_type: str, tags: Iterable[str]) -> list[str]:
    joined = ", ".join(sorted(set(tags)))
    return ["---", f"type: {note_type}", f"tags: [{joined}]", "---", ""]


def lineage_footer(position: int) -> list[str]:
    lines = ["", "## Lineage", ""]
    if position > 0:
        lines.append(f"- Previous stage: {link(CHAIN[position - 1])}")
    if position < len(CHAIN) - 1:
        lines.append(f"- Next stage: {link(CHAIN[position + 1])}")
    chain = " -> ".join(link(name) for name in CHAIN)
    lines.append(f"- Full chain: {chain}")
    return lines


def eval_run_note_name(run_id: int) -> str:
    return f"Eval Run {run_id:02d}"


def commit_note_name(short_sha: str) -> str:
    return f"Commit {short_sha}"


def render_architecture(engine_run: EngineRun | None) -> str:
    lines = frontmatter("hub", ["architecture", "lineage"])
    lines += [
        "# Architecture Overview",
        "",
        "The system under study: an orchestrator that dispatches sub-agents, then gates their",
        "output through automated checks (`ruff`, `mypy`, `pytest`) and a three-lens LLM judge",
        "whose verdict fails closed on schema errors.",
        "",
        "## Measured surface",
        "",
        "- `src/engine/orchestrator/` -- agent dispatch and repair loop",
        "- `src/engine/verification/` -- automated gates, judge lenses, schema, verdict",
        "- `src/engine/eval/` -- the 40-case benchmark harness (20 tasks x broken/clean)",
        "- `src/engine/state/` -- SQLite persistence for runs, defects, and eval results",
        "",
        "## Why this matters",
        "",
        "The architecture exists to make AI-generated code changes *falsifiable*: a change is",
        "accepted only when the gates and the judge both allow it, and a rejection is recorded",
        "with the specific defects that caused it.",
    ]
    if engine_run is not None:
        target = link(f"Engine Run {engine_run.run_id}")
        lines += ["", f"See {target} for a live execution of this pipeline."]
    lines += lineage_footer(0)
    return "\n".join(lines) + "\n"


def render_experiments() -> str:
    baseline_links = ", ".join(link(eval_run_note_name(r)) for r in BASELINE_ARM)
    intervention_links = ", ".join(link(eval_run_note_name(r)) for r in INTERVENTION_ARM)
    lines = frontmatter("hub", ["experiment", "lineage"])
    lines += [
        "# Experiments Overview",
        "",
        "Experiments are pre-registered before any run. An observation only counts as movement",
        f"if it clears the measured noise floor -- see {link('Noise Floor v3')}.",
        "",
        "## Phase 4 -- judge-prompt calibration",
        "",
        "Tested whether blocking CRITICAL/HIGH findings on *clean* cases could be reduced when a",
        "finding is contradicted by the supplied source (Mechanism B) or rests on a requirement",
        "the task does not state (Mechanism C), without reducing task-supported findings",
        "(Mechanism A) or broken-case blocking.",
        "",
        "| Arm | Commit | Runs |",
        "|-----|--------|------|",
        f"| Baseline | {link(commit_note_name('c0515eb'))} | {baseline_links} |",
        f"| Intervention | {link(commit_note_name('be990c7'))} | {intervention_links} |",
        "",
        f"Reverted by {link(commit_note_name('64518fe'))}.",
        "",
        f"Exclusion applied to this experiment: {link('Amendment A1')}.",
    ]
    lines += lineage_footer(1)
    return "\n".join(lines) + "\n"


def render_registrations() -> str:
    lines = frontmatter("hub", ["registration", "lineage"])
    lines += [
        "# Registrations Overview",
        "",
        "A registration fixes the hypothesis, the arms, the metrics, and the acceptance and",
        "rejection criteria *before* the runs execute. Without it, a post-hoc reading of the",
        "accuracy column is not evidence.",
        "",
        "## Phase 4 registration",
        "",
        "- **H1** -- that the calibration would reduce clean-case blocking: **NOT SUPPORTED**",
        f"- **Amendment A1** -- see {link('Amendment A1')}",
        "- Registered baseline arm: n=8, mean correct 33.000, SD 0.756",
        "- Guardrails: Mechanism A via `security-04-clean`; broken-case blocking via the",
        "  18-case G2 set",
        "",
        "## Recoverability defect",
        "",
        "Commit `be990c7` cites `PHASE4_REGISTRATION.md` as its pre-registration, but that file",
        "was never committed -- it is absent from every branch, from deleted-file history, and",
        "from unreachable objects. The registered facts recoverable today come only from the",
        "`be990c7` and `64518fe` commit messages. The exact wording of H1, of section 14, and",
        "the G2 membership are **not recoverable from this repository**.",
        "",
        f"Consequence recorded in {link('Lessons Learned Overview')}.",
    ]
    lines += lineage_footer(2)
    return "\n".join(lines) + "\n"


def render_baselines(runs: list[EvalRun]) -> str:
    versions: dict[str, list[int]] = {}
    for run in runs:
        versions.setdefault(run.dataset_version, []).append(run.run_id)
    arm = ", ".join(str(r) for r in BASELINE_ARM)
    lines = frontmatter("hub", ["baseline", "lineage"])
    lines += [
        "# Baselines Overview",
        "",
        "`BASELINE.md` is the append-mostly evidence log. Scores are **not comparable across**",
        "**dataset-version boundaries**.",
        "",
        "| dataset version | runs |",
        "|-----------------|------|",
    ]
    for version in sorted(versions):
        ids = versions[version]
        lines.append(f"| {version} | {min(ids)}-{max(ids)} ({len(ids)} runs) |")
    lines += [
        "",
        "## Frozen Phase 4 baseline",
        "",
        f"Runs {arm} at {link(commit_note_name('c0515eb'))} (n=8): mean 33.000, SD 0.756.",
        f"Run 26 is held out -- see {link('Amendment A1')}.",
        "",
        f"Dispersion for this dataset version: {link('Noise Floor v3')}.",
    ]
    lines += lineage_footer(3)
    return "\n".join(lines) + "\n"


def render_run_records(runs: list[EvalRun], engine_run: EngineRun | None) -> str:
    lines = frontmatter("hub", ["runs", "lineage"])
    lines += [
        "# Run Records Overview",
        "",
        f"{len(runs)} benchmark runs read from `eval_runs` in `.engine/state.db`.",
        "",
        "| run | dataset | commit | correct | false_pass | false_unverified | err | schema |",
        "|-----|---------|--------|---------|------------|------------------|-----|--------|",
    ]
    for run in runs:
        flag = " (EXCLUDED)" if run.run_id in EXCLUDED_RUNS else ""
        note = link(eval_run_note_name(run.run_id))
        correct = f"{run.correct_verdicts}/{run.total_cases}{flag}"
        lines.append(
            f"| {note} | {run.dataset_version} | `{run.short_sha}` | {correct} "
            f"| {run.false_pass} | {run.false_unverified} | {run.error_rows} "
            f"| {run.schema_failures} |"
        )
    if engine_run is not None:
        target = link(f"Engine Run {engine_run.run_id}")
        lines += [
            "",
            "## Not part of the benchmark",
            "",
            f"{target} is a live engine execution, excluded from every baseline and every arm.",
        ]
    lines += lineage_footer(4)
    return "\n".join(lines) + "\n"


def render_results(runs: list[EvalRun]) -> str:
    by_id = {run.run_id: run for run in runs}
    baseline = [by_id[r].correct_verdicts for r in BASELINE_ARM if r in by_id]
    intervention = [by_id[r].correct_verdicts for r in INTERVENTION_ARM if r in by_id]
    baseline_counts = ", ".join(str(v) for v in baseline)
    intervention_counts = ", ".join(str(v) for v in intervention)
    finding = link("Finding security-03-clean")
    lines = frontmatter("hub", ["results", "lineage"])
    lines += [
        "# Results Overview",
        "",
        "## Phase 4 measured outcome -- INCONCLUSIVE",
        "",
        "| arm | n | correct counts | mean | SD |",
        "|-----|---|----------------|------|-----|",
        f"| Baseline | {len(baseline)} | {baseline_counts} | 33.000 | 0.756 |",
        f"| Intervention | {len(intervention)} | {intervention_counts} | 32.625 | 1.061 |",
        "",
        "The 0.375-case difference sits far inside the noise floor. **H1 was NOT SUPPORTED.**",
        "",
        "## Mechanism evidence moved opposite to the hypothesis",
        "",
        "Mean `false_unverified` *rose* from 5.11 (runs 20-28) to 5.38 (runs 29-36): blocking",
        "on clean cases increased rather than decreased.",
        "",
        "Only four cases moved at all:",
        "",
        "- `quality-02-clean` +55.6 pp (44.4% -> 100%)",
        "- `quality-04-clean` -1.4 pp",
        "- `edge_case-04-clean` -18.1 pp (55.6% -> 37.5%)",
        f"- `security-03-clean` -62.5 pp (100% -> 37.5%) -- see {finding}",
        "",
        "None of the four always-fail clean cases moved.",
    ]
    lines += lineage_footer(5)
    return "\n".join(lines) + "\n"


def render_decisions() -> str:
    revert = link(commit_note_name("64518fe"))
    amendment = link("Amendment A1")
    sigma = link("Noise Floor v3")
    lines = frontmatter("hub", ["decision", "lineage"])
    lines += [
        "# Decisions Overview",
        "",
        "| decision | basis |",
        "|----------|-------|",
        (
            f"| Revert the Phase 4 calibration | {revert} -- effect inside the noise "
            "floor, mechanism evidence inverted |"
        ),
        f"| Exclude run 26 from the baseline arm | {amendment} -- silent `mypy` gate failure |",
        (
            "| Keep `quality-01` / `quality-03` at UNVERIFIED | changing them would assert "
            "no quality defect exists, which stored evidence contradicts |"
        ),
        f"| Supersede the provisional v2 sigma | {sigma} -- v3 now directly measured |",
        "",
        "## What was decided *not* to do",
        "",
        "No dataset change, no judge change, and no prompt change was made on the strength of",
        "Phase 4. An inconclusive result is a reason to stop, not a reason to keep tuning until",
        "the accuracy column moves.",
    ]
    lines += lineage_footer(6)
    return "\n".join(lines) + "\n"


def render_lessons() -> str:
    registrations = link("Registrations Overview")
    sigma = link("Noise Floor v3")
    finding = link("Finding security-03-clean")
    lines = frontmatter("hub", ["lessons", "lineage"])
    lines += [
        "# Lessons Learned Overview",
        "",
        "1. **Commit the registration with the intervention.** Phase 4's registration file was",
        f"   never committed; see {registrations}. The full wording of H1 is unrecoverable, so",
        "   the experiment can be described but not fully reproduced.",
        f"2. **Measure the noise floor before believing a delta.** {sigma} makes most",
        "   single-run movements uninterpretable on their own.",
        f"3. **Pre-register the guardrails you will actually need.** {finding} was the largest",
        "   per-case movement Phase 4 produced and was not a registered guardrail, so it is an",
        "   unregistered adverse finding rather than a triggered rejection criterion.",
        "4. **A verdict flip can be one severity boundary.** Verdicts move when a single defect",
        "   crosses MEDIUM/HIGH on byte-identical input -- accuracy alone hides the mechanism.",
        "5. **Separate what the code does from what a run measured.** Code is verified by the",
        "   gates; a hypothesis is verified by a pre-registered experiment.",
    ]
    lines += lineage_footer(7)
    return "\n".join(lines) + "\n"


def render_eval_run(run: EvalRun) -> str:
    excluded = run.run_id in EXCLUDED_RUNS
    tags = ["run", "benchmark", run.dataset_version]
    if excluded:
        tags.append("excluded")
    lines = frontmatter("eval-run", tags)
    lines += [
        f"# Eval Run {run.run_id:02d}",
        "",
        "| field | value |",
        "|-------|-------|",
        f"| run id | {run.run_id} |",
        f"| recorded at | {run.created_at} |",
        f"| commit | `{run.short_sha}` |",
        f"| dataset version | {run.dataset_version} |",
        f"| correct verdicts | {run.correct_verdicts}/{run.total_cases} |",
        f"| false_pass | {run.false_pass} |",
        f"| false_unverified | {run.false_unverified} |",
        f"| error rows | {run.error_rows} |",
        f"| schema failures | {run.schema_failures} |",
        f"| total cost | {run.total_cost} |",
        "",
        "## What changed",
        "",
        run.what_changed,
    ]
    if excluded:
        lines += [
            "",
            "## Excluded from the Phase 4 baseline arm",
            "",
            EXCLUDED_RUNS[run.run_id],
            "",
            f"Recorded under {link('Amendment A1')}.",
        ]
    if run.error_rows:
        lines += [
            "",
            "> **Not usable as a measurement.** This run has error rows, so `correct_verdicts`",
            (
                "> is counted over non-error rows but reported against a denominator of "
                f"{run.total_cases}."
            ),
        ]
    lines += ["", "## Provenance", ""]
    if run.short_sha in COMMIT_NOTES:
        lines.append(f"- Configuration: {link(commit_note_name(run.short_sha))}")
    if run.run_id in BASELINE_ARM:
        lines.append(f"- Phase 4 **baseline** arm member -- {link('Baselines Overview')}")
    if run.run_id in INTERVENTION_ARM:
        lines.append(f"- Phase 4 **intervention** arm member -- {link('Experiments Overview')}")
    lines += [
        f"- Indexed by: {link('Run Records Overview')}",
        f"- Contributes to: {link('Results Overview')}",
    ]
    return "\n".join(lines) + "\n"


def render_engine_run(run: EngineRun) -> str:
    lines = frontmatter("engine-run", ["run", "engine", "not-benchmark"])
    lines += [
        f"# Engine Run {run.run_id}",
        "",
        "> **NOT part of the benchmark baseline.** This is a live execution of the engine on",
        "> an ad-hoc task. It writes to the `runs` table, never to `eval_runs`, and it is",
        "> excluded from every baseline, every experiment arm, and every accuracy figure.",
        "",
        "| field | value |",
        "|-------|-------|",
        f"| run id | {run.run_id} |",
        f"| task | {run.task_text} |",
        f"| provider / model | {run.provider} / {run.model} |",
        f"| status | {run.status.upper()} |",
        f"| attempts | {run.attempts} |",
        f"| recorded defects | {run.defect_count} |",
        f"| verification gate rows | {run.gate_rows} |",
        "",
        "## Why it matters",
        "",
        "The run ended FAILED after three repair attempts. That is the pipeline working as",
        "designed: the automated gates and judge refused to certify code that had not met the",
        "bar, and recorded the specific defects that blocked it, rather than returning a",
        "plausible-looking pass.",
        "",
        "## Provenance",
        "",
        f"- Pipeline described in: {link('Architecture Overview')}",
        f"- Listed under: {link('Run Records Overview')}",
    ]
    return "\n".join(lines) + "\n"


def render_commit(short_sha: str, title: str, body: str) -> str:
    lines = frontmatter("commit", ["commit", "provenance"])
    lines += [
        f"# Commit {short_sha}",
        "",
        f"**{title}**",
        "",
        body,
        "",
        "## Referenced by",
        "",
        f"- {link('Experiments Overview')}",
        f"- {link('Decisions Overview')}",
    ]
    return "\n".join(lines) + "\n"


def render_amendment_a1() -> str:
    lines = frontmatter("amendment", ["registration", "exclusion"])
    lines += [
        "# Amendment A1",
        "",
        "A registered amendment to the Phase 4 experiment, excluding a single run from the",
        "baseline arm.",
        "",
        EXCLUDED_RUNS[26],
        "",
        "## Effect on the arm",
        "",
        "- Registered baseline (A1 applied, n=8): mean 33.000, SD 0.756",
        "- Inclusive of run 26 (n=9): mean 32.889, SD 0.782",
        "",
        "## Links",
        "",
        f"- Applies to: {link(eval_run_note_name(26))}",
        f"- Registered under: {link('Registrations Overview')}",
        f"- Decision recorded in: {link('Decisions Overview')}",
    ]
    return "\n".join(lines) + "\n"


def render_adverse_finding() -> str:
    lines = frontmatter("finding", ["adverse-finding", "unregistered"])
    lines += [
        "# Finding security-03-clean",
        "",
        "**Unregistered adverse finding.**",
        "",
        "`security-03-clean` fell from 9/9 (100%) in runs 20-28 to 3/8 (37.5%) in runs 29-36 --",
        "the single largest per-case movement Phase 4 produced.",
        "",
        "It was **not** among the registered guardrails: the registration guarded Mechanism A",
        "via `security-04-clean` and broken-case blocking via the 18-case G2 set. It is",
        "therefore recorded as an unregistered adverse finding, **not** as a triggered",
        "rejection criterion.",
        "",
        "## Carried forward",
        "",
        "This case should be a pre-registered guardrail in any future intervention that touches",
        "judge severity calibration.",
        "",
        "## Links",
        "",
        f"- Surfaced by: {link('Results Overview')}",
        f"- Lesson recorded in: {link('Lessons Learned Overview')}",
    ]
    return "\n".join(lines) + "\n"


def render_noise_floor() -> str:
    baseline_commit = link(commit_note_name("c0515eb"))
    intervention_commit = link(commit_note_name("be990c7"))
    lines = frontmatter("measurement", ["variance", "noise-floor"])
    lines += [
        "# Noise Floor v3",
        "",
        "**Pooled v3 sigma = 0.92 cases.**",
        "",
        "First direct measurement on dataset v3, from two identical-configuration clusters:",
        "",
        "| cluster | commit | n | SD |",
        "|---------|--------|---|-----|",
        f"| Baseline runs 20-28 | {baseline_commit} | 9 | 0.782 |",
        f"| Baseline runs 20-25, 27-28 (A1 applied) | {baseline_commit} | 8 | 0.756 |",
        f"| Intervention runs 29-36 | {intervention_commit} | 8 | 1.061 |",
        "",
        "0.9225 using the inclusive n=9 baseline, 0.9210 using the A1-excluded n=8 baseline --",
        "the A1 treatment does not change the pooled figure.",
        "",
        "**This supersedes the provisional sigma ~= 1.25 carried over from v2.** The v2 figure",
        "should no longer be applied to v3 work.",
        "",
        "## Links",
        "",
        f"- Constrains: {link('Experiments Overview')}",
        f"- Applied in: {link('Results Overview')}",
        f"- Superseding decision: {link('Decisions Overview')}",
    ]
    return "\n".join(lines) + "\n"


# --- Orchestration -----------------------------------------------------------


def build_notes(runs: list[EvalRun], engine_run: EngineRun | None) -> dict[str, str]:
    notes: dict[str, str] = {
        "Architecture Overview": render_architecture(engine_run),
        "Experiments Overview": render_experiments(),
        "Registrations Overview": render_registrations(),
        "Baselines Overview": render_baselines(runs),
        "Run Records Overview": render_run_records(runs, engine_run),
        "Results Overview": render_results(runs),
        "Decisions Overview": render_decisions(),
        "Lessons Learned Overview": render_lessons(),
        "Amendment A1": render_amendment_a1(),
        "Finding security-03-clean": render_adverse_finding(),
        "Noise Floor v3": render_noise_floor(),
    }
    for short_sha, (title, body) in COMMIT_NOTES.items():
        notes[commit_note_name(short_sha)] = render_commit(short_sha, title, body)
    for run in runs:
        notes[eval_run_note_name(run.run_id)] = render_eval_run(run)
    if engine_run is not None:
        notes[f"Engine Run {engine_run.run_id}"] = render_engine_run(engine_run)
    return notes


def export(db_path: Path, baseline_path: Path, out_dir: Path) -> list[Path]:
    """Read the sources and write the vault. Returns the written paths, sorted."""
    if not db_path.exists():
        raise SystemExit(f"state database not found: {db_path}")

    notes_by_run = parse_baseline_notes(baseline_path)

    # Copy first, then read the copy -- the live database is the only record of
    # the measurement history and is untracked and unbacked-up.
    with tempfile.TemporaryDirectory() as tmp:
        copy_path = Path(tmp) / "state-copy.db"
        shutil.copy2(db_path, copy_path)
        conn = sqlite3.connect(f"{copy_path.as_uri()}?mode=ro", uri=True)
        try:
            runs = load_eval_runs(conn, notes_by_run)
            engine_run = load_engine_run(conn, ENGINE_RUN_ID)
        finally:
            conn.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, body in sorted(build_notes(runs, engine_run).items()):
        path = out_dir / f"{name}.md"
        path.write_text(body, encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    written = export(DB_PATH, BASELINE_PATH, VAULT_DIR)
    print(f"Wrote {len(written)} notes to {VAULT_DIR.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
