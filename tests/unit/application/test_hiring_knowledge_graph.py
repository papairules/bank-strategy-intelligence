from datetime import date, datetime, timezone
from uuid import UUID

import networkx as nx
import pytest

from backend.app.application.hiring import (
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    GeneratedHiringSignal,
    HiringCapability,
    HiringEnrichmentResult,
    HiringSignalGenerationResult,
    HiringSignalScore,
)
from backend.app.application.hiring.kg import (
    HiringKGEdgeType,
    HiringKGNodeType,
    HiringKnowledgeGraphService,
    concept_node_id,
    evidence_node_id,
    get_business_units_for_organization,
    get_capabilities_for_organization,
    get_evidence_for_job,
    get_jobs_for_capability,
    get_jobs_for_technology,
    get_jobs_supporting_hiring_signal,
    get_technologies_for_organization,
    extract_source_technologies,
    job_node_id,
    organization_node_id,
    summarize_hiring_knowledge_graph,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import (
    Evidence,
    IntelligenceCapability,
    IntelligenceSignal,
    ObservationPeriod,
    SourceType,
)


NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)
WELLS_JOB_ID = UUID("00000000-0000-0000-0000-000000000101")
PLAIN_JOB_ID = UUID("00000000-0000-0000-0000-000000000102")
BNY_JOB_ID = UUID("00000000-0000-0000-0000-000000000201")
WELLS_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000011")
PLAIN_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000012")
BNY_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000021")
SIGNAL_ID = UUID("00000000-0000-0000-0000-000000000301")


def job(job_id, evidence_id, organization="Wells Fargo", **values):
    defaults = dict(
        job_id=job_id,
        evidence_id=evidence_id,
        organization=organization,
        source_job_id=f"SRC-{job_id.int}",
        title="Platform Engineer",
        description="Build Python services on AWS.",
        location="Charlotte, NC",
        country="US",
        posted_date=date(2026, 8, 1),
        source_url=f"https://jobs.example.test/{job_id}",
    )
    defaults.update(values)
    return JobPosting(**defaults)


def evidence(evidence_id, job_id):
    return Evidence(
        evidence_id=evidence_id,
        source_url=f"https://jobs.example.test/{job_id}",
        source_type=SourceType.CAREER_SITE,
        retrieved_at=NOW,
        source_excerpt="Build Python services on AWS.",
        collector_identity="approved_csv_import",
    )


def enrichment(posting, *, model="gpt-new"):
    return HiringEnrichmentResult(
        job_id=posting.job_id,
        evidence_id=posting.evidence_id,
        source_content_hash="a" * 64,
        capability_classifications=[HiringCapability.CLOUD_INFRASTRUCTURE],
        skills=["Platform engineering"],
        technologies=["Python", "AWS"],
        seniority_level=EnrichmentSeniority.SENIOR,
        is_leadership=False,
        business_unit="Technology",
        hiring_themes=[],
        confidence=0.82,
        field_confidences={},
        field_support=[],
        limitations=[],
        model_metadata=EnrichmentModelMetadata(
            provider="openai",
            model=model,
            prompt_schema_version="openai-hiring-enrichment-v1",
            enrichment_timestamp=NOW,
            model_confidence=0.82,
        ),
    )


class FakeRead:
    def __init__(self, jobs, evidence_records, enrichments=None):
        self.jobs = jobs
        self.evidence = {item.evidence_id: item for item in evidence_records}
        self.enrichments = enrichments or {}
        self.latest_calls = []

    def list_jobs_for_analytics(self, organization):
        return list(self.jobs)

    def get_evidence(self, evidence_id):
        return self.evidence.get(evidence_id)

    def get_latest_enrichment(self, job_id):
        self.latest_calls.append(job_id)
        return self.enrichments.get(job_id)


class FakeSignals:
    def __init__(self, signals=None, organization="Wells Fargo"):
        self.signals = signals or []
        self.organization = organization

    def generate(self, organization):
        return HiringSignalGenerationResult(
            organization=self.organization,
            generated_at=NOW,
            signals=self.signals,
        )


def generated_signal(organization="Wells Fargo", evidence_ids=None):
    return GeneratedHiringSignal(
        title="Observed hiring demand for Cloud & Infrastructure",
        signal=IntelligenceSignal(
            signal_id=SIGNAL_ID,
            signal_type="capability_hiring_concentration",
            organization=organization,
            originating_capability=IntelligenceCapability.HIRING,
            observation_period=ObservationPeriod(
                start_date=date(2026, 8, 1), end_date=date(2026, 8, 2)
            ),
            summary="Observed hiring concentration.",
            confidence=0.75,
            supporting_evidence_ids=evidence_ids or [WELLS_EVIDENCE_ID],
        ),
        score=HiringSignalScore(strength=0.8, confidence=0.75, evidence_coverage=1),
    )


