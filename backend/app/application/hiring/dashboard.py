from datetime import date, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.hiring.analytics import (
    CapabilityHiringConcentration,
    GeographicHiringConcentration,
    HiringAnalyticsService,
    HiringSnapshot,
    HiringTrendGranularity,
    HiringTrendSummary,
    SeniorityHiringSummary,
)
from backend.app.application.hiring.enrichment import HiringEnrichmentResult
from backend.app.application.hiring.observability import CollectionRun
from backend.app.application.hiring.signal_generation import (
    HiringSignalGenerationResult,
    HiringSignalService,
)
from backend.app.domain.hiring import JobPosting


class HiringDashboardQuery(Protocol):
    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]: ...

    def list_enrichments(
        self,
        organization: str,
    ) -> list[HiringEnrichmentResult]: ...

    def list_runs(
        self,
        *,
        organization: str | None,
        limit: int,
    ) -> list[CollectionRun]: ...


class HiringAnalyticsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: HiringSnapshot
    geographic: GeographicHiringConcentration
    capability: CapabilityHiringConcentration
    seniority: SeniorityHiringSummary
    daily_trend: HiringTrendSummary
    weekly_trend: HiringTrendSummary


class HiringOrganizationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    total_observed_jobs: int = Field(ge=0)
    jobs_with_evidence: int = Field(ge=0)
    evidence_coverage: float = Field(ge=0, le=100)
    observation_start: date | None = None
    observation_end: date | None = None
    latest_collection_run: CollectionRun | None = None
    enriched_job_count: int = Field(ge=0)
    enrichment_coverage: float = Field(ge=0, le=100)
    signal_count: int = Field(ge=0)
    generated_at: datetime
    geographic: GeographicHiringConcentration
    capability: CapabilityHiringConcentration
    seniority: SeniorityHiringSummary
    trend: HiringTrendSummary


class HiringDashboardService:
    def __init__(self, query: HiringDashboardQuery) -> None:
        self._query = query
        self._analytics = HiringAnalyticsService(query)
        self._signals = HiringSignalService(self._analytics)

    def analytics(self, organization: str) -> HiringAnalyticsResult:
        return HiringAnalyticsResult(
            snapshot=self._analytics.snapshot(organization),
            geographic=self._analytics.geographic_concentration(organization),
            capability=self._analytics.capability_concentration(organization),
            seniority=self._analytics.seniority_summary(organization),
            daily_trend=self._analytics.trend_summary(
                organization,
                HiringTrendGranularity.DAILY,
            ),
            weekly_trend=self._analytics.trend_summary(
                organization,
                HiringTrendGranularity.WEEKLY,
            ),
        )

    def signals(self, organization: str) -> HiringSignalGenerationResult:
        return self._signals.generate(organization)

    def summary(self, organization: str) -> HiringOrganizationSummary:
        analytics = self.analytics(organization)
        signals = self.signals(organization)
        enrichments = self._query.list_enrichments(organization)
        enriched_job_ids = {enrichment.job_id for enrichment in enrichments}
        latest_runs = self._query.list_runs(organization=organization, limit=1)
        total_jobs = analytics.snapshot.total_active_jobs
        jobs_with_evidence = len(
            {reference.job_id for reference in analytics.snapshot.contributing_records}
        )
        return HiringOrganizationSummary(
            organization=organization,
            total_observed_jobs=total_jobs,
            jobs_with_evidence=jobs_with_evidence,
            evidence_coverage=self._percentage(jobs_with_evidence, total_jobs),
            observation_start=analytics.snapshot.observation_start,
            observation_end=analytics.snapshot.observation_end,
            latest_collection_run=latest_runs[0] if latest_runs else None,
            enriched_job_count=len(enriched_job_ids),
            enrichment_coverage=self._percentage(len(enriched_job_ids), total_jobs),
            signal_count=len(signals.signals),
            generated_at=analytics.snapshot.generated_at,
            geographic=analytics.geographic,
            capability=analytics.capability,
            seniority=analytics.seniority,
            trend=analytics.weekly_trend,
        )

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        if denominator == 0:
            return 0.0
        return round(numerator / denominator * 100, 2)
