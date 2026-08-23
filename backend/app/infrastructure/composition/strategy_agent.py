from collections.abc import Callable
from typing import Any

from backend.app.application.agents.strategy_agent import StrategyAgentService
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.agent_tools import create_agent_intelligence_tools
from backend.app.infrastructure.llm.vertex.strategy_agent import VertexGeminiStrategyAgentProvider


def create_strategy_agent_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> StrategyAgentService:
    resolved = settings or HiringSettings()
    if resolved.strategy_agent_provider != "vertex_gemini":
        raise ValueError("Unsupported Strategy Agent provider configuration")
    tools = create_agent_intelligence_tools(resolved)
    provider = VertexGeminiStrategyAgentProvider(
        project=resolved.gcp_project,
        location=resolved.gcp_location,
        model=resolved.strategy_agent_model,
        temperature=resolved.gemini_temperature,
        max_output_tokens=resolved.gemini_max_output_tokens,
        client_factory=client_factory,
    )
    return StrategyAgentService(
        tools,
        provider,
        enabled=resolved.strategy_agent_enabled,
        max_tool_calls=resolved.strategy_agent_max_tool_calls,
        max_search_results=resolved.strategy_agent_max_search_results,
        max_evidence_records=resolved.strategy_agent_max_evidence,
        max_payload_chars=resolved.strategy_agent_max_payload_chars,
    )