def fixture_service(*, include_signal=False):
    enriched = job(WELLS_JOB_ID, WELLS_EVIDENCE_ID)
    plain = job(
        PLAIN_JOB_ID,
        PLAIN_EVIDENCE_ID,
        capability_classifications=["Raw classification must not enter KG"],
        technologies=["RawDB"],
        business_unit="Raw unit",
    )
    read = FakeRead(
        [plain, enriched],
        [evidence(PLAIN_EVIDENCE_ID, PLAIN_JOB_ID), evidence(WELLS_EVIDENCE_ID, WELLS_JOB_ID)],
        {WELLS_JOB_ID: enrichment(enriched)},
    )
    signals = FakeSignals([generated_signal()] if include_signal else [])
    return HiringKnowledgeGraphService(read, signals), read


def test_deterministic_company_scoped_nodes_edges_and_latest_enrichment_only():
    service, read = fixture_service()

    first = service.build_for_organization("Wells Fargo")
    second = service.build_for_organization("Wells Fargo")

    assert isinstance(first, nx.MultiDiGraph)
    assert set(first.nodes) == set(second.nodes)
    assert set(first.edges(keys=True)) == set(second.edges(keys=True))
    assert read.latest_calls.count(WELLS_JOB_ID) == 2
    assert organization_node_id("Wells Fargo") in first
    assert job_node_id(WELLS_JOB_ID) in first
    assert evidence_node_id(WELLS_EVIDENCE_ID) in first
    assert get_capabilities_for_organization(first) == ["Cloud & Infrastructure"]
    assert get_technologies_for_organization(first) == ["AWS", "Python"]
    assert get_business_units_for_organization(first) == ["Technology"]
    assert "Raw classification must not enter KG" not in get_capabilities_for_organization(first)
    assert "RawDB" not in get_technologies_for_organization(first)


def test_enriched_relationship_provenance_and_query_helpers():
    graph = fixture_service()[0].build_for_organization("Wells Fargo")
    technology = concept_node_id(HiringKGNodeType.TECHNOLOGY, "Wells Fargo", "Python")
    edge = graph.get_edge_data(job_node_id(WELLS_JOB_ID), technology)[HiringKGEdgeType.USES_TECHNOLOGY.value]

    assert edge["organization"] == "Wells Fargo"
    assert edge["job_id"] == str(WELLS_JOB_ID)
    assert edge["source_job_id"]
    assert edge["evidence_id"] == str(WELLS_EVIDENCE_ID)
    assert edge["source_url"].startswith("https://jobs.example.test/")
    assert edge["derivation_type"] == "latest_persisted_enrichment"
    assert edge["enrichment_provider"] == "openai"
    assert edge["enrichment_model"] == "gpt-new"
    assert edge["prompt_schema_version"] == "openai-hiring-enrichment-v1"
    assert edge["enrichment_confidence"] == 0.82
    assert edge["source_content_hash"] == "a" * 64
    assert "description" not in edge
    assert edge["support_classification"] == "multiple"
    assert edge["support_classifications"] == ["source_evidence", "ai_enrichment"]
    assert len(edge["provenance_records"]) == 2
    assert get_jobs_for_capability(graph, "Cloud & Infrastructure") == [WELLS_JOB_ID]
    assert get_jobs_for_technology(graph, "Python") == [WELLS_JOB_ID, PLAIN_JOB_ID]
    assert get_evidence_for_job(graph, WELLS_JOB_ID) == [WELLS_EVIDENCE_ID]


def test_unenriched_job_has_only_base_relationships_and_summary_is_safe():
    graph = fixture_service()[0].build_for_organization("Wells Fargo")
    outgoing = {
        attributes["edge_type"]
        for _, _, attributes in graph.out_edges(job_node_id(PLAIN_JOB_ID), data=True)
    }
    summary = summarize_hiring_knowledge_graph(graph)

    assert outgoing == {
        HiringKGEdgeType.SUPPORTED_BY.value,
        HiringKGEdgeType.LOCATED_IN.value,
        HiringKGEdgeType.USES_TECHNOLOGY.value,
    }
    assert summary.organization == "Wells Fargo"
    assert summary.jobs_read == 2
    assert summary.evidence_records_used == 2
    assert summary.enriched_jobs_used == 1
    assert summary.node_counts[HiringKGNodeType.JOB] == 2
    assert summary.edge_counts[HiringKGEdgeType.CLASSIFIED_AS] == 1
    assert "description" not in summary.model_dump_json()


