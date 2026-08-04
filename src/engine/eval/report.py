"""Formatting for `engine bench`'s three output modes: --dry-run's plan,
the normal post-run report, and --compare's diff against a prior run. Pure
string formatting -- no LLM calls, no DB access; callers pass in already-
loaded data.
"""

from collections import Counter
from decimal import Decimal

from engine.eval.dataset import (
    BENCHMARK_VERSION,
    DATASET_VERSION,
    EvalCase,
    validate_dataset,
)
from engine.eval.runner import (
    BENCHMARK_PLANNED_BUDGET,
    estimate_benchmark_cost,
)
from engine.runtime.budget import round_for_display
from engine.state.models import EvalCaseResult, EvalRun

# Display order and labels match the format specified for --dry-run exactly
# ("Security" before "Correctness", "Edge" not "Edge_case").
CATEGORY_DISPLAY_NAMES = {
    "security": "Security",
    "correctness": "Correctness",
    "quality": "Quality",
    "edge_case": "Edge",
}


def _signed_decimal(amount: Decimal) -> str:
    return f"+{amount}" if amount >= 0 else str(amount)


def format_dry_run_plan(cases: list[EvalCase], judge_model: str) -> tuple[str, list[str]]:
    """Zero LLM calls. Returns (plan_text, dataset_validation_errors) --
    callers should treat a non-empty errors list as a reason not to proceed.
    """
    errors = validate_dataset(cases)
    counts = Counter(c.category for c in cases)
    estimated_cost = round_for_display(estimate_benchmark_cost(len(cases), judge_model))

    lines = ["Benchmark plan:", f"  Cases: {len(cases)}"]
    for category, label in CATEGORY_DISPLAY_NAMES.items():
        lines.append(f"  {label}: {counts.get(category, 0)}")
    lines.append(f"  dataset_version: {DATASET_VERSION}")
    lines.append(f"  benchmark_version: {BENCHMARK_VERSION}")
    lines.append(f"  Estimated max cost: ${estimated_cost}")
    lines.append(f"  Benchmark budget ceiling: ${BENCHMARK_PLANNED_BUDGET}")

    if estimated_cost > BENCHMARK_PLANNED_BUDGET:
        lines.append("")
        lines.append(
            f"WARNING: estimated max cost ${estimated_cost} exceeds the "
            f"${BENCHMARK_PLANNED_BUDGET} budget ceiling."
        )

    if errors:
        lines.append("")
        lines.append("WARNING: dataset validation failed:")
        for error in errors:
            lines.append(f"  - {error}")

    return "\n".join(lines), errors


def format_benchmark_report(eval_run: EvalRun, results: list[EvalCaseResult]) -> str:
    error_count = sum(1 for r in results if r.error is not None)
    scored = eval_run.correct_verdicts + eval_run.false_pass + eval_run.false_unverified
    accuracy_pct = (eval_run.correct_verdicts / scored * 100) if scored else 0.0

    header = (
        f"Benchmark run #{eval_run.id} ({eval_run.benchmark_name} {eval_run.benchmark_version}, "
        f"dataset {eval_run.dataset_version})"
    )
    lines = [
        header,
        f"  git commit: {eval_run.git_commit_sha}",
        f"  Cases: {eval_run.total_cases} ({scored} scored, {error_count} error)",
        f"  Correct verdicts: {eval_run.correct_verdicts}/{scored} ({accuracy_pct:.1f}%)",
        f"  False pass: {eval_run.false_pass}",
        f"  False unverified: {eval_run.false_unverified}",
        "",
        "Category accuracy:",
    ]
    for category, label in CATEGORY_DISPLAY_NAMES.items():
        if category in eval_run.category_accuracy:
            lines.append(f"  {label}: {eval_run.category_accuracy[category] * 100:.1f}%")

    lines.append("")
    lines.append(
        f"Cost: ${round_for_display(eval_run.total_cost)} total, "
        f"${round_for_display(eval_run.average_cost)} average per case"
    )
    total_latency = sum(r.latency_ms for r in results)
    lines.append(f"Latency: {total_latency}ms total, {eval_run.average_latency}ms average per case")

    error_rows = [r for r in results if r.error is not None]
    if error_rows:
        lines.append("")
        lines.append("Errors (excluded from accuracy, cost still counted above):")
        for r in error_rows:
            lines.append(f"  {r.eval_case_id}: {r.error}")

    return "\n".join(lines)


