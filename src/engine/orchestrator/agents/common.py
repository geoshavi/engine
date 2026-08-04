import re
import sqlite3
from pathlib import Path

from engine.orchestrator.agents.base import AgentContext, AgentOutput
from engine.providers.base import Message
from engine.runtime.budget import BudgetController
from engine.runtime.gateway import LLMGateway

FILE_BLOCK_RE = re.compile(r"FILE:\s*(?P<path>\S+)\s*```(?:\w+)?\n(?P<content>.*?)```", re.DOTALL)


def generate_text(
    gateway: LLMGateway,
    budget: BudgetController,
    model: str,
    system_prompt: str,
    task_text: str,
    *,
    agent_name: str,
    run_id: int,
    task_id: str,
    conn: sqlite3.Connection | None,
    timeout_seconds: float | None,
    feedback: str | None = None,
) -> str:
    prompt = task_text if not feedback else f"{task_text}\n\n{feedback}"
    result = gateway.generate(
        budget=budget,
        messages=[Message(role="user", content=prompt)],
        model=model,
        system=system_prompt,
        max_tokens=8000,
        agent_name=agent_name,
        run_id=run_id,
        task_id=task_id,
        conn=conn,
        timeout_seconds=timeout_seconds,
    )
    return result.text


def parse_files(response_text: str) -> dict[str, str]:
    return {
        m.group("path"): m.group("content")
        for m in FILE_BLOCK_RE.finditer(response_text)
    }


def write_files(workspace: Path, files: dict[str, str]) -> list[str]:
    """Write generated files under ``workspace``, refusing anything that would
    escape it (absolute paths or ``..`` traversal in the model's FILE: lines).

    Returns the relative paths that were refused so the caller can treat them
    as a hard verification failure instead of silently dropping them.
    """
    workspace_root = workspace.resolve()
    skipped: list[str] = []
    for relative_path, content in files.items():
        target = (workspace_root / relative_path).resolve()
        if not target.is_relative_to(workspace_root):
            skipped.append(relative_path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return skipped


class PromptFileAgent:
    """Shared implementation for agents whose entire behavior is: load a
    static system prompt, ask the provider for FILE: blocks, write them into
    the workspace. Concrete agents just set ``role`` and ``prompt_path``.
    """

    role: str
    prompt_path: Path

    def run(self, context: AgentContext) -> AgentOutput:
        system_prompt = self.prompt_path.read_text().strip()
        response_text = generate_text(
            context.gateway,
            context.budget,
            context.model,
            system_prompt,
            context.task_text,
            agent_name=type(self).__name__,
            run_id=context.run_id,
            task_id=context.task_id,
            conn=context.conn,
            timeout_seconds=context.timeout_seconds,
            feedback=context.feedback,
        )
        files = parse_files(response_text)
        skipped_paths = write_files(context.workspace, files)
        return AgentOutput(files=files, skipped_paths=skipped_paths)
