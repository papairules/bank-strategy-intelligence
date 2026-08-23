from uuid import UUID

import networkx as nx

from .builder import concept_node_id, evidence_node_id, job_node_id, signal_node_id
from .models import HiringKGEdgeType, HiringKGNodeType


def get_strategic_themes_for_organization(graph: nx.MultiDiGraph) -> list[str]:
    return _organization_concepts(graph, HiringKGNodeType.STRATEGIC_THEME)


def get_evidence_for_strategic_theme(graph: nx.MultiDiGraph, theme: str) -> list[str]:
    target = concept_node_id(HiringKGNodeType.STRATEGIC_THEME, graph.graph["organization"], theme)
    if target not in graph:
        return []
    return sorted(
        graph.nodes[node]["evidence_id"]
        for _, node, attributes in graph.out_edges(target, data=True)
        if attributes.get("edge_type") == HiringKGEdgeType.SUPPORTED_BY.value
        and graph.nodes[node].get("node_type") == HiringKGNodeType.STRATEGY_EVIDENCE.value
    )


def _job_ids_for_concept(
    graph: nx.MultiDiGraph,
    node_type: HiringKGNodeType,
    value: str,
    edge_type: HiringKGEdgeType,
) -> list[UUID]:
    target = concept_node_id(node_type, graph.graph["organization"], value)
    if target not in graph:
        return []
    values = {
        UUID(graph.nodes[source]["job_id"])
        for source, _, attributes in graph.in_edges(target, data=True)
        if attributes.get("edge_type") == edge_type.value
        and graph.nodes[source].get("node_type") == HiringKGNodeType.JOB.value
    }
    return sorted(values, key=str)


def get_jobs_for_capability(graph: nx.MultiDiGraph, capability: str) -> list[UUID]:
    return _job_ids_for_concept(
        graph, HiringKGNodeType.CAPABILITY, capability, HiringKGEdgeType.CLASSIFIED_AS
    )


def get_jobs_for_technology(graph: nx.MultiDiGraph, technology: str) -> list[UUID]:
    return _job_ids_for_concept(
        graph, HiringKGNodeType.TECHNOLOGY, technology, HiringKGEdgeType.USES_TECHNOLOGY
    )


def _organization_concepts(graph: nx.MultiDiGraph, node_type: HiringKGNodeType) -> list[str]:
    return sorted(
        {
            attributes["value"]
            for _, attributes in graph.nodes(data=True)
            if attributes.get("node_type") == node_type.value
        },
        key=str.casefold,
    )


def get_capabilities_for_organization(graph: nx.MultiDiGraph) -> list[str]:
    return _organization_concepts(graph, HiringKGNodeType.CAPABILITY)


def get_technologies_for_organization(graph: nx.MultiDiGraph) -> list[str]:
    return _organization_concepts(graph, HiringKGNodeType.TECHNOLOGY)


def get_business_units_for_organization(graph: nx.MultiDiGraph) -> list[str]:
    return _organization_concepts(graph, HiringKGNodeType.BUSINESS_UNIT)


def get_evidence_for_job(graph: nx.MultiDiGraph, job_id: UUID | str) -> list[UUID]:
    source = job_node_id(job_id)
    if source not in graph:
        return []
    values = {
        UUID(graph.nodes[target]["evidence_id"])
        for _, target, attributes in graph.out_edges(source, data=True)
        if attributes.get("edge_type") == HiringKGEdgeType.SUPPORTED_BY.value
    }
    return sorted(values, key=str)


def get_jobs_supporting_hiring_signal(
    graph: nx.MultiDiGraph, signal_id: UUID | str
) -> list[UUID]:
    source = signal_node_id(signal_id)
    if source not in graph:
        return []
    evidence_nodes = {
        target
        for _, target, attributes in graph.out_edges(source, data=True)
        if attributes.get("edge_type") == HiringKGEdgeType.SUPPORTED_BY.value
    }
    jobs: set[UUID] = set()
    for evidence in evidence_nodes:
        for candidate, _, attributes in graph.in_edges(evidence, data=True):
            if (
                attributes.get("edge_type") == HiringKGEdgeType.SUPPORTED_BY.value
                and graph.nodes[candidate].get("node_type") == HiringKGNodeType.JOB.value
            ):
                jobs.add(UUID(graph.nodes[candidate]["job_id"]))
    return sorted(jobs, key=str)
