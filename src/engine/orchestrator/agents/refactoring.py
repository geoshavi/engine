from pathlib import Path

from engine.orchestrator.agents.common import PromptFileAgent


class RefactoringAgent(PromptFileAgent):
    role = "refactoring"
    prompt_path = Path(__file__).parent / "refactoring.md"
