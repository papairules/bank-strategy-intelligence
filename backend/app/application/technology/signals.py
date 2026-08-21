from datetime import date, datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.technology.models import (
    TechnologyAnalyticsResult,
    TechnologyRecordReference,
)
from backend.app.application.technology.service import TechnologyAnalyticsService


class TechnologySignalType(StrEnum):
    TECHNOLOGY_CONCENTRATION = "technology_concentration"
    TECHNOLOGY_CATEGORY_CONCENTRATION = "technology_category_concentration"
    BUSINESS_UNIT_TECHNOLOGY_CONCENTRATION = "business_unit_technology_concentration"
    GEOGRAPHIC_TECHNOLOGY_CONCENTRATION = "geographic_technology_concentration"
    TECHNOLOGY_HIRING_CLUSTER = "technology_hiring_cluster"


class TechnologySignalThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_enriched_jobs: int = Field(default=5, ge=1)
    minimum_enrichment_coverage: float = Field(default=0.25, ge=0, le=1)
    minimum_observations: int = Field(default=5, ge=1)
    minimum_contributing_jobs: int = Field(default=3, ge=1)
    technology_minimum_concentration: float = Field(default=0.4, ge=0, le=1)
    category_minimum_concentration: float = Field(default=0.4, ge=0, le=1)
    category_minimum_unique_technologies: int = Field(default=2, ge=1)
    context_minimum_concentration: float = Field(default=0.4, ge=0, le=1)
    cluster_minimum_unique_technologies: int = Field(default=3, ge=2)
    cluster_minimum_observations: int = Field(default=5, ge=2)
    limited_observation_window_days: int = Field(default=28, ge=1)
    small_enriched_sample: int = Field(default=10, ge=1)
    single_hiring_source: bool = True
    configuration_version: str = "technology-signals-v1"


class TechnologySignalScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    confidence: float = Field(ge=0, le=1)
    strength: float = Field(ge=0, le=1)
    evidence_coverage: float = Field(ge=0, le=1)


class TechnologySignalProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generator: str = "TechnologySignalService"
    configuration_version: str
    deterministic: bool = True


class TechnologySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: UUID
    organization: str
    signal_type: TechnologySignalType
    title: str
    summary: str
    subject: str
    observation_start: date
    observation_end: date
    confidence: float = Field(ge=0, le=1)
    strength: float = Field(ge=0, le=1)
    evidence_coverage: float = Field(ge=0, le=1)
    supporting_job_ids: list[UUID]
    supporting_evidence_ids: list[UUID]
    limitations: list[str]
    provenance: TechnologySignalProvenance


class TechnologySignalGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    generated_at: datetime
    total_jobs: int = Field(ge=0)
    enriched_jobs: int = Field(ge=0)
    enrichment_coverage: float = Field(ge=0, le=1)
    technology_observation_count: int = Field(ge=0)
    signals: list[TechnologySignal] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class TechnologySignalService:
    def __init__(
        self,
        analytics: TechnologyAnalyticsService,
        thresholds: TechnologySignalThresholds | None = None,
    ) -> None:
        self._analytics = analytics
        self._thresholds = thresholds or TechnologySignalThresholds()

    def generate(self, organization: str) -> TechnologySignalGenerationResult:
        analytics = self._analytics.analytics(organization)
        snapshot = analytics.snapshot
        coverage = self._ratio(snapshot.enriched_jobs, snapshot.total_jobs)
        limitations = self._result_limitations(analytics, coverage)
        if not self._sufficient_foundation(analytics, coverage):
            return TechnologySignalGenerationResult(
                organization=organization,
                generated_at=snapshot.generated_at,
                total_jobs=snapshot.total_jobs,
                enriched_jobs=snapshot.enriched_jobs,
                enrichment_coverage=coverage,
                technology_observation_count=snapshot.technology_observation_count,
                limitations=limitations,
            )

        signals = [
            *self._technology_signals(analytics, coverage),
            *self._category_signals(analytics, coverage),
            *self._context_signals(analytics, coverage, "business_unit"),
            *self._context_signals(analytics, coverage, "geography"),
            *self._cluster_signals(analytics, coverage),
        ]
        signals.sort(key=lambda item: (item.signal_type.value, item.subject, str(item.signal_id)))
        return TechnologySignalGenerationResult(
            organization=organization,
            generated_at=snapshot.generated_at,
            total_jobs=snapshot.total_jobs,
            enriched_jobs=snapshot.enriched_jobs,
            enrichment_coverage=coverage,
            technology_observation_count=snapshot.technology_observation_count,
            signals=signals,
            limitations=limitations,
        )

    def _sufficient_foundation(self, analytics: TechnologyAnalyticsResult, coverage: float) -> bool:
        snapshot = analytics.snapshot
        thresholds = self._thresholds
        return (
            snapshot.enriched_jobs >= thresholds.minimum_enriched_jobs
            and coverage >= thresholds.minimum_enrichment_coverage
            and snapshot.technology_observation_count >= thresholds.minimum_observations
            and snapshot.observation_start is not None
            and snapshot.observation_end is not None
        )

    def _technology_signals(self, analytics: TechnologyAnalyticsResult, coverage: float) -> list[TechnologySignal]:
        results = []
        for group in analytics.top_technologies:
            concentration = self._unit(group.percentage_of_enriched_jobs / 100)
            if group.job_count < self._thresholds.minimum_contributing_jobs or concentration < self._thresholds.technology_minimum_concentration:
                continue
            results.append(self._signal(
                analytics,
                coverage,
                TechnologySignalType.TECHNOLOGY_CONCENTRATION,
                group.technology,
                f"Observed hiring concentration for {group.technology}",
                f"Within the currently enriched hiring sample, {group.technology} appears in {group.job_count} enriched job records ({group.percentage_of_enriched_jobs:g}% of enriched jobs). This is an observed hiring concentration, not evidence of enterprise adoption.",
                concentration,
                group.contributing_records,
            ))
        return results

    def _category_signals(self, analytics: TechnologyAnalyticsResult, coverage: float) -> list[TechnologySignal]:
        results = []
        total = analytics.snapshot.technology_observation_count
        for group in analytics.categories:
            concentration = self._ratio(group.observation_count, total)
            if (
                group.job_count < self._thresholds.minimum_contributing_jobs
                or group.unique_technology_count < self._thresholds.category_minimum_unique_technologies
                or concentration < self._thresholds.category_minimum_concentration
            ):
                continue
            results.append(self._signal(
                analytics,
                coverage,
                TechnologySignalType.TECHNOLOGY_CATEGORY_CONCENTRATION,
                group.category.value,
                f"Observed {group.category.value} hiring concentration",
                f"Within the currently enriched hiring sample, {group.category.value} accounts for {group.observation_count} of {total} technology observations across {group.job_count} jobs. Concentration in hiring evidence does not establish organization-wide technology strategy.",
                concentration,
                group.contributing_records,
            ))
        return results

    def _context_signals(self, analytics: TechnologyAnalyticsResult, coverage: float, context: str) -> list[TechnologySignal]:
        groups = analytics.business_unit_technologies if context == "business_unit" else analytics.geography_technologies
        signal_type = TechnologySignalType.BUSINESS_UNIT_TECHNOLOGY_CONCENTRATION if context == "business_unit" else TechnologySignalType.GEOGRAPHIC_TECHNOLOGY_CONCENTRATION
        results = []
        for group in groups:
            concentration = self._ratio(group.job_count, analytics.snapshot.enriched_jobs)
            if group.job_count < self._thresholds.minimum_contributing_jobs or concentration < self._thresholds.context_minimum_concentration:
                continue
            label = group.business_unit if context == "business_unit" else group.location
            results.append(self._signal(
                analytics,
                coverage,
                signal_type,
                f"{label}:{group.technology}",
                f"Observed {group.technology} hiring cluster in {label}",
                f"Within the currently enriched hiring sample, {group.technology} appears in {group.job_count} job records associated with {label}. This describes observed hiring evidence and does not prove production deployment.",
                concentration,
                group.contributing_records,
            ))
        return results

    def _cluster_signals(self, analytics: TechnologyAnalyticsResult, coverage: float) -> list[TechnologySignal]:
        results = []
        for group in analytics.categories:
            if (
                group.job_count < self._thresholds.minimum_contributing_jobs
                or group.unique_technology_count < self._thresholds.cluster_minimum_unique_technologies
                or group.observation_count < self._thresholds.cluster_minimum_observations
            ):
                continue
            strength = self._unit(group.unique_technology_count / (self._thresholds.cluster_minimum_unique_technologies * 2))
            results.append(self._signal(
                analytics,
                coverage,
                TechnologySignalType.TECHNOLOGY_HIRING_CLUSTER,
                group.category.value,
                f"Observed technology hiring cluster in {group.category.value}",
                f"The currently enriched hiring evidence contains {group.unique_technology_count} distinct {group.category.value} technologies across {group.job_count} jobs. This is a hiring cluster observation, not an enterprise technology strategy claim.",
                strength,
                group.contributing_records,
            ))
        return results

    def _signal(self, analytics, coverage, signal_type, subject, title, summary, strength, references):
        references = self._deduplicate_references(references)
        evidence_coverage = self._ratio(len({item.evidence_id for item in references}), len({item.job_id for item in references}))
        sample_sufficiency = self._unit(len({item.job_id for item in references}) / (self._thresholds.minimum_contributing_jobs * 2))
        score = TechnologySignalScore(
            strength=self._unit(strength),
            evidence_coverage=evidence_coverage,
            confidence=self._unit((coverage + evidence_coverage + sample_sufficiency) / 3),
        )
        snapshot = analytics.snapshot
        identity = f"{snapshot.organization}|{signal_type.value}|{subject}|{snapshot.observation_start}|{snapshot.observation_end}|{self._thresholds.configuration_version}"
        return TechnologySignal(
            signal_id=uuid5(NAMESPACE_URL, identity),
            organization=snapshot.organization,
            signal_type=signal_type,
            title=title,
            summary=summary,
            subject=subject,
            observation_start=snapshot.observation_start,
            observation_end=snapshot.observation_end,
            confidence=score.confidence,
            strength=score.strength,
            evidence_coverage=score.evidence_coverage,
            supporting_job_ids=sorted({item.job_id for item in references}, key=str),
            supporting_evidence_ids=sorted({item.evidence_id for item in references}, key=str),
            limitations=self._signal_limitations(analytics, coverage),
            provenance=TechnologySignalProvenance(configuration_version=self._thresholds.configuration_version),
        )

    def _result_limitations(self, analytics: TechnologyAnalyticsResult, coverage: float) -> list[str]:
        limitations = []
        snapshot = analytics.snapshot
        if coverage < self._thresholds.minimum_enrichment_coverage:
            limitations.append("Enrichment coverage is below the configured minimum for reliable technology signal generation.")
        if snapshot.enriched_jobs < self._thresholds.minimum_enriched_jobs:
            limitations.append("The enriched hiring sample is smaller than the configured minimum.")
        if snapshot.technology_observation_count < self._thresholds.minimum_observations:
            limitations.append("Too few technology observations are available for signal generation.")
        limitations.extend(self._signal_limitations(analytics, coverage))
        return list(dict.fromkeys(limitations))

    def _signal_limitations(self, analytics: TechnologyAnalyticsResult, coverage: float) -> list[str]:
        snapshot = analytics.snapshot
        limitations = []
        if coverage < 1:
            limitations.append("Technology classifications cover only a subset of observed hiring records.")
        if snapshot.enriched_jobs < self._thresholds.small_enriched_sample:
            limitations.append("The enriched hiring sample is small.")
        if snapshot.observation_start and snapshot.observation_end and (snapshot.observation_end - snapshot.observation_start).days < self._thresholds.limited_observation_window_days:
            limitations.append("The observation period is limited.")
        if self._thresholds.single_hiring_source:
            limitations.append("Observations derive from a single public hiring source.")
        limitations.extend([
            "Technology classifications are derived from hiring evidence and do not prove production deployment.",
            "Concentration does not imply enterprise technology adoption.",
            "Absence from observed hiring does not prove absence from the organization.",
        ])
        return limitations

    @staticmethod
    def _deduplicate_references(references: list[TechnologyRecordReference]) -> list[TechnologyRecordReference]:
        return sorted(set(references), key=lambda item: (str(item.job_id), str(item.evidence_id)))

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 0.0

    @staticmethod
    def _unit(value: float) -> float:
        return max(0.0, min(1.0, value))
