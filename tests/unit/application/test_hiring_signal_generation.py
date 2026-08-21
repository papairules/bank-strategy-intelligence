from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from backend.app.application.hiring import (
    HiringAnalyticsService,
    HiringSignalService,
    HiringSignalThresholds,
    HiringSignalType,
)
from backend.app.domain.hiring import JobPosting, SeniorityLevel


GENERATED_AT = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


class StaticJobQuery:
    def __init__(self, jobs: list[JobPosting]) -> None:
        self.jobs = jobs

    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]:
        return [job for job in self.jobs if job.organization == organization]


def job(
    source_job_id: str,
    *,
    organization: str = "Example Bank",
    location: str = "Charlotte, NC",
    capability: str | None = None,
    seniority: SeniorityLevel | None = None,
    leadership: bool = False,
    posted_date: date,
) -> JobPosting:
    return JobPosting(
        job_id=uuid5(NAMESPACE_URL, f"signal-job:{organization}:{source_job_id}"),
        organization=organization,
        source_job_id=source_job_id,
        title=f"Role {source_job_id}",
        description="Synthetic normalized description.",
        location=location,
        country="US",
        capability_classifications=[capability] if capability else [],
        seniority_level=seniority,
        is_leadership=leadership,
        posted_date=posted_date,
        source_url=f"https://careers.example.test/jobs/{source_job_id}",
        evidence_id=uuid5(
            NAMESPACE_URL,
            f"signal-evidence:{organization}:{source_job_id}",
        ),
    )


def sufficient_jobs(organization: str = "Example Bank") -> list[JobPosting]:
    return [
        job(
            "R-1",
            organization=organization,
            capability="Risk Technology",
            seniority=SeniorityLevel.SENIOR,
            posted_date=date(2026, 8, 3),
        ),
        job(
            "R-2",
            organization=organization,
            capability="Risk Technology",
            seniority=SeniorityLevel.DIRECTOR,
            leadership=True,
            posted_date=date(2026, 8, 10),
        ),
        job(
            "R-3",
            organization=organization,
            capability="Risk Technology",
            seniority=SeniorityLevel.MANAGER,
            leadership=True,
            posted_date=date(2026, 8, 17),
        ),
        job(
            "R-4",
            organization=organization,
            capability="Risk Technology",
            seniority=SeniorityLevel.SENIOR,
            posted_date=date(2026, 8, 18),
        ),
        job(
            "R-5",
            organization=organization,
            location="New York, NY",
            capability="Data Platforms",
            seniority=SeniorityLevel.MID,
            posted_date=date(2026, 8, 19),
        ),
        job(
            "R-6",
            organization=organization,
            location="New York, NY",
            capability="Data Platforms",
            seniority=SeniorityLevel.MID,
            posted_date=date(2026, 8, 24),
        ),
        job(
            "R-7",
            organization=organization,
            location="Chicago, IL",
            posted_date=date(2026, 8, 25),
        ),
        job(
            "R-8",
            organization=organization,
            location="Chicago, IL",
            posted_date=date(2026, 8, 26),
        ),
    ]


def service(
    jobs: list[JobPosting],
    thresholds: HiringSignalThresholds | None = None,
) -> HiringSignalService:
    analytics = HiringAnalyticsService(
        StaticJobQuery(jobs),
        clock=lambda: GENERATED_AT,
    )
    return HiringSignalService(analytics, thresholds)


def signals_of_type(result, signal_type: HiringSignalType):
    return [
        generated
        for generated in result.signals
        if generated.signal.signal_type == signal_type.value
    ]


def test_empty_analytics_generates_no_signals():
    result = service([]).generate("Example Bank")

    assert result.organization == "Example Bank"
    assert result.generated_at == GENERATED_AT
    assert result.signals == []


def test_geographic_signal_above_threshold_and_below_threshold():
    jobs = sufficient_jobs()
    above = service(jobs).generate("Example Bank")
    below = service(
        jobs,
        HiringSignalThresholds(geographic_minimum_percentage=60),
    ).generate("Example Bank")

    geographic = signals_of_type(
        above,
        HiringSignalType.GEOGRAPHIC_HIRING_CONCENTRATION,
    )
    assert any("Charlotte" in generated.title for generated in geographic)
    assert not any(
        "Charlotte" in generated.title
        for generated in signals_of_type(
            below,
            HiringSignalType.GEOGRAPHIC_HIRING_CONCENTRATION,
        )
    )


