from collections.abc import Callable
from openai import OpenAI

from backend.app.application.agents.strategy_agent import IntegratedStrategyAgentService
from backend.app.application.agents.strategy_agent.graph import build_graph
from backend.app.config import HiringSettings


def create_strategy_agent_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[[], OpenAI] | None = None,
) -> IntegratedStrategyAgentService:
    resolved = settings or HiringSettings()
    if resolved.strategy_agent_provider != "openai_web":
        raise ValueError("Unsupported Strategy Agent provider configuration")
    graph = build_graph(
        model=resolved.openai_model,
        api_key=resolved.openai_api_key or "missing-api-key",
        client_factory=client_factory,
    )
    return IntegratedStrategyAgentService(
        graph,
        enabled=resolved.strategy_agent_enabled,
        model=resolved.openai_model,
        api_key_configured=bool(resolved.openai_api_key or client_factory),
    )
