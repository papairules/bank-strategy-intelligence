from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.hiring.analytics import (
    CapabilityHiringConcentration,
    GeographicHiringConcentration,
    HiringAnalyticsService,
    HiringRecordReference,
    HiringSnapshot,
    HiringTrendGranularity,
    HiringTrendSummary,
    SeniorityHiringSummary,
)
from backend.app.domain.intelligence import (
    IntelligenceCapability,
    IntelligenceSignal,
    ObservationPeriod,
)


class HiringSignalType(StrEnum):
    GEOGRAPHIC_HIRING_CONCENTRATION = "geographic_hiring_concentration"
    CAPABILITY_HIRING_CONCENTRATION = "capability_hiring_concentration"
    LEADERSHIP_HIRING = "leadership_hiring"
    HIRING_VOLUME = "hiring_volume"
    HIRING_TREND = "hiring_trend"


class HiringSignalThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    geographic_minimum_total_jobs: int = Field(default=5, ge=1)
    geographic_minimum_job_count: int = Field(default=2, ge=1)
    geographic_minimum_percentage: float = Field(default=30.0, ge=0, le=100)
    capability_minimum_classified_jobs: int = Field(default=3, ge=1)
    capability_minimum_classification_coverage: float = Field(
        default=0.5, ge=0, le=1
    )
    capability_minimum_job_count: int = Field(default=2, ge=1)
    capability_minimum_percentage: float = Field(default=30.0, ge=0, le=100)
    leadership_minimum_total_jobs: int = Field(default=5, ge=1)
    leadership_minimum_seniority_coverage: float = Field(default=0.5, ge=0, le=1)
    leadership_minimum_job_count: int = Field(default=2, ge=1)
    hiring_volume_minimum_jobs: int = Field(default=5, ge=1)
    trend_minimum_buckets: int = Field(default=4, ge=2)
    trend_minimum_observation_days: int = Field(default=21, ge=1)
    trend_minimum_directional_change: float = Field(default=0.25, gt=0)
    limited_observation_window_days: int = Field(default=28, ge=1)
    small_sample_job_count: int = Field(default=20, ge=1)
    single_source_data: bool = True


class HiringSignalScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strength: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    evidence_coverage: float = Field(ge=0, le=1)


class GeneratedHiringSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    signal: IntelligenceSignal
    score: HiringSignalScore


class HiringSignalGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    generated_at: datetime
    signals: list[GeneratedHiringSignal] = Field(default_factory=list)


