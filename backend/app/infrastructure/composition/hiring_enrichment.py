from collections.abc import Callable
from typing import Any

from backend.app.application.hiring import (
    BatchEnrichmentIdentity,
    HiringEnrichmentProvider,
    HiringEnrichmentService,
)
from backend.app.config import HiringSettings
from backend.app.infrastructure.llm.vertex import (
    VertexGeminiHiringEnrichmentProvider,
)
from backend.app.infrastructure.llm.openai import OpenAIHiringEnrichmentProvider


def create_hiring_enrichment_provider(
    settings: HiringSettings,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> HiringEnrichmentProvider:
    if settings.hiring_llm_provider == "vertex_gemini":
        return VertexGeminiHiringEnrichmentProvider(
            project=settings.gcp_project,
            location=settings.gcp_location,
            model=settings.gemini_model,
            temperature=settings.gemini_temperature,
            max_output_tokens=settings.gemini_max_output_tokens,
            client_factory=client_factory,
        )
    if settings.hiring_llm_provider == "openai":
        return OpenAIHiringEnrichmentProvider(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model,
            client_factory=client_factory,
        )
    raise ValueError("Unsupported hiring LLM provider configuration")


def hiring_enrichment_identity(settings: HiringSettings) -> BatchEnrichmentIdentity:
    if settings.hiring_llm_provider == "vertex_gemini":
        return BatchEnrichmentIdentity(
            provider=VertexGeminiHiringEnrichmentProvider.provider_name,
            model=settings.gemini_model,
            prompt_schema_version=VertexGeminiHiringEnrichmentProvider.prompt_schema_version,
        )
    if settings.hiring_llm_provider == "openai":
        return BatchEnrichmentIdentity(
            provider=OpenAIHiringEnrichmentProvider.provider_name,
            model=settings.openai_model,
            prompt_schema_version=OpenAIHiringEnrichmentProvider.prompt_schema_version,
        )
    raise ValueError("Unsupported hiring LLM provider configuration")


def create_hiring_enrichment_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> HiringEnrichmentService:
    resolved_settings = settings or HiringSettings()
    provider = create_hiring_enrichment_provider(
        resolved_settings,
        client_factory=client_factory,
    )
    return HiringEnrichmentService(
        provider,
        enabled=resolved_settings.hiring_enrichment_enabled,
    )
