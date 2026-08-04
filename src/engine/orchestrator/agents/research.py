from pathlib import Path

from engine.orchestrator.agents.common import PromptFileAgent


class ResearchAgent(PromptFileAgent):
    role = "research"
    prompt_path = Path(__file__).parent / "research.md"
