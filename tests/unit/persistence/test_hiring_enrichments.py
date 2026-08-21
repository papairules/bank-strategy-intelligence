from datetime import datetime, timedelta, timezone
import sqlite3
from uuid import uuid4

import pytest

from backend.app.application.hiring import (
    EnrichmentField,
    EnrichmentFieldSupport,
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    HiringCapability,
    HiringEnrichmentPersistenceService,
    HiringEnrichmentResult,
    HiringReadService,
    HiringTheme,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


GENERATED_AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "enrichments.sqlite3")
    database.initialize()
    return database


def persist_source_records(
    database: SQLiteDatabase,
    *,
    organization: str = "Example Bank",
) -> tuple[JobPosting, Evidence]:
    evidence = Evidence(
        evidence_id=uuid4(),
        source_url="https://careers.example.test/jobs/R-1",
        source_type=SourceType.CAREER_SITE,
        source_title="Senior Analytics Consultant",
        retrieved_at=GENERATED_AT - timedelta(hours=1),
        source_excerpt="Use Python and SQL for portfolio analytics.",
        raw_reference="career:example:R-1",
        collector_identity="synthetic-test-collector",
        provenance_metadata={"fixture": True},
    )
    posting = JobPosting(
        organization=organization,
        source_job_id=f"R-{uuid4()}",
        title="Senior Analytics Consultant",
        description="Use Python and SQL for portfolio analytics.",
        location="Charlotte, NC",
        country="US",
        posted_date="2026-08-20",
        source_url="https://careers.example.test/jobs/R-1",
        evidence_id=evidence.evidence_id,
    )
    with database.unit_of_work() as unit_of_work:
        unit_of_work.evidence.save(evidence)
        unit_of_work.job_postings.save(posting)
        unit_of_work.commit()
    return posting, evidence


def make_enrichment(
    posting: JobPosting,
    evidence: Evidence,
    *,
    model: str = "gemini-2.5-flash",
    schema_version: str = "hiring-enrichment-v3",
    generated_at: datetime = GENERATED_AT,
) -> HiringEnrichmentResult:
    return HiringEnrichmentResult(
        job_id=posting.job_id,
        evidence_id=evidence.evidence_id,
        capability_classifications=[HiringCapability.DATA_ANALYTICS],
        skills=["portfolio analytics"],
        technologies=["Python", "SQL"],
        seniority_level=EnrichmentSeniority.SENIOR,
        is_leadership=False,
        business_unit="Consumer Analytics",
        hiring_themes=[HiringTheme.DATA_MODERNIZATION],
        confidence=0.91,
        field_confidences={
            EnrichmentField.SKILLS: 1.0,
            EnrichmentField.TECHNOLOGIES: 1.0,
            EnrichmentField.CAPABILITY_CLASSIFICATIONS: 0.65,
        },
        field_support=[
            EnrichmentFieldSupport(
                field=EnrichmentField.TECHNOLOGIES,
                value="Python",
                excerpt="Python",
                evidence_id=evidence.evidence_id,
            ),
            EnrichmentFieldSupport(
                field=EnrichmentField.TECHNOLOGIES,
                value="SQL",
                excerpt="SQL",
                evidence_id=evidence.evidence_id,
            ),
        ],
        limitations=["Enrichment uses only supplied evidence."],
        model_metadata=EnrichmentModelMetadata(
            provider="vertex_gemini",
            model=model,
            prompt_schema_version=schema_version,
            provider_request_id="response-1",
            model_version="gemini-2.5-flash-001",
            usage_metadata={"total_token_count": 500},
            enrichment_timestamp=generated_at,
            model_confidence=0.88,
        ),
    )


