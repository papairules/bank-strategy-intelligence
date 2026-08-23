from collections.abc import Callable
from datetime import timedelta

from openai import OpenAI

from backend.app.application.agents.strategy_agent import (
    CachedStrategyAgentService,
    IntegratedStrategyAgentService,
)
from backend.app.application.agents.strategy_agent.cache import StrategyAgentBoundary
from backend.app.application.agents.strategy_agent.graph import build_graph
from backend.app.config import HiringSettings
from backend.app.infrastructure.persistence.hiring import (
    SQLiteDatabase,
    SQLiteStrategyResearchCacheRepository,
)


def create_strategy_agent_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[[], OpenAI] | None = None,
) -> StrategyAgentBoundary:
    resolved = settings or HiringSettings()
    if resolved.strategy_agent_provider != "openai_web":
        raise ValueError("Unsupported Strategy Agent provider configuration")
    graph = build_graph(
        model=resolved.openai_model,
        api_key=resolved.openai_api_key or "missing-api-key",
        client_factory=client_factory,
    )
    inner = IntegratedStrategyAgentService(
        graph,
        enabled=resolved.strategy_agent_enabled,
        model=resolved.openai_model,
        api_key_configured=bool(resolved.openai_api_key or client_factory),
    )
    if resolved.strategy_agent_cache_ttl_hours <= 0:
        return inner
    database = SQLiteDatabase(resolved.sqlite_database_path)
    database.initialize()
    return CachedStrategyAgentService(
        inner,
        SQLiteStrategyResearchCacheRepository(database),
        provider="openai",
        model=resolved.openai_model,
        agent_version=IntegratedStrategyAgentService.AGENT_VERSION,
        ttl=timedelta(hours=resolved.strategy_agent_cache_ttl_hours),
    )
