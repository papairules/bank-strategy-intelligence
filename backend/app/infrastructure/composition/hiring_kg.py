from backend.app.application.hiring import HiringAnalyticsService, HiringSignalService
from backend.app.application.hiring.kg import HiringKnowledgeGraphService
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_read import create_hiring_read_service
from backend.app.infrastructure.persistence.hiring import (
    SQLiteDatabase,
    SQLiteStrategyResearchCacheRepository,
)


def create_hiring_knowledge_graph_service(
    settings: HiringSettings | None = None,
) -> HiringKnowledgeGraphService:
    settings = settings or HiringSettings()
    read_service = create_hiring_read_service(settings)
    database = SQLiteDatabase(settings.sqlite_database_path)
    database.initialize()
    return HiringKnowledgeGraphService(
        read_service,
        HiringSignalService(HiringAnalyticsService(read_service)),
        graph_directory=settings.hiring_kg_graph_directory,
        strategy_research=SQLiteStrategyResearchCacheRepository(database),
    )
