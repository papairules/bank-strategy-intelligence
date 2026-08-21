from collections.abc import Callable
from typing import Any

from backend.app.application.hiring import HiringEnrichmentService
from backend.app.config import HiringSettings
from backend.app.infrastructure.llm.vertex import (
    VertexGeminiHiringEnrichmentProvider,
)


def create_hiring_enrichment_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> HiringEnrichmentService:
    resolved_settings = settings or HiringSettings()
    if resolved_settings.hiring_llm_provider != "vertex_gemini":
        raise ValueError("Unsupported hiring LLM provider configuration")
    provider = VertexGeminiHiringEnrichmentProvider(
        project=resolved_settings.gcp_project,
        location=resolved_settings.gcp_location,
        model=resolved_settings.gemini_model,
        temperature=resolved_settings.gemini_temperature,
        max_output_tokens=resolved_settings.gemini_max_output_tokens,
        client_factory=client_factory,
    )
    return HiringEnrichmentService(
        provider,
        enabled=resolved_settings.hiring_enrichment_enabled,
    )
