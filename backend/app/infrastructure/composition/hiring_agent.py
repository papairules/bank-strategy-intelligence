from collections.abc import Callable
from typing import Any

from openai import OpenAI

from backend.app.application.agents.hiring_agent import HiringAgentAppService
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_read import create_hiring_read_service


def create_hiring_agent_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[[], Any] | None = None,
) -> HiringAgentAppService:
    resolved = settings or HiringSettings()
    read_service = create_hiring_read_service(resolved)
    api_key = resolved.openai_api_key
    if client_factory is not None:
        factory = client_factory
    elif api_key:
        factory = lambda: OpenAI(api_key=api_key)
    else:
        factory = None
    return HiringAgentAppService(
        job_source=read_service.list_jobs_for_analytics,
        enabled=resolved.hiring_agent_enabled,
        model=resolved.openai_model,
        api_key_configured=bool(api_key or client_factory),
        use_llm=resolved.hiring_agent_use_llm,
        max_jobs=resolved.hiring_agent_max_jobs,
        workers=resolved.hiring_agent_workers,
        client_factory=factory,
    )
