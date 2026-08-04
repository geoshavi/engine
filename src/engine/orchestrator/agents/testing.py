from pathlib import Path

from engine.orchestrator.agents.common import PromptFileAgent


class TestingAgent(PromptFileAgent):
    role = "testing"
    prompt_path = Path(__file__).parent / "testing.md"
