from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, uuid5

import pytest

from backend.app.application.hiring import (
    CollectedJob,
    HiringAnalyticsService,
    HiringPersistenceService,
    HiringReadService,
    HiringTrendGranularity,
)
from backend.app.domain.hiring import JobPosting, SeniorityLevel
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


GENERATED_AT = datetime(2026, 8, 20, 15, tzinfo=timezone.utc)


def synthetic_job(
    source_job_id: str,
    *,
    organization: str = "Wells Fargo",
    country: str = "US",
    location: str = "Charlotte, NC",
    capabilities: list[str] | None = None,
    seniority: SeniorityLevel | None = None,
    leadership: bool = False,
    posted_date: date = date(2026, 8, 3),
) -> CollectedJob:
    evidence_id = uuid5(NAMESPACE_URL, f"analytics:evidence:{organization}:{source_job_id}")
    source_url = f"https://careers.example.test/jobs/{source_job_id}"
    evidence = Evidence(
        evidence_id=evidence_id,
        source_url=source_url,
        source_type=SourceType.CAREER_SITE,
        source_title=f"Role {source_job_id}",
        retrieved_at=GENERATED_AT,
        source_excerpt="Synthetic analytics evidence.",
        raw_reference=f"synthetic:{source_job_id}",
        collector_identity="synthetic-analytics-fixture",
        provenance_metadata={"fixture": True},
    )
    posting = JobPosting(
        job_id=uuid5(NAMESPACE_URL, f"analytics:job:{organization}:{source_job_id}"),
        organization=organization,
        source_job_id=source_job_id,
        title=f"Role {source_job_id}",
        description="Synthetic normalized job description.",
        location=location,
        country=country,
        capability_classifications=capabilities or [],
        seniority_level=seniority,
        is_leadership=leadership,
        posted_date=posted_date,
        source_url=source_url,
        evidence_id=evidence_id,
    )
    return CollectedJob(posting=posting, evidence=evidence)


@pytest.fixture
def database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "analytics.sqlite3")
    database.initialize()
    return database


@pytest.fixture
def jobs() -> list[CollectedJob]:
    return [
        synthetic_job(
            "R-1",
            capabilities=["Cloud", "Data"],
            seniority=SeniorityLevel.SENIOR,
        ),
        synthetic_job(
            "R-2",
            location="New York, NY",
            capabilities=["Data"],
            seniority=SeniorityLevel.DIRECTOR,
            leadership=True,
        ),
        synthetic_job(
            "R-3",
            location="Austin, TX / Charlotte, NC",
            posted_date=date(2026, 8, 4),
        ),
        synthetic_job(
            "R-4",
            country="IN",
            location="Bengaluru, Karnataka, India",
            capabilities=["Cloud", "Cloud"],
            seniority=SeniorityLevel.MANAGER,
            posted_date=date(2026, 8, 10),
        ),
        synthetic_job(
            "R-5",
            country="IN",
            location=" ",
            capabilities=[""],
            posted_date=date(2026, 8, 11),
        ),
        synthetic_job(
            "OTHER-1",
            organization="Example Bank",
            country="GB",
            location="London, United Kingdom",
            capabilities=["Payments"],
            seniority=SeniorityLevel.EXECUTIVE,
            leadership=True,
        ),
    ]


@pytest.fixture
def analytics(database, jobs) -> HiringAnalyticsService:
    HiringPersistenceService(database.unit_of_work).save_collected_jobs(jobs)
    return HiringAnalyticsService(
        HiringReadService(database.unit_of_work),
        clock=lambda: GENERATED_AT,
    )


def groups_by_value(groups):
    return {group.value: group for group in groups}


def capabilities_by_name(result):
    return {group.capability: group for group in result.capabilities}


def test_empty_organization_returns_clean_empty_results(database):
    service = HiringAnalyticsService(
        HiringReadService(database.unit_of_work),
        clock=lambda: GENERATED_AT,
    )

    snapshot = service.snapshot("Missing Bank")
    geography = service.geographic_concentration("Missing Bank")
    capability = service.capability_concentration("Missing Bank")
    seniority = service.seniority_summary("Missing Bank")
    trend = service.trend_summary("Missing Bank", HiringTrendGranularity.DAILY)

    assert snapshot.total_active_jobs == 0
    assert snapshot.observation_start is None
    assert snapshot.observation_end is None
    assert snapshot.contributing_records == []
    assert geography.total_jobs == 0
    assert geography.by_country == []
    assert capability.classified_job_count == 0
    assert capability.capabilities == []
    assert seniority.total_jobs == 0
    assert seniority.leadership_percentage == 0
    assert trend.buckets == []


def test_snapshot_counts_and_organization_isolation(analytics):
    snapshot = analytics.snapshot("Wells Fargo")

    assert snapshot.organization == "Wells Fargo"
    assert snapshot.total_active_jobs == 5
    assert snapshot.jobs_with_capability_classification == 3
    assert snapshot.jobs_with_seniority == 3
    assert snapshot.jobs_with_location == 4
    assert snapshot.generated_at == GENERATED_AT
    assert snapshot.observation_start == date(2026, 8, 3)
    assert snapshot.observation_end == date(2026, 8, 11)
    assert len(snapshot.contributing_records) == 5
    assert analytics.snapshot("Example Bank").total_active_jobs == 1


