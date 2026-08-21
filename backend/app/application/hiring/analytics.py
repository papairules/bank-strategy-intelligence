from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.hiring import JobPosting, SeniorityLevel


class HiringAnalyticsJobQuery(Protocol):
    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]: ...


class HiringRecordReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: UUID
    evidence_id: UUID


class HiringSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    total_active_jobs: int = Field(ge=0)
    jobs_with_capability_classification: int = Field(ge=0)
    jobs_with_seniority: int = Field(ge=0)
    jobs_with_location: int = Field(ge=0)
    generated_at: datetime
    observation_start: date | None = None
    observation_end: date | None = None
    contributing_records: list[HiringRecordReference] = Field(default_factory=list)


class GeographicHiringGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    job_count: int = Field(ge=1)
    percentage_of_total: float = Field(ge=0, le=100)
    contributing_records: list[HiringRecordReference] = Field(min_length=1)


class GeographicHiringConcentration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    total_jobs: int = Field(ge=0)
    by_country: list[GeographicHiringGroup] = Field(default_factory=list)
    by_state_region: list[GeographicHiringGroup] = Field(default_factory=list)
    by_city: list[GeographicHiringGroup] = Field(default_factory=list)
    contributing_records: list[HiringRecordReference] = Field(default_factory=list)


class CapabilityHiringGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    job_count: int = Field(ge=1)
    percentage_of_classified_jobs: float = Field(ge=0, le=100)
    contributing_records: list[HiringRecordReference] = Field(min_length=1)


class CapabilityHiringConcentration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    classified_job_count: int = Field(ge=0)
    capabilities: list[CapabilityHiringGroup] = Field(default_factory=list)
    contributing_records: list[HiringRecordReference] = Field(default_factory=list)


class SeniorityHiringGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seniority_level: SeniorityLevel
    job_count: int = Field(ge=1)
    percentage_of_jobs_with_seniority: float = Field(ge=0, le=100)
    contributing_records: list[HiringRecordReference] = Field(min_length=1)


class SeniorityHiringSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    total_jobs: int = Field(ge=0)
    jobs_with_seniority: int = Field(ge=0)
    distribution: list[SeniorityHiringGroup] = Field(default_factory=list)
    leadership_job_count: int = Field(ge=0)
    leadership_percentage: float = Field(ge=0, le=100)
    leadership_contributing_records: list[HiringRecordReference] = Field(
        default_factory=list
    )
    contributing_records: list[HiringRecordReference] = Field(default_factory=list)


