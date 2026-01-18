"""
Unit tests for HRG metrics.
"""

import pytest
import networkx as nx
from src.metrics import (
    bus_factor_score,
    decision_concentration_score,
    bypass_risk_score,
    composite_hrg_score,
    interpret_risk_level,
)


class TestBusFactorScore:
    def test_empty_graph(self):
        """Bus factor should be 0 for empty graph."""
        graph = nx.DiGraph()
        criticality = {}
        assert bus_factor_score(graph, criticality) == 0.0

    def test_no_articulation_points(self):
        """Bus factor should be 0 when no articulation points exist."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "A")])  # Cycle, no articulation points
        criticality = {"A": 0.8, "B": 0.7}

        # In a strongly connected graph with >2 nodes or a cycle, no articulation points
        assert bus_factor_score(graph, criticality) == 0.0

    def test_star_graph(self):
        """Star graph center should be articulation point."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("A", "C"), ("A", "D")])
        criticality = {"A": 0.9, "B": 0.5, "C": 0.5, "D": 0.5}

        score = bus_factor_score(graph, criticality)
        assert score > 0.0  # Center A is articulation point


class TestDecisionConcentrationScore:
    def test_no_approvals(self):
        """DC should be 0 when no approval edges exist."""
        graph = nx.DiGraph()
        graph.add_edge("A", "B")
        edge_types = {("A", "B"): "escalation"}
        weights = {("A", "B"): 0.5}

        assert decision_concentration_score(graph, edge_types, weights) == 0.0

    def test_single_approval(self):
        """DC with single approval should be 0 (no inequality)."""
        graph = nx.DiGraph()
        graph.add_edge("A", "B")
        edge_types = {("A", "B"): "approval"}
        weights = {("A", "B"): 0.8}

        score = decision_concentration_score(graph, edge_types, weights)
        assert score == 0.0  # Single entity, no inequality

    def test_equal_distribution(self):
        """Equal approval distribution should have low DC."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "C"), ("B", "D")])
        edge_types = {("A", "C"): "approval", ("B", "D"): "approval"}
        weights = {("A", "C"): 0.5, ("B", "D"): 0.5}

        score = decision_concentration_score(graph, edge_types, weights)
        assert 0.0 <= score <= 0.1  # Nearly equal distribution


class TestBypassRiskScore:
    def test_no_bypasses(self):
        """BR should be 0 when no bypass edges exist."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B"), ("B", "C")])
        criticality = {"A": 0.9, "B": 0.7, "C": 0.6}
        edge_types = {("A", "B"): "approval", ("B", "C"): "approval"}

        score = bypass_risk_score(graph, criticality, edge_types)
        assert score == 0.0

    def test_no_critical_nodes(self):
        """BR should be 0 when no nodes are critical."""
        graph = nx.DiGraph()
        graph.add_edges_from([("A", "B")])
        criticality = {"A": 0.3, "B": 0.4}  # Below threshold
        edge_types = {("A", "B"): "bypass"}

        score = bypass_risk_score(graph, criticality, edge_types, critical_threshold=0.7)
        assert score == 0.0


class TestCompositeScore:
    def test_weights_sum_to_one(self):
        """Weights must sum to 1."""
        with pytest.raises(ValueError):
            composite_hrg_score(0.5, 0.5, 0.5, alpha=0.5, beta=0.5, gamma=0.5)

    def test_valid_composite(self):
        """Valid composite score calculation."""
        score = composite_hrg_score(0.6, 0.4, 0.2, alpha=0.4, beta=0.3, gamma=0.3)
        expected = 0.4 * 0.6 + 0.3 * 0.4 + 0.3 * 0.2
        assert abs(score - expected) < 1e-10


class TestRiskInterpretation:
    def test_low_risk(self):
        assert interpret_risk_level(0.2) == "Low"

    def test_moderate_risk(self):
        assert interpret_risk_level(0.4) == "Moderate"

    def test_high_risk(self):
        assert interpret_risk_level(0.6) == "High"

    def test_critical_risk(self):
        assert interpret_risk_level(0.8) == "Critical"
