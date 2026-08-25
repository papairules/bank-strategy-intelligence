from collections.abc import Callable
from datetime import timedelta

from openai import OpenAI

from backend.app.application.agents.supervisor_agent import (
    CachedSupervisorReportService,
    SupervisorAppService,
    SupervisorReportBoundary,
    SupervisorRequest,
    SupervisorResponse,
    run_supervisor,
)
from backend.app.application.hiring import HiringAnalyticsService, HiringSignalService
from backend.app.application.hiring.kg import HiringKnowledgeGraphService
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_read import create_hiring_read_service
from backend.app.infrastructure.composition.strategy_agent import create_strategy_agent_service
from backend.app.infrastructure.persistence.hiring import (
    SQLiteDatabase,
    SQLiteStrategyResearchCacheRepository,
    SQLiteSupervisorReportCacheRepository,
)


def create_supervisor_app_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[[], OpenAI] | None = None,
) -> SupervisorReportBoundary:
    resolved = settings or HiringSettings()
    read_service = create_hiring_read_service(resolved)
    hiring_signals = HiringSignalService(HiringAnalyticsService(read_service))
    database = SQLiteDatabase(resolved.sqlite_database_path)
    database.initialize()
    hiring_kg = HiringKnowledgeGraphService(
        read_service,
        hiring_signals,
        graph_directory=resolved.hiring_kg_graph_directory,
        strategy_research=SQLiteStrategyResearchCacheRepository(database),
    )

    def supervisor_runner(request: SupervisorRequest) -> SupervisorResponse:
        client = client_factory() if client_factory else OpenAI(
            api_key=resolved.openai_api_key or "missing-api-key"
        )
        return run_supervisor(request, client=client, model=resolved.openai_model)

    inner = SupervisorAppService(
        strategy_service=create_strategy_agent_service(
            resolved, client_factory=client_factory
        ),
        hiring_signals=hiring_signals,
        hiring_read=read_service,
        hiring_kg=hiring_kg,
        supervisor_runner=supervisor_runner,
        enabled=resolved.supervisor_agent_enabled,
        provider="openai",
        model=resolved.openai_model,
    )
    if resolved.supervisor_report_cache_ttl_hours <= 0:
        return inner
    return CachedSupervisorReportService(
        inner,
        SQLiteSupervisorReportCacheRepository(database),
        provider="openai",
        model=resolved.openai_model,
        ttl=timedelta(hours=resolved.supervisor_report_cache_ttl_hours),
    )
