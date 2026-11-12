"""
Graph analysis algorithms for Human Risk Graph.

This module implements core graph algorithms used in HRG metrics:
- Articulation point detection (for bus factor)
- Critical path enumeration (for bypass risk)
- Graph connectivity analysis
"""

import networkx as nx
from typing import List, Set, Dict, Tuple


def find_articulation_points(graph: nx.DiGraph) -> Set[str]:
    """
    Find all articulation points (cut vertices) in the graph.

    An articulation point is a node whose removal would disconnect
    the graph or isolate critical nodes.

    Uses Tarjan's algorithm with time complexity O(|V| + |E|).

    Args:
        graph: NetworkX directed graph representing HRG

    Returns:
        Set of node IDs that are articulation points
    """
    # Convert to undirected for articulation point analysis
    undirected = graph.to_undirected()

    # Find articulation points using NetworkX
    articulation_points = set(nx.articulation_points(undirected))

    return articulation_points


def find_bridges(graph: nx.DiGraph) -> List[Tuple[str, str]]:
    """
    Find all bridges (cut edges) in the graph.

    A bridge is an edge whose removal would disconnect the graph.

    Args:
        graph: NetworkX directed graph

    Returns:
        List of edge tuples (u, v) that are bridges
    """
    undirected = graph.to_undirected()
    return list(nx.bridges(undirected))


def find_critical_paths(
    graph: nx.DiGraph, critical_nodes: Set[str], edge_types: Dict[Tuple[str, str], str]
) -> List[List[str]]:
    """
    Find all critical paths in the graph.

    A path is critical if:
    1. It starts or ends at a critical node
    2. It contains at least one approval edge

    Args:
        graph: NetworkX directed graph
        critical_nodes: Set of node IDs with high criticality
        edge_types: Dict mapping (u, v) -> edge type ('approval', 'bypass', etc)

    Returns:
        List of paths, where each path is a list of node IDs
    """
    critical_paths = []

    # For each critical node, find paths involving approval
    for source in critical_nodes:
        for target in graph.nodes():
            if source == target:
                continue

            # Find all simple paths between source and target
            try:
                paths = nx.all_simple_paths(graph, source, target, cutoff=5)

                for path in paths:
                    # Check if path contains approval edge
                    has_approval = False
                    for i in range(len(path) - 1):
                        edge = (path[i], path[i + 1])
                        if edge in edge_types and edge_types[edge] == "approval":
                            has_approval = True
                            break

                    if has_approval:
                        critical_paths.append(path)
            except nx.NetworkXNoPath:
                continue

    return critical_paths


def is_path_bypassable(
    path: List[str], graph: nx.DiGraph, edge_types: Dict[Tuple[str, str], str]
) -> bool:
    """
    Check if a critical path can be bypassed.

    A path is bypassable if there exists a bypass edge that creates
    a shortcut around any segment of the path.

    Args:
        path: List of node IDs forming a path
        graph: NetworkX directed graph
        edge_types: Dict mapping (u, v) -> edge type

    Returns:
        True if path can be bypassed, False otherwise
    """
    if len(path) < 2:
        return False

    # Check for bypass edges that shortcut the path
    for i in range(len(path)):
        for j in range(i + 2, len(path)):
            # Check if there's a direct bypass edge from path[i] to path[j]
            if graph.has_edge(path[i], path[j]):
                edge = (path[i], path[j])
                if edge in edge_types and edge_types[edge] == "bypass":
                    return True

            # Check if there's any bypass edge that connects to intermediate nodes
            for node in graph.nodes():
                if node not in path[i : j + 1]:
                    edge1 = (path[i], node)
                    edge2 = (node, path[j])

                    if (edge1 in edge_types and edge_types[edge1] == "bypass") or (
                        edge2 in edge_types and edge_types[edge2] == "bypass"
                    ):
                        if graph.has_edge(path[i], node) and graph.has_edge(node, path[j]):
                            return True

    return False


def compute_betweenness_centrality(graph: nx.DiGraph) -> Dict[str, float]:
    """
    Compute betweenness centrality for all nodes.

    Betweenness centrality measures how often a node appears on
    shortest paths between other nodes. High betweenness indicates
    a potential bottleneck.

    Args:
        graph: NetworkX directed graph

    Returns:
        Dict mapping node ID -> betweenness centrality score [0,1]
    """
    return nx.betweenness_centrality(graph)


def compute_degree_centrality(graph: nx.DiGraph) -> Dict[str, float]:
    """
    Compute degree centrality (both in-degree and out-degree).

    Args:
        graph: NetworkX directed graph

    Returns:
        Dict with 'in', 'out', and 'total' degree centrality per node
    """
    in_degree = dict(graph.in_degree())
    out_degree = dict(graph.out_degree())

    result = {}
    for node in graph.nodes():
        result[node] = {
            "in": in_degree.get(node, 0),
            "out": out_degree.get(node, 0),
            "total": in_degree.get(node, 0) + out_degree.get(node, 0),
        }

    return result


def find_strongly_connected_components(graph: nx.DiGraph) -> List[Set[str]]:
    """
    Find all strongly connected components.

    A strongly connected component is a maximal set of nodes where
    every node is reachable from every other node.

    Args:
        graph: NetworkX directed graph

    Returns:
        List of sets, where each set contains node IDs in a component
    """
    return [set(component) for component in nx.strongly_connected_components(graph)]


def compute_graph_density(graph: nx.DiGraph) -> float:
    """
    Compute the density of the graph.

    Density = |E| / (|V| * (|V| - 1))

    High density indicates many dependencies, low density indicates sparse connections.

    Args:
        graph: NetworkX directed graph

    Returns:
        Graph density as a float [0,1]
    """
    return nx.density(graph)
