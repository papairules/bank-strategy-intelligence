import re
from typing import Protocol
import unicodedata
from uuid import UUID

import networkx as nx

from backend.app.application.hiring.analytics import HiringAnalyticsService
from backend.app.application.hiring.enrichment import (
    EnrichmentSeniority,
    HiringEnrichmentResult,
)
from backend.app.application.hiring.queries import HiringReadServiceProtocol
from backend.app.application.hiring.signal_generation import (
    GeneratedHiringSignal,
    HiringSignalGenerationResult,
    HiringSignalService,
    HiringSignalType,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence
from backend.app.domain.organization import organization_key

from .models import HiringKGEdgeType, HiringKGNodeType, HiringKnowledgeGraphSummary


class HiringSignalBoundary(Protocol):
    def generate(self, organization: str) -> HiringSignalGenerationResult: ...


def normalized_graph_value(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    key = re.sub(r"[^a-z0-9]+", "_", normalized.casefold()).strip("_")
    if not key:
        raise ValueError("graph concept values must contain letters or numbers")
    return key


def organization_node_id(organization: str) -> str:
    return f"org:{organization_key(organization)}"


def job_node_id(job_id: UUID | str) -> str:
    return f"job:{job_id}"


def evidence_node_id(evidence_id: UUID | str) -> str:
    return f"evidence:{evidence_id}"


def concept_node_id(node_type: HiringKGNodeType, organization: str, value: str) -> str:
    prefixes = {
        HiringKGNodeType.LOCATION: "location",
        HiringKGNodeType.BUSINESS_UNIT: "business_unit",
        HiringKGNodeType.CAPABILITY: "capability",
        HiringKGNodeType.TECHNOLOGY: "technology",
        HiringKGNodeType.SENIORITY: "seniority",
    }
    if node_type not in prefixes:
        raise ValueError("node type is not an organization-qualified concept")
    return f"{prefixes[node_type]}:{organization_key(organization)}:{normalized_graph_value(value)}"


def signal_node_id(signal_id: UUID | str) -> str:
    return f"hiring_signal:{signal_id}"


class HiringKnowledgeGraphService:
    def __init__(
        self,
        read_service: HiringReadServiceProtocol,
        signal_service: HiringSignalBoundary | None = None,
    ) -> None:
        self._read = read_service
        self._signals = signal_service or HiringSignalService(
            HiringAnalyticsService(read_service)
        )

    def build_for_organization(self, organization: str) -> nx.MultiDiGraph:
        organization = organization.strip()
        if not organization:
            raise ValueError("organization must not be blank")
        graph = nx.MultiDiGraph(organization=organization)
        org_id = organization_node_id(organization)
        graph.add_node(
            org_id,
            node_type=HiringKGNodeType.ORGANIZATION.value,
            organization=organization,
            label=organization,
        )

        jobs = sorted(
            self._read.list_jobs_for_analytics(organization),
            key=lambda item: (item.posted_date, str(item.job_id)),
        )
        evidence_ids: set[UUID] = set()
        enriched_jobs = 0
        for job in jobs:
            if job.organization != organization:
                raise ValueError("company-scoped hiring graph received another organization's job")
            evidence = self._read.get_evidence(job.evidence_id)
            if evidence is None:
                raise ValueError("company-scoped hiring graph requires matching persisted evidence")
            if evidence.evidence_id != job.evidence_id:
                raise ValueError("job and evidence identities do not match")
            evidence_ids.add(evidence.evidence_id)
            enrichment = self._read.get_latest_enrichment(job.job_id)
            if enrichment is not None:
                self._validate_enrichment(job, enrichment)
                enriched_jobs += 1
            self._add_job(graph, org_id, job, evidence, enrichment)

        signal_result = self._signals.generate(organization)
        if signal_result.organization != organization:
            raise ValueError("company-scoped hiring graph received another organization's signals")
        signals = sorted(signal_result.signals, key=lambda item: str(item.signal.signal_id))
        for generated in signals:
            self._add_signal(graph, org_id, generated, organization, evidence_ids)

        graph.graph.update(
            jobs_read=len(jobs),
            evidence_records_used=len(evidence_ids),
            enriched_jobs_used=enriched_jobs,
            hiring_signals_used=len(signals),
        )
        return graph

    @staticmethod
    def _validate_enrichment(job: JobPosting, enrichment: HiringEnrichmentResult) -> None:
        if enrichment.job_id != job.job_id or enrichment.evidence_id != job.evidence_id:
            raise ValueError("latest hiring enrichment does not match its job and evidence")

    def _add_job(
        self,
        graph: nx.MultiDiGraph,
        org_id: str,
        job: JobPosting,
        evidence: Evidence,
        enrichment: HiringEnrichmentResult | None,
    ) -> None:
        job_id = job_node_id(job.job_id)
        evidence_id = evidence_node_id(evidence.evidence_id)
        graph.add_node(
            job_id,
            node_type=HiringKGNodeType.JOB.value,
            organization=job.organization,
            job_id=str(job.job_id),
            source_job_id=job.source_job_id,
            label=job.title,
        )
        graph.add_node(
            evidence_id,
            node_type=HiringKGNodeType.EVIDENCE.value,
            organization=job.organization,
            evidence_id=str(evidence.evidence_id),
            source_url=str(evidence.source_url),
            source_type=evidence.source_type.value,
        )
        base = self._provenance(job, evidence, "persisted_source", None)
        self._add_edge(graph, org_id, job_id, HiringKGEdgeType.HAS_JOB, base)
        self._add_edge(graph, job_id, evidence_id, HiringKGEdgeType.SUPPORTED_BY, base)
        self._add_concept_edge(
            graph, job, evidence, None, job.location, HiringKGNodeType.LOCATION,
            HiringKGEdgeType.LOCATED_IN, "persisted_source",
        )
        if enrichment is None:
            return
        if enrichment.business_unit:
            self._add_concept_edge(
                graph, job, evidence, enrichment, enrichment.business_unit,
                HiringKGNodeType.BUSINESS_UNIT, HiringKGEdgeType.BELONGS_TO,
                "latest_persisted_enrichment",
            )
        for capability in enrichment.capability_classifications:
            self._add_concept_edge(
                graph, job, evidence, enrichment, capability.value,
                HiringKGNodeType.CAPABILITY, HiringKGEdgeType.CLASSIFIED_AS,
                "latest_persisted_enrichment",
            )
        for technology in enrichment.technologies:
            self._add_concept_edge(
                graph, job, evidence, enrichment, technology,
                HiringKGNodeType.TECHNOLOGY, HiringKGEdgeType.USES_TECHNOLOGY,
                "latest_persisted_enrichment",
            )
        if enrichment.seniority_level != EnrichmentSeniority.UNKNOWN:
            self._add_concept_edge(
                graph, job, evidence, enrichment, enrichment.seniority_level.value,
                HiringKGNodeType.SENIORITY, HiringKGEdgeType.HAS_SENIORITY,
                "latest_persisted_enrichment",
            )

    def _add_concept_edge(
        self,
        graph: nx.MultiDiGraph,
        job: JobPosting,
        evidence: Evidence,
        enrichment: HiringEnrichmentResult | None,
        value: str,
        node_type: HiringKGNodeType,
        edge_type: HiringKGEdgeType,
        derivation_type: str,
    ) -> None:
        if not value.strip():
            return
        node_id = concept_node_id(node_type, job.organization, value)
        graph.add_node(
            node_id,
            node_type=node_type.value,
            organization=job.organization,
            value=value,
            label=value,
        )
        self._add_edge(
            graph,
            job_node_id(job.job_id),
            node_id,
            edge_type,
            self._provenance(job, evidence, derivation_type, enrichment),
        )

    def _add_signal(
        self,
        graph: nx.MultiDiGraph,
        org_id: str,
        generated: GeneratedHiringSignal,
        organization: str,
        company_evidence_ids: set[UUID],
    ) -> None:
        signal = generated.signal
        if signal.organization != organization:
            raise ValueError("company-scoped hiring graph received another organization's signal")
        if not set(signal.supporting_evidence_ids).issubset(company_evidence_ids):
            raise ValueError("hiring signal references evidence outside the company graph")
        node_id = signal_node_id(signal.signal_id)
        graph.add_node(
            node_id,
            node_type=HiringKGNodeType.HIRING_SIGNAL.value,
            organization=organization,
            signal_id=str(signal.signal_id),
            signal_type=signal.signal_type,
            label=generated.title,
            confidence=signal.confidence,
            strength=generated.score.strength,
        )
        self._add_edge(
            graph, org_id, node_id, HiringKGEdgeType.HAS_HIRING_SIGNAL,
            {"organization": organization, "derivation_type": "deterministic_hiring_signal"},
        )
        for supported_id in sorted(signal.supporting_evidence_ids, key=str):
            self._add_edge(
                graph, node_id, evidence_node_id(supported_id),
                HiringKGEdgeType.SUPPORTED_BY,
                {
                    "organization": organization,
                    "evidence_id": str(supported_id),
                    "derivation_type": "deterministic_hiring_signal",
                    "signal_id": str(signal.signal_id),
                    "signal_confidence": signal.confidence,
                    "signal_strength": generated.score.strength,
                },
            )
        self._connect_signal_capability(graph, node_id, generated, organization)

    @staticmethod
    def _connect_signal_capability(
        graph: nx.MultiDiGraph,
        signal_id: str,
        generated: GeneratedHiringSignal,
        organization: str,
    ) -> None:
        if generated.signal.signal_type != HiringSignalType.CAPABILITY_HIRING_CONCENTRATION:
            return
        prefix = "Observed hiring demand for "
        if not generated.title.startswith(prefix):
            return
        value = generated.title.removeprefix(prefix)
        target = concept_node_id(HiringKGNodeType.CAPABILITY, organization, value)
        if target not in graph:
            return
        HiringKnowledgeGraphService._add_edge(
            graph,
            signal_id,
            target,
            HiringKGEdgeType.ABOUT_CAPABILITY,
            {
                "organization": organization,
                "derivation_type": "deterministic_hiring_signal",
                "signal_id": generated.signal.signal_id.hex,
            },
        )

    @staticmethod
    def _provenance(
        job: JobPosting,
        evidence: Evidence,
        derivation_type: str,
        enrichment: HiringEnrichmentResult | None,
    ) -> dict:
        values = {
            "organization": job.organization,
            "job_id": str(job.job_id),
            "source_job_id": job.source_job_id,
            "evidence_id": str(evidence.evidence_id),
            "source_url": str(evidence.source_url),
            "derivation_type": derivation_type,
            "enrichment_provider": None,
            "enrichment_model": None,
            "prompt_schema_version": None,
            "enrichment_confidence": None,
            "source_content_hash": None,
        }
        if enrichment is not None:
            values.update(
                enrichment_provider=enrichment.model_metadata.provider,
                enrichment_model=enrichment.model_metadata.model,
                prompt_schema_version=enrichment.model_metadata.prompt_schema_version,
                enrichment_confidence=enrichment.confidence,
                source_content_hash=enrichment.source_content_hash,
            )
        return values

    @staticmethod
    def _add_edge(
        graph: nx.MultiDiGraph,
        source: str,
        target: str,
        edge_type: HiringKGEdgeType,
        attributes: dict,
    ) -> None:
        graph.add_edge(source, target, key=edge_type.value, edge_type=edge_type.value, **attributes)


def summarize_hiring_knowledge_graph(graph: nx.MultiDiGraph) -> HiringKnowledgeGraphSummary:
    node_counts = {node_type: 0 for node_type in HiringKGNodeType}
    edge_counts = {edge_type: 0 for edge_type in HiringKGEdgeType}
    for _, attributes in graph.nodes(data=True):
        node_counts[HiringKGNodeType(attributes["node_type"])] += 1
    for _, _, attributes in graph.edges(data=True):
        edge_counts[HiringKGEdgeType(attributes["edge_type"])] += 1
    return HiringKnowledgeGraphSummary(
        organization=graph.graph["organization"],
        node_count=graph.number_of_nodes(),
        edge_count=graph.number_of_edges(),
        node_counts=node_counts,
        edge_counts=edge_counts,
        jobs_read=graph.graph.get("jobs_read", 0),
        evidence_records_used=graph.graph.get("evidence_records_used", 0),
        enriched_jobs_used=graph.graph.get("enriched_jobs_used", 0),
        hiring_signals_used=graph.graph.get("hiring_signals_used", 0),
    )