def detect_version_mismatch(current: EvalRun, previous: EvalRun) -> list[str]:
    warnings: list[str] = []
    if current.dataset_version != previous.dataset_version:
        warnings.append(
            f"dataset_version differs (current={current.dataset_version!r}, "
            f"previous={previous.dataset_version!r}) -- comparison may not be meaningful."
        )
    if current.benchmark_version != previous.benchmark_version:
        warnings.append(
            f"benchmark_version differs (current={current.benchmark_version!r}, "
            f"previous={previous.benchmark_version!r}) -- comparison may not be meaningful."
        )
    return warnings


def format_comparison(
    current: EvalRun,
    current_results: list[EvalCaseResult],
    previous: EvalRun,
    previous_results: list[EvalCaseResult],
) -> str:
    lines = [f"Comparing eval run #{current.id} against #{previous.id}"]

    for warning in detect_version_mismatch(current, previous):
        lines.append(f"WARNING: {warning}")

    previous_by_case = {r.eval_case_id: r for r in previous_results}

    verdict_changes: list[tuple[str, str, str]] = []
    category_changes: list[tuple[str, list[str], list[str]]] = []
    for r in current_results:
        prev = previous_by_case.get(r.eval_case_id)
        if prev is None:
            continue
        if r.actual_verdict != prev.actual_verdict:
            verdict_changes.append((r.eval_case_id, prev.actual_verdict, r.actual_verdict))
        if sorted(r.detected_defect_categories) != sorted(prev.detected_defect_categories):
            category_changes.append(
                (r.eval_case_id, prev.detected_defect_categories, r.detected_defect_categories)
            )

    lines.append("")
    lines.append("Verdict changes:" if verdict_changes else "Verdict changes: none")
    for case_id, verdict_before, verdict_after in verdict_changes:
        lines.append(f"  {case_id}: {verdict_before} -> {verdict_after}")

    lines.append("")
    lines.append("Defect category changes:" if category_changes else "Defect category changes: none")
    for case_id, categories_before, categories_after in category_changes:
        lines.append(f"  {case_id}: {categories_before} -> {categories_after}")

    cost_deltas: list[tuple[str, Decimal, Decimal, Decimal]] = []
    latency_deltas: list[tuple[str, int, int, int]] = []
    for r in current_results:
        prev = previous_by_case.get(r.eval_case_id)
        if prev is None:
            continue
        cost_delta = r.cost - prev.cost
        if cost_delta != 0:
            cost_deltas.append((r.eval_case_id, prev.cost, r.cost, cost_delta))
        latency_delta = r.latency_ms - prev.latency_ms
        if latency_delta != 0:
            latency_deltas.append((r.eval_case_id, prev.latency_ms, r.latency_ms, latency_delta))

    lines.append("")
    lines.append("Cost delta by case:" if cost_deltas else "Cost delta by case: none")
    for case_id, cost_before, cost_after, cost_delta in cost_deltas:
        lines.append(f"  {case_id}: {_signed_decimal(cost_delta)} (${cost_before} -> ${cost_after})")

    lines.append("")
    lines.append("Latency delta by case:" if latency_deltas else "Latency delta by case: none")
    for case_id, latency_before, latency_after, latency_delta in latency_deltas:
        lines.append(f"  {case_id}: {latency_delta:+d}ms ({latency_before}ms -> {latency_after}ms)")

    total_cost_diff = current.total_cost - previous.total_cost
    total_latency_current = sum(r.latency_ms for r in current_results)
    total_latency_previous = sum(r.latency_ms for r in previous_results)
    total_latency_diff = total_latency_current - total_latency_previous

    lines.append("")
    lines.append(
        f"Total cost difference: {_signed_decimal(total_cost_diff)} "
        f"(${previous.total_cost} -> ${current.total_cost})"
    )
    lines.append(
        f"Total latency difference: {total_latency_diff:+d}ms "
        f"({total_latency_previous}ms -> {total_latency_current}ms)"
    )

    return "\n".join(lines)
