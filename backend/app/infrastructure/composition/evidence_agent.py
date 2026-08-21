from collections.abc import Callable
from typing import Any

from backend.app.application.agents.evidence_agent import EvidenceAgentService
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.agent_tools import (
    create_agent_intelligence_tools,
)
from backend.app.infrastructure.llm.vertex.evidence_agent import (
    VertexGeminiEvidenceAgentProvider,
)


def create_evidence_agent_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> EvidenceAgentService:
    resolved = settings or HiringSettings()
    if resolved.evidence_agent_provider != "vertex_gemini":
        raise ValueError("Unsupported Evidence Agent provider configuration")
    tools = create_agent_intelligence_tools(resolved)
    provider = VertexGeminiEvidenceAgentProvider(
        project=resolved.gcp_project,
        location=resolved.gcp_location,
        model=resolved.evidence_agent_model,
        temperature=resolved.gemini_temperature,
        max_output_tokens=resolved.gemini_max_output_tokens,
        client_factory=client_factory,
    )
    return EvidenceAgentService(
        tools.evidence,
        provider,
        enabled=resolved.evidence_agent_enabled,
        max_tool_calls=resolved.evidence_agent_max_tool_calls,
        max_evidence_records=resolved.evidence_agent_max_evidence,
        registry=tools.registry,
    )