class HiringTrendGranularity(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class HiringTrendBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket_start: date
    job_count: int = Field(ge=1)
    contributing_records: list[HiringRecordReference] = Field(min_length=1)


class HiringTrendSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    granularity: HiringTrendGranularity
    observation_start: date | None = None
    observation_end: date | None = None
    buckets: list[HiringTrendBucket] = Field(default_factory=list)
    contributing_records: list[HiringRecordReference] = Field(default_factory=list)


class HiringAnalyticsService:
    def __init__(
        self,
        job_query: HiringAnalyticsJobQuery,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._job_query = job_query
        self._clock = clock

    def snapshot(self, organization: str) -> HiringSnapshot:
        jobs = self._jobs(organization)
        dates = self._posted_dates(jobs)
        return HiringSnapshot(
            organization=organization,
            total_active_jobs=len(jobs),
            jobs_with_capability_classification=sum(
                bool(self._capabilities(job)) for job in jobs
            ),
            jobs_with_seniority=sum(job.seniority_level is not None for job in jobs),
            jobs_with_location=sum(bool(job.location.strip()) for job in jobs),
            generated_at=self._clock(),
            observation_start=min(dates) if dates else None,
            observation_end=max(dates) if dates else None,
            contributing_records=self._references(jobs),
        )

    def geographic_concentration(
        self,
        organization: str,
    ) -> GeographicHiringConcentration:
        jobs = self._jobs(organization)
        countries: dict[str, list[JobPosting]] = defaultdict(list)
        regions: dict[str, list[JobPosting]] = defaultdict(list)
        cities: dict[str, list[JobPosting]] = defaultdict(list)
        for job in jobs:
            country = job.country.strip()
            if country:
                countries[country].append(job)
            job_regions: set[str] = set()
            job_cities: set[str] = set()
            for location in job.location.split(" / "):
                city, region = self._parse_location(location, country)
                if city:
                    job_cities.add(city)
                if region:
                    job_regions.add(region)
            for region in job_regions:
                regions[region].append(job)
            for city in job_cities:
                cities[city].append(job)
        return GeographicHiringConcentration(
            organization=organization,
            total_jobs=len(jobs),
            by_country=self._geographic_groups(countries, len(jobs)),
            by_state_region=self._geographic_groups(regions, len(jobs)),
            by_city=self._geographic_groups(cities, len(jobs)),
            contributing_records=self._references(jobs),
        )

    def capability_concentration(
        self,
        organization: str,
    ) -> CapabilityHiringConcentration:
        jobs = self._jobs(organization)
        classified_jobs = [job for job in jobs if self._capabilities(job)]
        grouped: dict[str, list[JobPosting]] = defaultdict(list)
        for job in classified_jobs:
            for capability in self._capabilities(job):
                grouped[capability].append(job)
        capabilities = [
            CapabilityHiringGroup(
                capability=capability,
                job_count=len(contributors),
                percentage_of_classified_jobs=self._percentage(
                    len(contributors),
                    len(classified_jobs),
                ),
                contributing_records=self._references(contributors),
            )
            for capability, contributors in grouped.items()
        ]
        capabilities.sort(key=lambda item: (-item.job_count, item.capability))
        return CapabilityHiringConcentration(
            organization=organization,
            classified_job_count=len(classified_jobs),
            capabilities=capabilities,
            contributing_records=self._references(classified_jobs),
        )

    def seniority_summary(self, organization: str) -> SeniorityHiringSummary:
        jobs = self._jobs(organization)
        grouped: dict[SeniorityLevel, list[JobPosting]] = defaultdict(list)
        leadership_jobs: list[JobPosting] = []
        for job in jobs:
            if job.seniority_level is not None:
                grouped[job.seniority_level].append(job)
            if job.is_leadership:
                leadership_jobs.append(job)
        jobs_with_seniority = sum(len(contributors) for contributors in grouped.values())
        distribution = [
            SeniorityHiringGroup(
                seniority_level=level,
                job_count=len(contributors),
                percentage_of_jobs_with_seniority=self._percentage(
                    len(contributors),
                    jobs_with_seniority,
                ),
                contributing_records=self._references(contributors),
            )
            for level, contributors in grouped.items()
        ]
        distribution.sort(
            key=lambda item: (-item.job_count, item.seniority_level.value)
        )
        return SeniorityHiringSummary(
            organization=organization,
            total_jobs=len(jobs),
            jobs_with_seniority=jobs_with_seniority,
            distribution=distribution,
            leadership_job_count=len(leadership_jobs),
            leadership_percentage=self._percentage(len(leadership_jobs), len(jobs)),
            leadership_contributing_records=self._references(leadership_jobs),
            contributing_records=self._references(jobs),
        )

    def trend_summary(
        self,
        organization: str,
        granularity: HiringTrendGranularity,
    ) -> HiringTrendSummary:
        jobs = self._jobs(organization)
        grouped: dict[date, list[JobPosting]] = defaultdict(list)
        for job in jobs:
            posted_date = getattr(job, "posted_date", None)
            if posted_date is None:
                continue
            bucket = (
                posted_date
                if granularity is HiringTrendGranularity.DAILY
                else posted_date - timedelta(days=posted_date.weekday())
            )
            grouped[bucket].append(job)
        buckets = [
            HiringTrendBucket(
                bucket_start=bucket,
                job_count=len(contributors),
                contributing_records=self._references(contributors),
            )
            for bucket, contributors in sorted(grouped.items())
        ]
        dates = self._posted_dates(jobs)
        return HiringTrendSummary(
            organization=organization,
            granularity=granularity,
            observation_start=min(dates) if dates else None,
            observation_end=max(dates) if dates else None,
            buckets=buckets,
            contributing_records=self._references(jobs),
        )

    def _jobs(self, organization: str) -> list[JobPosting]:
        return sorted(
            self._job_query.list_jobs_for_analytics(organization),
            key=lambda job: str(job.job_id),
        )

    @staticmethod
    def _capabilities(job: JobPosting) -> list[str]:
        return sorted(
            {
                capability.strip()
                for capability in job.capability_classifications
                if capability.strip()
            }
        )

    @staticmethod
    def _posted_dates(jobs: list[JobPosting]) -> list[date]:
        return [
            posted_date
            for job in jobs
            if (posted_date := getattr(job, "posted_date", None)) is not None
        ]

    @staticmethod
    def _parse_location(location: str, country: str) -> tuple[str | None, str | None]:
        parts = [part.strip() for part in location.split(",") if part.strip()]
        if not parts:
            return None, None
        city = parts[0]
        region = None
        if len(parts) >= 3:
            region = parts[-2]
        elif len(parts) == 2 and country.upper() in {"US", "CA", "AU"}:
            region = parts[1]
        return city, region

    @classmethod
    def _geographic_groups(
        cls,
        grouped: dict[str, list[JobPosting]],
        total_jobs: int,
    ) -> list[GeographicHiringGroup]:
        groups = [
            GeographicHiringGroup(
                value=value,
                job_count=len(contributors),
                percentage_of_total=cls._percentage(len(contributors), total_jobs),
                contributing_records=cls._references(contributors),
            )
            for value, contributors in grouped.items()
        ]
        groups.sort(key=lambda item: (-item.job_count, item.value))
        return groups

    @staticmethod
    def _references(jobs: list[JobPosting]) -> list[HiringRecordReference]:
        return [
            HiringRecordReference(job_id=job.job_id, evidence_id=job.evidence_id)
            for job in sorted(jobs, key=lambda item: str(item.job_id))
        ]

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        if denominator == 0:
            return 0.0
        return round(numerator / denominator * 100, 2)
