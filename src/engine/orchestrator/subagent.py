import re
from pathlib import Path

from engine.providers.base import Message, Provider

AGENT_PROMPT_PATH = Path(__file__).parent / "agent.md"


def load_system_prompt() -> str:
    return AGENT_PROMPT_PATH.read_text().strip()


FILE_BLOCK_RE = re.compile(r"FILE:\s*(?P<path>\S+)\s*```(?:\w+)?\n(?P<content>.*?)```", re.DOTALL)


def generate_code(
    provider: Provider, model: str, task_text: str, feedback: str | None = None
) -> str:
    prompt = task_text if not feedback else f"{task_text}\n\n{feedback}"
    result = provider.generate(
        messages=[Message(role="user", content=prompt)],
        model=model,
        system=load_system_prompt(),
        max_tokens=8000,
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
