from pydantic import BaseModel, ConfigDict, Field

from .builder import HiringKnowledgeGraphService, concept_node_id
from .models import HiringKGNodeType
from .queries import (
    get_capabilities_for_organization,
    get_evidence_for_strategic_theme,
    get_jobs_for_capability,
    get_jobs_for_location,
    get_jobs_for_technology,
    get_locations_for_organization,
    get_strategic_themes_for_organization,
    get_technologies_for_organization,
)
from .builder import summarize_hiring_knowledge_graph


class GraphInsightConcept(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    job_count: int = Field(ge=0)


class GraphInsightStrategicTheme(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    direction: str
    confidence: float = Field(ge=0, le=1)
    time_horizon: str | None = None
    business_unit: str | None = None
    evidence_count: int = Field(ge=0)


class GraphInsightsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    jobs_read: int = Field(ge=0)
    classified_jobs_used: int = Field(ge=0)
    enriched_jobs_used: int = Field(ge=0)
    hiring_signals_used: int = Field(ge=0)
    strategic_themes_used: int = Field(ge=0)
    top_capabilities: list[GraphInsightConcept]
    top_technologies: list[GraphInsightConcept]
    top_locations: list[GraphInsightConcept]
    strategic_themes: list[GraphInsightStrategicTheme]


class GraphInsightsService:
    """Read-only, cheap view over the persisted knowledge graph: reuses the
    disk-cached graph (via `load_or_build_for_organization`) rather than
    forcing a full rebuild on every page view."""

    def __init__(self, kg_service: HiringKnowledgeGraphService, *, top_n: int = 10) -> None:
        self._kg = kg_service
        self._top_n = top_n

    def get_insights(self, organization: str) -> GraphInsightsSnapshot:
        graph = self._kg.load_or_build_for_organization(organization)
        summary = summarize_hiring_knowledge_graph(graph)
        capabilities = self._ranked_concepts(
            get_capabilities_for_organization(graph), lambda name: get_jobs_for_capability(graph, name)
        )
        technologies = self._ranked_concepts(
            get_technologies_for_organization(graph), lambda name: get_jobs_for_technology(graph, name)
        )
        locations = self._ranked_concepts(
            get_locations_for_organization(graph), lambda name: get_jobs_for_location(graph, name)
        )
        return GraphInsightsSnapshot(
            organization=organization,
            node_count=graph.number_of_nodes(),
            edge_count=graph.number_of_edges(),
            jobs_read=summary.jobs_read,
            classified_jobs_used=summary.classified_jobs_used,
            enriched_jobs_used=summary.enriched_jobs_used,
            hiring_signals_used=summary.hiring_signals_used,
            strategic_themes_used=summary.strategic_themes_used,
            top_capabilities=capabilities[: self._top_n],
            top_technologies=technologies[: self._top_n],
            top_locations=locations[: self._top_n],
            strategic_themes=self._strategic_themes(graph, organization),
        )

    @staticmethod
    def _ranked_concepts(names: list[str], job_query) -> list[GraphInsightConcept]:
        items = [GraphInsightConcept(name=name, job_count=len(job_query(name))) for name in names]
        return sorted(items, key=lambda item: (-item.job_count, item.name.casefold()))

    @staticmethod
    def _strategic_themes(graph, organization: str) -> list[GraphInsightStrategicTheme]:
        results = []
        for name in get_strategic_themes_for_organization(graph):
            node_id = concept_node_id(HiringKGNodeType.STRATEGIC_THEME, organization, name)
            attributes = graph.nodes[node_id]
            results.append(
                GraphInsightStrategicTheme(
                    name=name,
                    direction=attributes["direction"],
                    confidence=attributes["confidence"],
                    time_horizon=attributes.get("time_horizon"),
                    business_unit=attributes.get("business_unit"),
                    evidence_count=len(get_evidence_for_strategic_theme(graph, name)),
                )
            )
        return sorted(results, key=lambda item: -item.confidence)
