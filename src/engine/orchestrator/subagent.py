import re
from pathlib import Path

from engine.providers.base import Message, Provider

SYSTEM_PROMPT = (
    "You are a senior software engineer sub-agent. You receive a coding task and must produce "
    "complete, working code plus tests when appropriate. Output ONLY file blocks in this exact "
    "format, one per file, nothing else before, between, or after them:\n\n"
    "FILE: relative/path.py\n"
    "```\n"
    "<full file content>\n"
    "```\n\n"
    "Use straightforward, idiomatic Python. Include a test file (test_*.py) if the task can be "
    "meaningfully tested."
)

FILE_BLOCK_RE = re.compile(r"FILE:\s*(?P<path>\S+)\s*```(?:\w+)?\n(?P<content>.*?)```", re.DOTALL)


def generate_code(
    provider: Provider, model: str, task_text: str, feedback: str | None = None
) -> str:
    prompt = task_text if not feedback else f"{task_text}\n\n{feedback}"
    result = provider.generate(
        messages=[Message(role="user", content=prompt)],
        model=model,
        system=SYSTEM_PROMPT,
        max_tokens=8000,
    )
    return result.text


def parse_files(response_text: str) -> dict[str, str]:
    return {
        m.group("path"): m.group("content")
        for m in FILE_BLOCK_RE.finditer(response_text)
    }


def write_files(workspace: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        target = workspace / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
