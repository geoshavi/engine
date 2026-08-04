from pathlib import Path

from engine.orchestrator.agents.common import PromptFileAgent


class CodingAgent(PromptFileAgent):
    role = "coding"
    prompt_path = Path(__file__).parent / "coding.md"
