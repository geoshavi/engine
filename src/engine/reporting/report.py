from engine.orchestrator.engine import RunResult


def generate_report(result: RunResult) -> str:
    lines = [
        f"# Engine run #{result.run_id}",
        "",
        f"**Task:** {result.task_text}",
        f"**Workspace:** {result.workspace}",
        f"**Result:** {'PASSED' if result.passed else 'FAILED'}",
        f"**Attempts:** {result.attempts}",
        "",
    ]
    for attempt_number, results in enumerate(result.verification_history, start=1):
        lines.append(f"## Attempt {attempt_number}")
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"- [{status}] {r.gate_name}")
            if not r.passed:
                detail = r.detail.strip().replace("\n", "\n  ")
                lines.append(f"  ```\n  {detail}\n  ```")
        lines.append("")
    return "\n".join(lines)
