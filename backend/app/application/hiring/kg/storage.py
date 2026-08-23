import json
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from backend.app.domain.organization import organization_key


def graph_file_path(directory: Path, organization: str) -> Path:
    return Path(directory) / f"{organization_key(organization)}.json"


def save_graph(graph: nx.MultiDiGraph, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json_graph.node_link_data(graph, edges="edges")
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def load_graph(path: Path) -> nx.MultiDiGraph | None:
    path = Path(path)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return json_graph.node_link_graph(data, edges="edges", multigraph=True, directed=True)