class HiringSignalService:
    def __init__(
        self,
        analytics: HiringAnalyticsService,
        thresholds: HiringSignalThresholds | None = None,
    ) -> None:
        self._analytics = analytics
        self._thresholds = thresholds or HiringSignalThresholds()

    def generate(self, organization: str) -> HiringSignalGenerationResult:
        snapshot = self._analytics.snapshot(organization)
        if (
            snapshot.total_active_jobs == 0
            or snapshot.observation_start is None
            or snapshot.observation_end is None
        ):
            return HiringSignalGenerationResult(
                organization=organization,
                generated_at=snapshot.generated_at,
            )

        geography = self._analytics.geographic_concentration(organization)
        capability = self._analytics.capability_concentration(organization)
        seniority = self._analytics.seniority_summary(organization)
        trend = self._analytics.trend_summary(
            organization,
            HiringTrendGranularity.WEEKLY,
        )
        signals = [
            *self._geographic_signals(snapshot, geography),
            *self._capability_signals(snapshot, capability),
            *self._leadership_signals(snapshot, seniority),
            *self._volume_signals(snapshot),
            *self._trend_signals(snapshot, trend),
        ]
        signals.sort(
            key=lambda generated: (
                generated.signal.signal_type,
                generated.title,
                str(generated.signal.signal_id),
            )
        )
        return HiringSignalGenerationResult(
            organization=organization,
            generated_at=snapshot.generated_at,
            signals=signals,
        )

    def _geographic_signals(
        self,
        snapshot: HiringSnapshot,
        geography: GeographicHiringConcentration,
    ) -> list[GeneratedHiringSignal]:
        thresholds = self._thresholds
        if geography.total_jobs < thresholds.geographic_minimum_total_jobs:
            return []
        coverage = self._ratio(snapshot.jobs_with_location, snapshot.total_active_jobs)
        results: list[GeneratedHiringSignal] = []
        for level, groups in (
            ("country", geography.by_country),
            ("state/region", geography.by_state_region),
            ("city", geography.by_city),
        ):
            for group in groups:
                if (
                    group.job_count < thresholds.geographic_minimum_job_count
                    or group.percentage_of_total
                    < thresholds.geographic_minimum_percentage
                ):
                    continue
                evidence_coverage = self._evidence_coverage(
                    group.contributing_records,
                    group.job_count,
                )
                strength = self._unit(group.percentage_of_total / 100)
                sample_sufficiency = self._unit(
                    group.job_count
                    / (thresholds.geographic_minimum_job_count * 2)
                )
                score = self._score(
                    strength,
                    evidence_coverage,
                    sample_sufficiency,
                    coverage,
                )
                title = f"Observed hiring concentration in {group.value}"
                summary = (
                    f"{group.value} represents {group.percentage_of_total:g}% of "
                    f"observed hiring activity ({group.job_count} of "
                    f"{geography.total_jobs} jobs) at the {level} level; this is a "
                    "hiring concentration signal, not proof of investment."
                )
                results.append(
                    self._generated_signal(
                        snapshot,
                        HiringSignalType.GEOGRAPHIC_HIRING_CONCENTRATION,
                        subject=f"{level}:{group.value}",
                        title=title,
                        summary=summary,
                        score=score,
                        references=group.contributing_records,
                        limitations=self._limitations(snapshot),
                    )
                )
        return results

    def _capability_signals(
        self,
        snapshot: HiringSnapshot,
        capability: CapabilityHiringConcentration,
    ) -> list[GeneratedHiringSignal]:
        thresholds = self._thresholds
        classification_coverage = self._ratio(
            snapshot.jobs_with_capability_classification,
            snapshot.total_active_jobs,
        )
        if (
            capability.classified_job_count
            < thresholds.capability_minimum_classified_jobs
            or classification_coverage
            < thresholds.capability_minimum_classification_coverage
        ):
            return []
        limitations = self._limitations(
            snapshot,
            incomplete_capability_coverage=classification_coverage < 1,
        )
        results: list[GeneratedHiringSignal] = []
        for group in capability.capabilities:
            if (
                group.job_count < thresholds.capability_minimum_job_count
                or group.percentage_of_classified_jobs
                < thresholds.capability_minimum_percentage
            ):
                continue
            evidence_coverage = self._evidence_coverage(
                group.contributing_records,
                group.job_count,
            )
            strength = self._unit(group.percentage_of_classified_jobs / 100)
            sample_sufficiency = self._unit(
                group.job_count / (thresholds.capability_minimum_job_count * 2)
            )
            score = self._score(
                strength,
                evidence_coverage,
                sample_sufficiency,
                classification_coverage,
            )
            results.append(
                self._generated_signal(
                    snapshot,
                    HiringSignalType.CAPABILITY_HIRING_CONCENTRATION,
                    subject=group.capability,
                    title=f"Observed hiring demand for {group.capability}",
                    summary=(
                        f"{group.capability} accounts for "
                        f"{group.percentage_of_classified_jobs:g}% of classified "
                        f"hiring activity ({group.job_count} of "
                        f"{capability.classified_job_count} classified jobs); observed "
                        "demand suggests a hiring focus, not confirmed investment."
                    ),
                    score=score,
                    references=group.contributing_records,
                    limitations=limitations,
                )
            )
        return results

    def _leadership_signals(
        self,
        snapshot: HiringSnapshot,
        seniority: SeniorityHiringSummary,
    ) -> list[GeneratedHiringSignal]:
        thresholds = self._thresholds
        seniority_coverage = self._ratio(
            seniority.jobs_with_seniority,
            seniority.total_jobs,
        )
        if (
            seniority.total_jobs < thresholds.leadership_minimum_total_jobs
            or seniority_coverage < thresholds.leadership_minimum_seniority_coverage
            or seniority.leadership_job_count
            < thresholds.leadership_minimum_job_count
        ):
            return []
        evidence_coverage = self._evidence_coverage(
            seniority.leadership_contributing_records,
            seniority.leadership_job_count,
        )
        strength = self._unit(seniority.leadership_percentage / 100)
        sample_sufficiency = self._unit(
            seniority.leadership_job_count
            / (thresholds.leadership_minimum_job_count * 2)
        )
        score = self._score(
            strength,
            evidence_coverage,
            sample_sufficiency,
            seniority_coverage,
        )
        return [
            self._generated_signal(
                snapshot,
                HiringSignalType.LEADERSHIP_HIRING,
                subject="leadership",
                title="Observed leadership hiring activity",
                summary=(
                    f"Leadership roles represent {seniority.leadership_percentage:g}% "
                    f"of observed hiring activity ({seniority.leadership_job_count} of "
                    f"{seniority.total_jobs} jobs); this hiring signal does not establish "
                    "an organizational investment decision."
                ),
                score=score,
                references=seniority.leadership_contributing_records,
                limitations=self._limitations(
                    snapshot,
                    incomplete_seniority_coverage=seniority_coverage < 1,
                ),
            )
        ]

    def _volume_signals(
        self,
        snapshot: HiringSnapshot,
    ) -> list[GeneratedHiringSignal]:
        threshold = self._thresholds.hiring_volume_minimum_jobs
        if snapshot.total_active_jobs < threshold:
            return []
        evidence_coverage = self._evidence_coverage(
            snapshot.contributing_records,
            snapshot.total_active_jobs,
        )
        strength = self._unit(snapshot.total_active_jobs / (threshold * 2))
        score = self._score(
            strength,
            evidence_coverage,
            self._unit(snapshot.total_active_jobs / (threshold * 2)),
            1.0,
        )
        return [
            self._generated_signal(
                snapshot,
                HiringSignalType.HIRING_VOLUME,
                subject="observed-volume",
                title="Observed hiring volume",
                summary=(
                    f"{snapshot.total_active_jobs} active job postings were observed "
                    "during the observation period; this volume is a hiring activity "
                    "signal and does not by itself confirm strategic investment."
                ),
                score=score,
                references=snapshot.contributing_records,
                limitations=self._limitations(snapshot),
            )
        ]

    def _trend_signals(
        self,
        snapshot: HiringSnapshot,
        trend: HiringTrendSummary,
    ) -> list[GeneratedHiringSignal]:
        thresholds = self._thresholds
        if (
            trend.observation_start is None
            or trend.observation_end is None
            or len(trend.buckets) < thresholds.trend_minimum_buckets
            or (trend.observation_end - trend.observation_start).days
            < thresholds.trend_minimum_observation_days
        ):
            return []
        midpoint = len(trend.buckets) // 2
        earlier = trend.buckets[:midpoint]
        later = trend.buckets[midpoint:]
        earlier_average = sum(bucket.job_count for bucket in earlier) / len(earlier)
        later_average = sum(bucket.job_count for bucket in later) / len(later)
        if earlier_average == 0:
            return []
        change = (later_average - earlier_average) / earlier_average
        if abs(change) < thresholds.trend_minimum_directional_change:
            return []
        direction = "increased" if change > 0 else "decreased"
        evidence_coverage = self._evidence_coverage(
            trend.contributing_records,
            len(trend.contributing_records),
        )
        bucket_sufficiency = self._unit(
            len(trend.buckets) / (thresholds.trend_minimum_buckets * 2)
        )
        period_sufficiency = self._unit(
            (trend.observation_end - trend.observation_start).days
            / thresholds.trend_minimum_observation_days
        )
        score = self._score(
            self._unit(abs(change)),
            evidence_coverage,
            bucket_sufficiency,
            period_sufficiency,
        )
        return [
            self._generated_signal(
                snapshot,
                HiringSignalType.HIRING_TREND,
                subject=f"weekly:{direction}",
                title=f"Observed weekly hiring activity {direction}",
                summary=(
                    f"Average observed weekly hiring activity {direction} from "
                    f"{earlier_average:g} to {later_average:g} jobs per populated "
                    "bucket across the observation period; this directional hiring "
                    "signal is not proof of sustained growth, decline, or investment."
                ),
                score=score,
                references=trend.contributing_records,
                limitations=[
                    *self._limitations(snapshot),
                    "Trend compares populated time buckets and does not model zero-posting intervals.",
                ],
            )
        ]

    def _generated_signal(
        self,
        snapshot: HiringSnapshot,
        signal_type: HiringSignalType,
        *,
        subject: str,
        title: str,
        summary: str,
        score: HiringSignalScore,
        references: list[HiringRecordReference],
        limitations: list[str],
    ) -> GeneratedHiringSignal:
        observation_period = ObservationPeriod(
            start_date=snapshot.observation_start,
            end_date=snapshot.observation_end,
        )
        evidence_ids = sorted(
            {reference.evidence_id for reference in references},
            key=str,
        )
        identity = "|".join(
            (
                snapshot.organization,
                signal_type.value,
                subject,
                observation_period.start_date.isoformat(),
                observation_period.end_date.isoformat(),
            )
        )
        signal = IntelligenceSignal(
            signal_id=uuid5(NAMESPACE_URL, f"hiring-signal:{identity}"),
            signal_type=signal_type.value,
            organization=snapshot.organization,
            originating_capability=IntelligenceCapability.HIRING,
            observation_period=observation_period,
            summary=summary,
            confidence=score.confidence,
            supporting_evidence_ids=evidence_ids,
            limitations=limitations,
        )
        return GeneratedHiringSignal(title=title, signal=signal, score=score)

    def _limitations(
        self,
        snapshot: HiringSnapshot,
        *,
        incomplete_capability_coverage: bool = False,
        incomplete_seniority_coverage: bool = False,
    ) -> list[str]:
        limitations: list[str] = []
        if self._thresholds.single_source_data:
            limitations.append("Based on a single public hiring source.")
        if snapshot.total_active_jobs < self._thresholds.small_sample_job_count:
            limitations.append("Observed job sample is small.")
        if (
            snapshot.observation_start is not None
            and snapshot.observation_end is not None
            and (snapshot.observation_end - snapshot.observation_start).days
            < self._thresholds.limited_observation_window_days
        ):
            limitations.append("Observation window is limited.")
        if incomplete_capability_coverage:
            limitations.append("Capability classification coverage is incomplete.")
        if incomplete_seniority_coverage:
            limitations.append("Seniority coverage is incomplete.")
        return limitations

    @staticmethod
    def _score(
        strength: float,
        evidence_coverage: float,
        sample_sufficiency: float,
        data_coverage: float,
    ) -> HiringSignalScore:
        confidence = round(
            (evidence_coverage + sample_sufficiency + data_coverage) / 3,
            4,
        )
        return HiringSignalScore(
            strength=round(strength, 4),
            confidence=confidence,
            evidence_coverage=round(evidence_coverage, 4),
        )

    @staticmethod
    def _evidence_coverage(
        references: list[HiringRecordReference],
        expected_records: int,
    ) -> float:
        if expected_records == 0:
            return 0.0
        return HiringSignalService._unit(
            len({reference.evidence_id for reference in references}) / expected_records
        )

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        if denominator == 0:
            return 0.0
        return numerator / denominator

    @staticmethod
    def _unit(value: float) -> float:
        return max(0.0, min(1.0, value))
