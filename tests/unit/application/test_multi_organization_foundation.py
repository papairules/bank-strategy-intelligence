from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.application.agents import (
    EvidenceIdInput,
    EvidenceSearchInput,
    JobIdInput,
    JobSearchInput,
    OrganizationInput,
    TechnologyObservationSearchInput,
)
from backend.app.application.hiring import (
    CanonicalJobIdentity,
    CanonicalJobImport,
    EnrichmentField,
    EnrichmentFieldSupport,
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    HiringCapability,
    HiringEnrichmentPersistenceService,
    HiringEnrichmentResult,
    HiringPersistenceService,
    HiringReadService,
)
from backend.app.config import HiringSettings
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.domain.organization import OrganizationIdentity
from backend.app.infrastructure.composition.agent_tools import create_agent_intelligence_tools
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


NOW = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
ORGANIZATIONS = ("Wells Fargo", "Goldman Sachs", "BNY")


def canonical_import(
    organization: str,
    *,
    source_id: str = "synthetic-careers",
    external_job_id: str = "12345",
    technology: str = "Python",
) -> CanonicalJobImport:
    identity = CanonicalJobIdentity(
        organization=OrganizationIdentity.from_display_name(organization),
        source_id=source_id,
        external_job_id=external_job_id,
    )
    provenance = {
        "organization_key": identity.organization.key,
        "source_id": source_id,
        "external_job_id": external_job_id,
        "source_system": "Synthetic Careers",
    }
    evidence = Evidence(
        evidence_id=identity.evidence_id,
        source_url=f"https://careers.example.test/{identity.organization.key}/{external_job_id}",
        source_type=SourceType.CAREER_SITE,
        source_title=f"{technology} Engineer",
        retrieved_at=NOW,
        source_excerpt=f"Use {technology} in this role.",
        raw_reference=f"{source_id}:{identity.organization.key}:{external_job_id}",
        collector_identity="synthetic-multi-organization-v1",
        provenance_metadata=provenance,
    )
    posting = JobPosting(
        job_id=identity.job_id,
        organization=organization,
        source_job_id=identity.source_scoped_job_id,
        title=f"{technology} Engineer",
        description=f"Use {technology} in this role.",
        location="New York, NY",
        country="US",
        posted_date=date(2026, 8, 20),
        source_url=evidence.source_url,
        evidence_id=identity.evidence_id,
    )
    return CanonicalJobImport(identity=identity, posting=posting, evidence=evidence)


def enrichment(item: CanonicalJobImport, technology: str) -> HiringEnrichmentResult:
    return HiringEnrichmentResult(
        job_id=item.posting.job_id,
        evidence_id=item.evidence.evidence_id,
        capability_classifications=[HiringCapability.SOFTWARE_ENGINEERING],
        skills=[technology],
        technologies=[technology],
        seniority_level=EnrichmentSeniority.MID,
        is_leadership=False,
        confidence=0.9,
        field_confidences={EnrichmentField.TECHNOLOGIES: 1.0},
        field_support=[EnrichmentFieldSupport(field=EnrichmentField.TECHNOLOGIES, value=technology, excerpt=technology, evidence_id=item.evidence.evidence_id)],
        limitations=["Synthetic offline organization-isolation fixture."],
        model_metadata=EnrichmentModelMetadata(provider="fake", model="offline", prompt_schema_version="hiring-enrichment-v3", enrichment_timestamp=NOW, model_confidence=0.9),
    )


@pytest.fixture
def multi_organization_fixture(tmp_path):
    database = SQLiteDatabase(tmp_path / "multi-organization.sqlite3")
    database.initialize()
    technologies = ("Python", "Java", "COBOL")
    imports = [canonical_import(organization, technology=technology) for organization, technology in zip(ORGANIZATIONS, technologies, strict=True)]
    HiringPersistenceService(database.unit_of_work).save_collected_jobs(imports)
    persistence = HiringEnrichmentPersistenceService(database.unit_of_work)
    for item, technology in zip(imports, technologies, strict=True):
        persistence.save(enrichment(item, technology))
    settings = HiringSettings(sqlite_database_path=tmp_path / "multi-organization.sqlite3")
    return database, imports, technologies, create_agent_intelligence_tools(settings)


