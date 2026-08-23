from backend.app.application.hiring.kg import GraphInsightsService
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_kg import create_hiring_knowledge_graph_service


def create_graph_insights_service(settings: HiringSettings | None = None) -> GraphInsightsService:
    settings = settings or HiringSettings()
    return GraphInsightsService(create_hiring_knowledge_graph_service(settings))
