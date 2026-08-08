"""CLI-facing entrypoint. All real orchestration logic lives in
task_analyzer.py (classification) -> execution_plan.py (turning that into a
concrete plan) -> manager.py (executing it). This module's only remaining
job is to preserve the ``run_task(...) -> RunResult`` call shape cli.py
already depends on.
"""

from pathlib import Path

from engine.config import DEFAULT_MODELS, Config
from engine.orchestrator.execution_plan import build_execution_plan
from engine.orchestrator.manager import OrchestratorManager
from engine.orchestrator.task_analyzer import classify_task
from engine.runtime.gateway import LLMGateway
from engine.state.models import RunResult


def run_task(
    task_text: str, workspace: Path, gateway: LLMGateway, config: Config, provider_name: str = "anthropic"
) -> RunResult:
    analysis = classify_task(task_text)
    plan = build_execution_plan(analysis, config)
    manager = OrchestratorManager(gateway, DEFAULT_MODELS[provider_name])
    return manager.execute(plan, workspace, config, provider_name)
