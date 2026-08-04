from engine.orchestrator.agents.base import Agent
from engine.orchestrator.agents.coding import CodingAgent
from engine.orchestrator.agents.refactoring import RefactoringAgent
from engine.orchestrator.agents.research import ResearchAgent
from engine.orchestrator.agents.testing import TestingAgent

AGENT_REGISTRY: dict[str, Agent] = {
    "coding": CodingAgent(),
    "research": ResearchAgent(),
    "testing": TestingAgent(),
    "refactoring": RefactoringAgent(),
}


def get_agent(role: str) -> Agent:
    try:
        return AGENT_REGISTRY[role]
    except KeyError:
        raise ValueError(f"Unknown agent role: {role!r}. Registered roles: {sorted(AGENT_REGISTRY)}") from None
