import json
from datetime import datetime, timezone

import pytest

from backend.app.application.agents.supervisor_agent import (
    CompactHiringKGSummary,
    CompanyIntelligenceReport,
    EvidenceAssessment,
    HiringCoverageMetadata,
    SupervisorReportResult,
    SupervisorResponse,
)
from backend.app.infrastructure.persistence.hiring import (
    SQLiteDatabase,
    SQLiteSupervisorReportCacheRepository,
)


@pytest.fixture
def database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "supervisor_report_cache.sqlite3")
    database.initialize()
    return database


def result(question: str = "report", organization: str = "Wells Fargo") -> SupervisorReportResult:
    return SupervisorReportResult(
        organization=organization,
        strategy_signal_count=0,
        hiring_signal_count=0,
        coverage=HiringCoverageMetadata(
            organization=organization,
            total_jobs=0,
            enriched_jobs=0,
            enrichment_coverage_percentage=0,
            classified_jobs=0,
            classification_coverage_percentage=0,
            kg_enriched_job_count=0,
        ),
        kg_summary=CompactHiringKGSummary(organization=organization, node_count=0, edge_count=0, enriched_jobs_used=0),
        supervisor=SupervisorResponse(
            generated_at=datetime(2026, 8, 23, tzinfo=timezone.utc).isoformat(),
            company_id=organization.upper().replace(" ", "_"),
            company_name=organization,
            question=question,
            mode="report",
            executive_summary=f"Summary for: {question}",
            evidence_assessment=EvidenceAssessment(sufficient=True, overall_confidence=0.6),
            opportunities=[],
            limitations=[],
            answer=f"Summary for: {question}",
        ),
        report=CompanyIntelligenceReport(
            organization=organization,
            generated_at=datetime(2026, 8, 23, tzinfo=timezone.utc).isoformat(),
            executive_summary=f"Summary for: {question}",
        ),
        provider="openai",
        model="gpt-5.4-mini",
    )


def test_get_returns_none_when_absent(database):
    repository = SQLiteSupervisorReportCacheRepository(database)

    assert repository.get(
        organization="Wells Fargo",
        question_key="report",
        time_horizon="",
        provider="openai",
        model="gpt-5.4-mini",
    ) is None


def test_save_and_get_round_trips_the_result(database):
    repository = SQLiteSupervisorReportCacheRepository(database)
    generated_at = datetime(2026, 8, 23, 12, tzinfo=timezone.utc).isoformat()

    repository.save(
        organization="Wells Fargo",
        question_key="report",
        time_horizon="",
        provider="openai",
        model="gpt-5.4-mini",
        generated_at=generated_at,
        result=result(),
    )
    fetched = repository.get(
        organization="Wells Fargo",
        question_key="report",
        time_horizon="",
        provider="openai",
        model="gpt-5.4-mini",
    )

    assert fetched is not None
    fetched_result, fetched_generated_at = fetched
    assert fetched_result == result()
    assert fetched_generated_at == generated_at


def test_save_overwrites_existing_entry_for_the_same_key(database):
    repository = SQLiteSupervisorReportCacheRepository(database)
    key = dict(
        organization="Wells Fargo",
        question_key="report",
        time_horizon="",
        provider="openai",
        model="gpt-5.4-mini",
    )

    repository.save(**key, generated_at="2026-08-01T00:00:00+00:00", result=result("first"))
    repository.save(**key, generated_at="2026-08-23T00:00:00+00:00", result=result("second"))
    fetched_result, fetched_generated_at = repository.get(**key)

    assert fetched_generated_at == "2026-08-23T00:00:00+00:00"
    assert fetched_result.supervisor.question == "second"


def test_different_time_horizon_is_a_distinct_entry(database):
    repository = SQLiteSupervisorReportCacheRepository(database)
    base_key = dict(
        organization="Wells Fargo",
        question_key="report",
        provider="openai",
        model="gpt-5.4-mini",
    )

    repository.save(**base_key, time_horizon="12 months", generated_at="2026-08-23T00:00:00+00:00", result=result())
    fetched = repository.get(**base_key, time_horizon="24 months")

    assert fetched is None


def test_incompatible_cached_json_is_treated_as_a_cache_miss(database):
    repository = SQLiteSupervisorReportCacheRepository(database)
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO supervisor_report_cache (
                organization, question_key, time_horizon, provider, model,
                generated_at, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Wells Fargo",
                "report",
                "",
                "openai",
                "gpt-5.4-mini",
                "2026-08-23T00:00:00+00:00",
                json.dumps({"stale_schema": True}),
            ),
        )
        connection.commit()

    assert repository.get(
        organization="Wells Fargo",
        question_key="report",
        time_horizon="",
        provider="openai",
        model="gpt-5.4-mini",
    ) is None