def test_capability_signal_and_insufficient_classification_coverage():
    jobs = sufficient_jobs()
    result = service(jobs).generate("Example Bank")
    capability = signals_of_type(
        result,
        HiringSignalType.CAPABILITY_HIRING_CONCENTRATION,
    )

    risk = next(
        generated for generated in capability if "Risk Technology" in generated.title
    )
    expected_evidence = {
        current.evidence_id
        for current in jobs
        if current.capability_classifications == ["Risk Technology"]
    }
    assert set(risk.signal.supporting_evidence_ids) == expected_evidence
    assert "Capability classification coverage is incomplete." in risk.signal.limitations

    low_coverage_jobs = [
        job(
            f"LOW-{index}",
            capability="Risk Technology" if index == 0 else None,
            posted_date=date(2026, 8, index + 1),
        )
        for index in range(5)
    ]
    low_coverage = service(low_coverage_jobs).generate("Example Bank")
    assert signals_of_type(
        low_coverage,
        HiringSignalType.CAPABILITY_HIRING_CONCENTRATION,
    ) == []


def test_leadership_signal_and_insufficient_seniority_coverage():
    result = service(sufficient_jobs()).generate("Example Bank")
    leadership = signals_of_type(result, HiringSignalType.LEADERSHIP_HIRING)

    assert len(leadership) == 1
    assert len(leadership[0].signal.supporting_evidence_ids) == 2
    assert "Seniority coverage is incomplete." in leadership[0].signal.limitations

    sparse = [
        job(
            f"SPARSE-{index}",
            seniority=SeniorityLevel.DIRECTOR if index < 2 else None,
            leadership=index < 2,
            posted_date=date(2026, 8, index + 1),
        )
        for index in range(6)
    ]
    assert signals_of_type(
        service(sparse).generate("Example Bank"),
        HiringSignalType.LEADERSHIP_HIRING,
    ) == []


def test_hiring_volume_requires_minimum_observed_jobs():
    enough = service(sufficient_jobs()).generate("Example Bank")
    too_few = service(sufficient_jobs()[:4]).generate("Example Bank")

    assert len(signals_of_type(enough, HiringSignalType.HIRING_VOLUME)) == 1
    assert signals_of_type(too_few, HiringSignalType.HIRING_VOLUME) == []


def test_trend_requires_sufficient_bucket_history_and_generates_direction_safely():
    sufficient = service(sufficient_jobs()).generate("Example Bank")
    trend = signals_of_type(sufficient, HiringSignalType.HIRING_TREND)

    assert len(trend) == 1
    assert "increased" in trend[0].signal.summary
    assert "populated time buckets" in " ".join(trend[0].signal.limitations)

    insufficient = service(sufficient_jobs()[:5]).generate("Example Bank")
    assert signals_of_type(insufficient, HiringSignalType.HIRING_TREND) == []


def test_observation_period_confidence_scores_and_limitations_are_valid():
    result = service(sufficient_jobs()).generate("Example Bank")

    assert result.signals
    for generated in result.signals:
        signal = generated.signal
        assert signal.observation_period.start_date == date(2026, 8, 3)
        assert signal.observation_period.end_date == date(2026, 8, 26)
        assert 0 <= signal.confidence <= 1
        assert signal.confidence == generated.score.confidence
        assert 0 <= generated.score.strength <= 1
        assert 0 <= generated.score.evidence_coverage <= 1
        assert generated.score.evidence_coverage == 1
        assert signal.supporting_evidence_ids
        assert "Based on a single public hiring source." in signal.limitations
        assert "Observed job sample is small." in signal.limitations
        assert "Observation window is limited." in signal.limitations


def test_signal_generation_is_deterministic_and_organization_isolated():
    example_jobs = sufficient_jobs("Example Bank")
    other_jobs = sufficient_jobs("Other Bank")
    generator = service([*example_jobs, *other_jobs])

    first = generator.generate("Example Bank").model_dump(mode="json")
    second = generator.generate("Example Bank").model_dump(mode="json")
    other = generator.generate("Other Bank")

    assert first == second
    assert all(
        generated.signal.organization == "Other Bank" for generated in other.signals
    )
    example_evidence = {current.evidence_id for current in example_jobs}
    assert all(
        set(generated.signal.supporting_evidence_ids) <= example_evidence
        for generated in generator.generate("Example Bank").signals
    )