def test_canonical_identity_is_stable_and_scoped_by_organization_and_source():
    wells = canonical_import("Wells Fargo")
    goldman = canonical_import("Goldman Sachs")
    bny = canonical_import("BNY")
    other_source = canonical_import("Wells Fargo", source_id="other-careers")

    assert wells.identity.organization.key == "wells_fargo"
    assert goldman.identity.organization.key == "goldman_sachs"
    assert bny.identity.organization.key == "bny"
    assert len({item.posting.job_id for item in (wells, goldman, bny, other_source)}) == 4
    assert len({item.evidence.evidence_id for item in (wells, goldman, bny, other_source)}) == 4
    assert wells.identity == canonical_import("Wells Fargo").identity


def test_canonical_import_rejects_identity_and_provenance_mismatch():
    item = canonical_import("Wells Fargo")
    with pytest.raises(ValidationError, match="posting organization"):
        CanonicalJobImport(identity=item.identity, posting=item.posting.model_copy(update={"organization": "Goldman Sachs"}), evidence=item.evidence)
    with pytest.raises(ValidationError, match="provenance"):
        CanonicalJobImport(identity=item.identity, posting=item.posting, evidence=item.evidence.model_copy(update={"provenance_metadata": {}}))
    with pytest.raises(ValidationError, match="source_url"):
        CanonicalJobImport(
            identity=item.identity,
            posting=item.posting.model_copy(
                update={"source_url": "https://careers.example.test/wrong"}
            ),
            evidence=item.evidence,
        )


def test_persistence_is_idempotent_within_scope_and_distinct_across_organizations(multi_organization_fixture):
    database, imports, _, _ = multi_organization_fixture
    HiringPersistenceService(database.unit_of_work).save_collected_jobs([imports[0]])
    read = HiringReadService(database.unit_of_work)

    assert len(read.list_all_jobs()) == 3
    assert [len(read.list_jobs_for_analytics(name)) for name in ORGANIZATIONS] == [1, 1, 1]
    assert len({item.posting.source_job_id for item in imports}) == 1
    assert len({item.posting.job_id for item in imports}) == 3


def test_intelligence_and_agent_tools_are_isolated_by_organization(multi_organization_fixture):
    database, imports, technologies, tools = multi_organization_fixture
    read = HiringReadService(database.unit_of_work)

    for index, organization in enumerate(ORGANIZATIONS):
        other = imports[(index + 1) % len(imports)]
        jobs = tools.hiring.search_jobs(JobSearchInput(organization=organization))
        assert jobs.total == 1
        assert {item.organization for item in jobs.items} == {organization}
        assert tools.hiring.get_job_intelligence(JobIdInput(organization=organization, job_id=imports[index].posting.job_id)).found
        assert not tools.hiring.get_job_intelligence(JobIdInput(organization=organization, job_id=other.posting.job_id)).found

        evidence = tools.evidence.search(EvidenceSearchInput(organization=organization))
        assert evidence.total == 1
        assert {item.organization for item in evidence.items} == {organization}
        assert not tools.evidence.get(EvidenceIdInput(organization=organization, evidence_id=other.evidence.evidence_id)).found
        assert not tools.evidence.trace(EvidenceIdInput(organization=organization, evidence_id=other.evidence.evidence_id)).found

        enrichments = read.list_enrichments(organization)
        assert [item.job_id for item in enrichments] == [imports[index].posting.job_id]
        observations = tools.technology.search_observations(TechnologyObservationSearchInput(organization=organization))
        assert observations.total == 1
        assert observations.items[0].normalized_technology == technologies[index]
        assert observations.items[0].organization == organization

        hiring_signals = tools.hiring.get_signals(OrganizationInput(organization=organization))
        technology_signals = tools.technology.get_signals(OrganizationInput(organization=organization))
        strategy_signals = tools.strategy.get_signals(OrganizationInput(organization=organization))
        assert hiring_signals.organization == organization
        assert technology_signals.organization == organization
        assert strategy_signals.organization == organization
        assert technology_signals.signals == []
        assert strategy_signals.signals == []


def test_direct_agent_tool_contracts_require_explicit_organization():
    with pytest.raises(ValidationError):
        JobIdInput(job_id=canonical_import("Wells Fargo").posting.job_id)
    with pytest.raises(ValidationError):
        EvidenceIdInput(evidence_id=canonical_import("Wells Fargo").evidence.evidence_id)
