from engine.state.models import RunResult


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
    for attempt_number, record in enumerate(result.verification_history, start=1):
        lines.append(f"## Attempt {attempt_number} - verdict: {record.status}")
        for r in record.automated_results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"- [{status}] {r.gate_name}")

        defects = record.merged_critic.get("defects", [])
        if defects:
            lines.append("\nDefects:")
            for d in defects:
                lines.append(
                    f"- [{d.get('severity')}] {d.get('category')} @ {d.get('location')}: "
                    f"{d.get('fix')}"
                )

        schema_errors = record.merged_critic.get("schema_errors", [])
        for err in schema_errors:
            lines.append(f"- [SCHEMA ERROR] {err}")

        lines.append("")
    return "\n".join(lines)
