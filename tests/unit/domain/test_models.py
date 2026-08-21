from datetime import date, datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.domain.hiring import EmploymentType, JobPosting, SeniorityLevel
from backend.app.domain.intelligence import (
    Evidence,
    IntelligenceCapability,
    IntelligenceSignal,
    ObservationPeriod,
    SourceType,
)


EVIDENCE_ID = UUID("11111111-1111-1111-1111-111111111111")
SIGNAL_ID = UUID("22222222-2222-2222-2222-222222222222")
JOB_ID = UUID("33333333-3333-3333-3333-333333333333")


def test_evidence_serializes_domain_types():
    evidence = Evidence(
        evidence_id=EVIDENCE_ID,
        source_url="https://careers.example.com/jobs/123",
        source_type=SourceType.CAREER_SITE,
        source_title="Senior Data Engineer",
        retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        source_excerpt="Build the bank's data platform.",
        collector_identity="example-careers-collector",
        provenance_metadata={"http_status": 200, "archived": False},
    )

    assert evidence.model_dump(mode="json") == {
        "evidence_id": str(EVIDENCE_ID),
        "source_url": "https://careers.example.com/jobs/123",
        "source_type": "career_site",
        "source_title": "Senior Data Engineer",
        "retrieved_at": "2026-08-20T12:00:00Z",
        "source_excerpt": "Build the bank's data platform.",
        "raw_reference": None,
        "collector_identity": "example-careers-collector",
        "provenance_metadata": {"http_status": 200, "archived": False},
    }


def test_evidence_requires_traceable_content_and_aware_timestamp():
    common_fields = {
        "source_url": "https://careers.example.com/jobs/123",
        "source_type": SourceType.CAREER_SITE,
        "collector_identity": "example-careers-collector",
    }

    with pytest.raises(ValidationError):
        Evidence(retrieved_at=datetime(2026, 8, 20, 12, 0), **common_fields)

    with pytest.raises(ValidationError):
        Evidence(
            retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            **common_fields,
        )


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_intelligence_signal_rejects_confidence_outside_unit_interval(confidence):
    with pytest.raises(ValidationError):
        IntelligenceSignal(
            signal_type="hiring_concentration",
            organization="Example Bank",
            originating_capability=IntelligenceCapability.HIRING,
            observation_period=ObservationPeriod(
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            ),
            summary="Hiring is concentrated in data engineering.",
            confidence=confidence,
            supporting_evidence_ids=[EVIDENCE_ID],
            limitations=[],
        )


def test_intelligence_signal_serializes_evidence_links_and_period():
    signal = IntelligenceSignal(
        signal_id=SIGNAL_ID,
        signal_type="hiring_concentration",
        organization="Example Bank",
        originating_capability=IntelligenceCapability.HIRING,
        observation_period=ObservationPeriod(
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        ),
        summary="Hiring is concentrated in data engineering.",
        confidence=0.85,
        supporting_evidence_ids=[EVIDENCE_ID],
        limitations=["Only public postings were analyzed."],
    )

    assert signal.model_dump(mode="json") == {
        "signal_id": str(SIGNAL_ID),
        "signal_type": "hiring_concentration",
        "organization": "Example Bank",
        "originating_capability": "hiring",
        "observation_period": {
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
        },
        "summary": "Hiring is concentrated in data engineering.",
        "confidence": 0.85,
        "supporting_evidence_ids": [str(EVIDENCE_ID)],
        "limitations": ["Only public postings were analyzed."],
    }


def test_observation_period_rejects_reversed_dates():
    with pytest.raises(ValidationError):
        ObservationPeriod(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 7, 31),
        )


def test_job_posting_serializes_normalized_fields():
    posting = JobPosting(
        job_id=JOB_ID,
        organization="Example Bank",
        source_job_id="JOB-123",
        title="Director of Data Platforms",
        description="Lead data platform modernization.",
        location="New York, NY",
        country="US",
        business_unit="Technology",
        capability_classifications=["data_platforms"],
        skills=["data architecture", "leadership"],
        technologies=["Python", "Snowflake"],
        seniority_level=SeniorityLevel.DIRECTOR,
        is_leadership=True,
        posted_date=date(2026, 8, 1),
        closing_date=date(2026, 8, 31),
        employment_type=EmploymentType.FULL_TIME,
        source_url="https://careers.example.com/jobs/JOB-123",
        evidence_id=EVIDENCE_ID,
    )

    assert posting.model_dump(mode="json") == {
        "job_id": str(JOB_ID),
        "organization": "Example Bank",
        "source_job_id": "JOB-123",
        "title": "Director of Data Platforms",
        "description": "Lead data platform modernization.",
        "location": "New York, NY",
        "country": "US",
        "business_unit": "Technology",
        "capability_classifications": ["data_platforms"],
        "skills": ["data architecture", "leadership"],
        "technologies": ["Python", "Snowflake"],
        "seniority_level": "director",
        "is_leadership": True,
        "posted_date": "2026-08-01",
        "closing_date": "2026-08-31",
        "employment_type": "full_time",
        "source_url": "https://careers.example.com/jobs/JOB-123",
        "evidence_id": str(EVIDENCE_ID),
    }


def test_job_posting_rejects_closing_date_before_posted_date():
    with pytest.raises(ValidationError):
        JobPosting(
            organization="Example Bank",
            source_job_id="JOB-123",
            title="Data Engineer",
            description="Build data products.",
            location="New York, NY",
            country="US",
            posted_date=date(2026, 8, 20),
            closing_date=date(2026, 8, 19),
            source_url="https://careers.example.com/jobs/JOB-123",
            evidence_id=EVIDENCE_ID,
        )