def test_geographic_country_region_city_aggregations_and_percentages(analytics):
    result = analytics.geographic_concentration("Wells Fargo")
    countries = groups_by_value(result.by_country)
    regions = groups_by_value(result.by_state_region)
    cities = groups_by_value(result.by_city)

    assert countries["US"].job_count == 3
    assert countries["US"].percentage_of_total == 60.0
    assert countries["IN"].job_count == 2
    assert countries["IN"].percentage_of_total == 40.0
    assert regions["NC"].job_count == 2
    assert regions["NC"].percentage_of_total == 40.0
    assert regions["NY"].job_count == 1
    assert regions["TX"].job_count == 1
    assert regions["Karnataka"].job_count == 1
    assert cities["Charlotte"].job_count == 2
    assert cities["Austin"].job_count == 1
    assert cities["New York"].job_count == 1
    assert cities["Bengaluru"].job_count == 1


def test_capability_aggregation_uses_classified_jobs_as_denominator(analytics):
    result = analytics.capability_concentration("Wells Fargo")
    groups = capabilities_by_name(result)

    assert result.classified_job_count == 3
    assert groups["Cloud"].job_count == 2
    assert groups["Cloud"].percentage_of_classified_jobs == 66.67
    assert groups["Data"].job_count == 2
    assert groups["Data"].percentage_of_classified_jobs == 66.67
    assert len(groups["Cloud"].contributing_records) == 2
    assert "" not in groups


def test_seniority_distribution_and_leadership_metrics(analytics):
    result = analytics.seniority_summary("Wells Fargo")
    distribution = {group.seniority_level: group for group in result.distribution}

    assert result.total_jobs == 5
    assert result.jobs_with_seniority == 3
    assert distribution[SeniorityLevel.SENIOR].job_count == 1
    assert distribution[SeniorityLevel.SENIOR].percentage_of_jobs_with_seniority == 33.33
    assert distribution[SeniorityLevel.DIRECTOR].job_count == 1
    assert distribution[SeniorityLevel.MANAGER].job_count == 1
    assert result.leadership_job_count == 1
    assert result.leadership_percentage == 20.0
    assert len(result.leadership_contributing_records) == 1


def test_daily_and_weekly_trend_buckets_without_growth_claims(analytics):
    daily = analytics.trend_summary("Wells Fargo", HiringTrendGranularity.DAILY)
    weekly = analytics.trend_summary("Wells Fargo", HiringTrendGranularity.WEEKLY)

    assert [(bucket.bucket_start, bucket.job_count) for bucket in daily.buckets] == [
        (date(2026, 8, 3), 2),
        (date(2026, 8, 4), 1),
        (date(2026, 8, 10), 1),
        (date(2026, 8, 11), 1),
    ]
    assert [(bucket.bucket_start, bucket.job_count) for bucket in weekly.buckets] == [
        (date(2026, 8, 3), 3),
        (date(2026, 8, 10), 2),
    ]
    assert "growth" not in daily.model_dump()


def test_every_aggregate_entry_preserves_job_and_evidence_references(analytics):
    snapshot = analytics.snapshot("Wells Fargo")
    geography = analytics.geographic_concentration("Wells Fargo")
    capability = analytics.capability_concentration("Wells Fargo")
    seniority = analytics.seniority_summary("Wells Fargo")
    trend = analytics.trend_summary("Wells Fargo", HiringTrendGranularity.WEEKLY)

    assert all(reference.job_id and reference.evidence_id for reference in snapshot.contributing_records)
    aggregate_references = [
        geography.contributing_records,
        capability.contributing_records,
        seniority.contributing_records,
        trend.contributing_records,
        *(group.contributing_records for group in geography.by_country),
        *(group.contributing_records for group in geography.by_state_region),
        *(group.contributing_records for group in geography.by_city),
        *(group.contributing_records for group in capability.capabilities),
        *(group.contributing_records for group in seniority.distribution),
        seniority.leadership_contributing_records,
        *(bucket.contributing_records for bucket in trend.buckets),
    ]
    assert all(
        reference.job_id and reference.evidence_id
        for references in aggregate_references
        for reference in references
    )


def test_results_are_deterministic_and_use_no_network_or_llm(analytics):
    first = {
        "snapshot": analytics.snapshot("Wells Fargo").model_dump(mode="json"),
        "geography": analytics.geographic_concentration("Wells Fargo").model_dump(mode="json"),
        "capability": analytics.capability_concentration("Wells Fargo").model_dump(mode="json"),
        "seniority": analytics.seniority_summary("Wells Fargo").model_dump(mode="json"),
        "trend": analytics.trend_summary(
            "Wells Fargo", HiringTrendGranularity.WEEKLY
        ).model_dump(mode="json"),
    }
    second = {
        "snapshot": analytics.snapshot("Wells Fargo").model_dump(mode="json"),
        "geography": analytics.geographic_concentration("Wells Fargo").model_dump(mode="json"),
        "capability": analytics.capability_concentration("Wells Fargo").model_dump(mode="json"),
        "seniority": analytics.seniority_summary("Wells Fargo").model_dump(mode="json"),
        "trend": analytics.trend_summary(
            "Wells Fargo", HiringTrendGranularity.WEEKLY
        ).model_dump(mode="json"),
    }

    assert first == second
