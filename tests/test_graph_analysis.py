"""
Unit tests for graph analysis functions.
"""

import networkx as nx
from src.graph_analysis import (
    find_articulation_points,
    find_bridges,
    find_critical_paths,
    is_path_bypassable,
    compute_betweenness_centrality,
    compute_degree_centrality,
    find_strongly_connected_components,
    compute_graph_density,
)


class TestGraphAnalysis:
    def test_find_articulation_points_star(self):
        """Test articulation points in star graph."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("A", "C"), ("A", "D")])

        ap = find_articulation_points(graph)
        assert "A" in ap  # Center is articulation point

    def test_find_articulation_points_cycle(self):
        """Test no articulation points in cycle."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])

        ap = find_articulation_points(graph)
        assert len(ap) == 0  # No articulation points in cycle

    def test_betweenness_centrality(self):
        """Test betweenness centrality calculation."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "C")])

        bc = compute_betweenness_centrality(graph)

        assert "A" in bc
        assert "B" in bc
        assert "C" in bc
        # B should have higher betweenness (it's on path A->C)
        assert bc["B"] >= bc["A"]

    def test_graph_density_empty(self):
        """Test density of empty graph."""
        graph = nx.DiGraph()
        density = compute_graph_density(graph)
        assert density == 0.0

    def test_graph_density_complete(self):
        """Test density approaches 1 for complete graph."""
        graph = nx.DiGraph()
        # Complete directed graph on 3 nodes
        graph.add_edges_from(
            [("A", "B"), ("A", "C"), ("B", "A"), ("B", "C"), ("C", "A"), ("C", "B")]
        )

        density = compute_graph_density(graph)
        assert density == 1.0  # Complete graph

    def test_find_bridges(self):
        """Bridge detection should identify cut edges in chain-like topology."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "C")])

        bridges = find_bridges(graph)
        bridge_sets = {frozenset(edge) for edge in bridges}

        assert frozenset(("A", "B")) in bridge_sets
        assert frozenset(("B", "C")) in bridge_sets

    def test_find_critical_paths_requires_approval(self):
        """Critical path discovery should only include paths with approval edges."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "C"), ("A", "D")])
        edge_types = {
            ("A", "B"): "approval",
            ("B", "C"): "escalation",
            ("A", "D"): "escalation",
        }

        paths = find_critical_paths(graph, {"A"}, edge_types)

        assert ["A", "B"] in paths
        assert ["A", "B", "C"] in paths
        assert ["A", "D"] not in paths

    def test_is_path_bypassable_direct_edge(self):
        """Bypass shortcut directly on the path should be detected."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "C"), ("A", "C")])
        edge_types = {
            ("A", "B"): "approval",
            ("B", "C"): "approval",
            ("A", "C"): "bypass",
        }

        assert is_path_bypassable(["A", "B", "C"], graph, edge_types) is True

    def test_is_path_bypassable_via_intermediate_node(self):
        """Bypass through an off-path intermediate node should be detected."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "C"), ("A", "X"), ("X", "C")])
        edge_types = {
            ("A", "B"): "approval",
            ("B", "C"): "approval",
            ("A", "X"): "bypass",
            ("X", "C"): "escalation",
        }

        assert is_path_bypassable(["A", "B", "C"], graph, edge_types) is True

    def test_is_path_bypassable_false_and_short_path(self):
        """Non-bypassable path and short path edge case should return False."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "C")])
        edge_types = {
            ("A", "B"): "approval",
            ("B", "C"): "approval",
        }

        assert is_path_bypassable(["A", "B", "C"], graph, edge_types) is False
        assert is_path_bypassable(["A"], graph, edge_types) is False

    def test_compute_degree_centrality(self):
        """Degree centrality should return in/out/total counts per node."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("C", "B")])

        degree = compute_degree_centrality(graph)
        assert degree["B"]["in"] == 2
        assert degree["B"]["out"] == 0
        assert degree["B"]["total"] == 2

    def test_find_strongly_connected_components(self):
        """SCC detection should return strongly connected node groups."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "A"), ("C", "D")])

        components = find_strongly_connected_components(graph)
        component_sets = [frozenset(c) for c in components]

        assert frozenset(("A", "B")) in component_sets
