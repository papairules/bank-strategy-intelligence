from backend.app.application.hiring import HiringAnalyticsService, HiringSignalService
from backend.app.application.hiring.kg import HiringKnowledgeGraphService
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_read import create_hiring_read_service


def create_hiring_knowledge_graph_service(
    settings: HiringSettings | None = None,
) -> HiringKnowledgeGraphService:
    read_service = create_hiring_read_service(settings)
    return HiringKnowledgeGraphService(
        read_service,
        HiringSignalService(HiringAnalyticsService(read_service)),
    )
