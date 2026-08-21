from typing import Protocol

from backend.app.application.agents.models import (
    AgentTechnologyAnalytics,
    AgentTechnologyObservationSearchResult,
    AgentTechnologySummary,
    OrganizationInput,
    TechnologyObservationSearchInput,
)
from backend.app.application.technology import (
    TechnologyAnalyticsResult,
    TechnologySignalGenerationResult,
)


class TechnologyAnalyticsBoundary(Protocol):
    def analytics(self, organization: str) -> TechnologyAnalyticsResult: ...
    def observations(self, organization: str): ...


class TechnologySignalBoundary(Protocol):
    def generate(self, organization: str) -> TechnologySignalGenerationResult: ...


class TechnologyAgentTools:
    def __init__(self, analytics: TechnologyAnalyticsBoundary, signals: TechnologySignalBoundary) -> None:
        self._analytics = analytics
        self._signals = signals

    def get_summary(self, request: OrganizationInput) -> AgentTechnologySummary:
        snapshot = self._analytics.analytics(request.organization).snapshot
        coverage = snapshot.enriched_jobs / snapshot.total_jobs if snapshot.total_jobs else 0.0
        limitations = []
        if coverage < 1:
            limitations.append("Technology classifications cover only a subset of observed hiring records.")
        if snapshot.enriched_jobs == 0:
            limitations.append("No persisted enrichment is available for technology observation extraction.")
        return AgentTechnologySummary(
            organization=request.organization,
            total_jobs=snapshot.total_jobs,
            enriched_jobs=snapshot.enriched_jobs,
            technology_observation_count=snapshot.technology_observation_count,
            unique_technologies=snapshot.unique_technologies,
            technology_coverage=coverage,
            observation_start=snapshot.observation_start,
            observation_end=snapshot.observation_end,
            limitations=limitations,
        )

    def get_analytics(self, request: OrganizationInput) -> AgentTechnologyAnalytics:
        analytics = self._analytics.analytics(request.organization)
        limitations = self.get_summary(request).limitations
        return AgentTechnologyAnalytics(analytics=analytics, limitations=limitations)

    def search_observations(self, request: TechnologyObservationSearchInput) -> AgentTechnologyObservationSearchResult:
        items = self._analytics.observations(request.organization)
        if request.technology:
            needle = request.technology.casefold()
            items = [item for item in items if needle in item.normalized_technology.casefold()]
        if request.category:
            items = [item for item in items if item.category == request.category]
        if request.business_unit:
            needle = request.business_unit.casefold()
            items = [item for item in items if item.business_unit and needle in item.business_unit.casefold()]
        if request.location:
            needle = request.location.casefold()
            items = [item for item in items if needle in item.location.casefold()]
        items = sorted(items, key=lambda item: (item.normalized_technology.casefold(), item.observation_date, str(item.job_id)))
        total = len(items)
        return AgentTechnologyObservationSearchResult(
            organization=request.organization,
            items=items[request.offset : request.offset + request.limit],
            total=total,
            limit=request.limit,
            offset=request.offset,
        )

    def get_signals(self, request: OrganizationInput) -> TechnologySignalGenerationResult:
        return self._signals.generate(request.organization)