def test_source_only_technology_relationship_is_grounded_and_queryable():
    graph = fixture_service()[0].build_for_organization("Wells Fargo")
    technology = concept_node_id(HiringKGNodeType.TECHNOLOGY, "Wells Fargo", "Python")
    edge = graph.get_edge_data(job_node_id(PLAIN_JOB_ID), technology)[
        HiringKGEdgeType.USES_TECHNOLOGY.value
    ]

    assert edge["derivation_type"] == "persisted_source_technology"
    assert edge["support_classification"] == "source_evidence"
    assert edge["source_field"] == "job.description"
    assert edge["matched_value"] == "Python"
    assert edge["matched_text"] == "Python"
    assert edge["evidence_id"] == str(PLAIN_EVIDENCE_ID)
    assert get_jobs_for_technology(graph, "Python") == [WELLS_JOB_ID, PLAIN_JOB_ID]


def test_source_extraction_uses_boundaries_and_is_deterministic():
    text = "Pythonic code, Python; SQL and SQLServer. AWS, not awsish."
    first = extract_source_technologies(text)
    second = extract_source_technologies(text)

    assert first == second
    assert [item.technology for item in first] == ["AWS", "Python", "SQL"]
    assert all(item.source_field == "job.description" for item in first)


def test_source_technology_concepts_remain_organization_qualified():
    wells_graph = fixture_service()[0].build_for_organization("Wells Fargo")
    bny_posting = job(BNY_JOB_ID, BNY_EVIDENCE_ID, organization="BNY")
    bny_graph = HiringKnowledgeGraphService(
        FakeRead([bny_posting], [evidence(BNY_EVIDENCE_ID, BNY_JOB_ID)]),
        FakeSignals(organization="BNY"),
    ).build_for_organization("BNY")

    wells_technology = concept_node_id(HiringKGNodeType.TECHNOLOGY, "Wells Fargo", "Python")
    bny_technology = concept_node_id(HiringKGNodeType.TECHNOLOGY, "BNY", "Python")
    assert wells_technology in wells_graph
    assert bny_technology in bny_graph
    assert bny_technology not in wells_graph
    assert wells_technology not in bny_graph


def test_deterministic_hiring_signal_is_evidence_linked_and_queryable():
    graph = fixture_service(include_signal=True)[0].build_for_organization("Wells Fargo")

    assert get_jobs_supporting_hiring_signal(graph, SIGNAL_ID) == [WELLS_JOB_ID]
    signal = f"hiring_signal:{SIGNAL_ID}"
    capability = concept_node_id(
        HiringKGNodeType.CAPABILITY, "Wells Fargo", "Cloud & Infrastructure"
    )
    assert graph.has_edge(signal, evidence_node_id(WELLS_EVIDENCE_ID), HiringKGEdgeType.SUPPORTED_BY.value)
    assert graph.has_edge(signal, capability, HiringKGEdgeType.ABOUT_CAPABILITY.value)
    assert summarize_hiring_knowledge_graph(graph).hiring_signals_used == 1


def test_concept_ids_are_organization_qualified():
    wells = concept_node_id(HiringKGNodeType.TECHNOLOGY, "Wells Fargo", "Python")
    bny = concept_node_id(HiringKGNodeType.TECHNOLOGY, "BNY", "Python")
    assert wells == "technology:wells_fargo:python"
    assert bny == "technology:bny:python"
    assert wells != bny


def test_cross_company_job_enrichment_and_signal_are_rejected():
    wells_evidence = evidence(WELLS_EVIDENCE_ID, WELLS_JOB_ID)
    other_job = job(BNY_JOB_ID, BNY_EVIDENCE_ID, organization="BNY")
    with pytest.raises(ValueError, match="another organization's job"):
        HiringKnowledgeGraphService(
            FakeRead([other_job], [evidence(BNY_EVIDENCE_ID, BNY_JOB_ID)]),
            FakeSignals(),
        ).build_for_organization("Wells Fargo")

    wells_job = job(WELLS_JOB_ID, WELLS_EVIDENCE_ID)
    mismatch = enrichment(wells_job).model_copy(update={"job_id": BNY_JOB_ID})
    with pytest.raises(ValueError, match="does not match"):
        HiringKnowledgeGraphService(
            FakeRead([wells_job], [wells_evidence], {WELLS_JOB_ID: mismatch}),
            FakeSignals(),
        ).build_for_organization("Wells Fargo")

    with pytest.raises(ValueError, match="another organization's signal"):
        HiringKnowledgeGraphService(
            FakeRead([wells_job], [wells_evidence]),
            FakeSignals([generated_signal(organization="BNY")]),
        ).build_for_organization("Wells Fargo")


def test_signal_cannot_reference_evidence_outside_company_graph():
    wells_job = job(WELLS_JOB_ID, WELLS_EVIDENCE_ID)
    with pytest.raises(ValueError, match="outside the company graph"):
        HiringKnowledgeGraphService(
            FakeRead([wells_job], [evidence(WELLS_EVIDENCE_ID, WELLS_JOB_ID)]),
            FakeSignals([generated_signal(evidence_ids=[BNY_EVIDENCE_ID])]),
        ).build_for_organization("Wells Fargo")
