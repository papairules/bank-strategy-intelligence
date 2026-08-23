from pathlib import Path

import networkx as nx

from backend.app.application.hiring.kg import graph_file_path, load_graph, save_graph
from backend.app.application.hiring.kg.models import HiringKGEdgeType, HiringKGNodeType


def sample_graph(organization: str = "Wells Fargo") -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(organization=organization)
    graph.add_node(
        "org:wells_fargo",
        node_type=HiringKGNodeType.ORGANIZATION.value,
        organization=organization,
        label=organization,
    )
    graph.add_node(
        "job:1",
        node_type=HiringKGNodeType.JOB.value,
        organization=organization,
        label="Platform Engineer",
    )
    graph.add_edge(
        "org:wells_fargo",
        "job:1",
        key=HiringKGEdgeType.HAS_JOB.value,
        edge_type=HiringKGEdgeType.HAS_JOB.value,
        organization=organization,
    )
    return graph


def test_graph_file_path_is_organization_scoped(tmp_path: Path):
    wells = graph_file_path(tmp_path, "Wells Fargo")
    bny = graph_file_path(tmp_path, "BNY")

    assert wells == tmp_path / "wells_fargo.json"
    assert bny == tmp_path / "bny.json"


def test_load_graph_returns_none_when_missing(tmp_path: Path):
    assert load_graph(tmp_path / "missing.json") is None


def test_save_and_load_graph_round_trips_nodes_and_edges(tmp_path: Path):
    graph = sample_graph()
    path = graph_file_path(tmp_path, "Wells Fargo")

    save_graph(graph, path)
    loaded = load_graph(path)

    assert isinstance(loaded, nx.MultiDiGraph)
    assert loaded.is_directed()
    assert loaded.is_multigraph()
    assert set(loaded.nodes) == set(graph.nodes)
    assert set(loaded.edges(keys=True)) == set(graph.edges(keys=True))
    assert loaded.graph["organization"] == "Wells Fargo"
    assert loaded.nodes["job:1"]["label"] == "Platform Engineer"


def test_save_graph_overwrites_existing_file_atomically(tmp_path: Path):
    path = graph_file_path(tmp_path, "Wells Fargo")
    save_graph(sample_graph(), path)
    save_graph(nx.MultiDiGraph(organization="Wells Fargo"), path)

    loaded = load_graph(path)
    assert loaded.number_of_nodes() == 0
    assert not (path.with_suffix(path.suffix + ".tmp")).exists()