def test_database_initialization_adds_enrichment_schema_and_indexes(database):
    with sqlite3.connect(database.path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert "hiring_enrichments" in tables
    assert "idx_hiring_enrichments_job_latest" in indexes
    assert "idx_hiring_enrichments_evidence_id" in indexes


def test_enrichment_round_trip_preserves_complete_application_result(database):
    posting, evidence = persist_source_records(database)
    enrichment = make_enrichment(posting, evidence)

    HiringEnrichmentPersistenceService(database.unit_of_work).save(enrichment)
    retrieved = HiringReadService(database.unit_of_work).get_enrichment(
        job_id=posting.job_id,
        evidence_id=evidence.evidence_id,
        provider="vertex_gemini",
        model="gemini-2.5-flash",
        prompt_schema_version="hiring-enrichment-v3",
    )

    assert retrieved == enrichment
    assert retrieved.capability_classifications == [HiringCapability.DATA_ANALYTICS]
    assert retrieved.skills == ["portfolio analytics"]
    assert retrieved.technologies == ["Python", "SQL"]
    assert retrieved.seniority_level is EnrichmentSeniority.SENIOR
    assert retrieved.business_unit == "Consumer Analytics"
    assert retrieved.hiring_themes == [HiringTheme.DATA_MODERNIZATION]
    assert retrieved.confidence == 0.91
    assert retrieved.model_metadata.model_confidence == 0.88
    assert retrieved.field_confidences[EnrichmentField.TECHNOLOGIES] == 1.0
    assert retrieved.field_support == enrichment.field_support
    assert retrieved.limitations == enrichment.limitations
    assert retrieved.model_metadata == enrichment.model_metadata


def test_repeated_save_is_idempotent_and_updates_same_logical_version(database):
    posting, evidence = persist_source_records(database)
    enrichment = make_enrichment(posting, evidence)
    updated = enrichment.model_copy(
        update={"confidence": 0.95, "limitations": ["Updated validation note."]}
    )
    service = HiringEnrichmentPersistenceService(database.unit_of_work)

    service.save(enrichment)
    service.save(updated)

    with database.unit_of_work() as unit_of_work:
        stored = unit_of_work.enrichments.list_by_organization("Example Bank")
    assert stored == [updated]


def test_model_and_schema_versions_coexist_and_latest_uses_timestamp(database):
    posting, evidence = persist_source_records(database)
    older = make_enrichment(posting, evidence)
    newer_schema = make_enrichment(
        posting,
        evidence,
        schema_version="hiring-enrichment-v4",
        generated_at=GENERATED_AT + timedelta(minutes=1),
    )
    newer_model = make_enrichment(
        posting,
        evidence,
        model="gemini-3-flash",
        schema_version="hiring-enrichment-v4",
        generated_at=GENERATED_AT + timedelta(minutes=2),
    )
    service = HiringEnrichmentPersistenceService(database.unit_of_work)

    for enrichment in (older, newer_schema, newer_model):
        service.save(enrichment)

    read_service = HiringReadService(database.unit_of_work)
    assert read_service.get_latest_enrichment(posting.job_id) == newer_model
    assert len(read_service.list_enrichments("Example Bank")) == 3


def test_exact_cache_lookup_and_missing_enrichment_are_deterministic(database):
    posting, evidence = persist_source_records(database)
    enrichment = make_enrichment(posting, evidence)
    service = HiringEnrichmentPersistenceService(database.unit_of_work)

    assert not service.has_current(
        job_id=posting.job_id,
        evidence_id=evidence.evidence_id,
        provider="vertex_gemini",
        model="gemini-2.5-flash",
        prompt_schema_version="hiring-enrichment-v3",
    )
    assert HiringReadService(database.unit_of_work).get_latest_enrichment(
        posting.job_id
    ) is None

    service.save(enrichment)

    assert service.has_current(
        job_id=posting.job_id,
        evidence_id=evidence.evidence_id,
        provider="vertex_gemini",
        model="gemini-2.5-flash",
        prompt_schema_version="hiring-enrichment-v3",
    )


def test_organization_queries_are_isolated(database):
    first_posting, first_evidence = persist_source_records(database)
    second_posting, second_evidence = persist_source_records(
        database,
        organization="Other Bank",
    )
    service = HiringEnrichmentPersistenceService(database.unit_of_work)
    service.save(make_enrichment(first_posting, first_evidence))
    service.save(make_enrichment(second_posting, second_evidence))

    read_service = HiringReadService(database.unit_of_work)
    first = read_service.list_enrichments("Example Bank")
    second = read_service.list_enrichments("Other Bank")

    assert [result.job_id for result in first] == [first_posting.job_id]
    assert [result.job_id for result in second] == [second_posting.job_id]


def test_persistence_survives_service_and_database_reconstruction(database):
    posting, evidence = persist_source_records(database)
    enrichment = make_enrichment(posting, evidence)
    HiringEnrichmentPersistenceService(database.unit_of_work).save(enrichment)

    reconstructed = SQLiteDatabase(database.path)
    reconstructed.initialize()
    retrieved = HiringReadService(
        reconstructed.unit_of_work
    ).get_latest_enrichment(posting.job_id)

    assert retrieved == enrichment


def test_support_references_must_match_original_evidence(database):
    posting, evidence = persist_source_records(database)
    enrichment = make_enrichment(posting, evidence)
    enrichment.field_support[0].evidence_id = uuid4()

    with pytest.raises(ValueError, match="support evidence_id must match"):
        HiringEnrichmentPersistenceService(database.unit_of_work).save(enrichment)

    assert HiringReadService(database.unit_of_work).get_latest_enrichment(
        posting.job_id
    ) is None


def test_enrichment_cannot_link_a_job_to_another_organizations_evidence(database):
    posting, _ = persist_source_records(database, organization="Wells Fargo")
    _, other_evidence = persist_source_records(database, organization="Goldman Sachs")
    mismatched = make_enrichment(posting, other_evidence)

    with pytest.raises(ValueError, match="source job evidence_id"):
        HiringEnrichmentPersistenceService(database.unit_of_work).save(mismatched)

    assert HiringReadService(database.unit_of_work).get_latest_enrichment(posting.job_id) is None
