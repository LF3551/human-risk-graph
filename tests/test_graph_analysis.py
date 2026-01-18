"""
Unit tests for graph analysis functions.
"""

import networkx as nx
from src.graph_analysis import (
    find_articulation_points,
    compute_betweenness_centrality,
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
