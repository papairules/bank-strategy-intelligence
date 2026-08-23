from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_graph_insights_service
from backend.app.application.hiring.kg import GraphInsightsService, GraphInsightsSnapshot

router = APIRouter(prefix="/graph-insights", tags=["Graph Insights"])
GraphInsights = Annotated[GraphInsightsService, Depends(get_graph_insights_service)]


@router.get("/organizations/{organization}", response_model=GraphInsightsSnapshot)
def get_graph_insights(organization: str, service: GraphInsights) -> GraphInsightsSnapshot:
    return service.get_insights(organization)
