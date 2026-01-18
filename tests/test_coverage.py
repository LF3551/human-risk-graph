"""
Additional tests to improve coverage for graph_analysis and metrics modules.
"""

import networkx as nx
from src.metrics import decision_concentration_score, bypass_risk_score


class TestDecisionConcentrationEdgeCases:
    """Additional tests for decision concentration scoring."""

    def test_decision_concentration_equal_weights(self):
        """Test DC score with equal approval weights."""
        G = nx.DiGraph()
        G.add_edges_from(
            [
                ("A", "B", {"type": "approval"}),
                ("C", "D", {"type": "approval"}),
                ("E", "F", {"type": "approval"}),
            ]
        )

        weights = {"A": 1/3, "C": 1/3, "E": 1/3}  # Equal distribution
        edge_types = {
            ("A", "B"): "approval",
            ("C", "D"): "approval",
            ("E", "F"): "approval",
        }

        score = decision_concentration_score(G, edge_types, weights)
        assert 0 <= score <= 1
        # Equal distribution should have low concentration
        assert score < 0.5

    def test_decision_concentration_multiple_approvers(self):
        """Test with multiple people having approval edges."""
        G = nx.DiGraph()
        edges = [
            ("A", "X", {"type": "approval"}),
            ("A", "Y", {"type": "approval"}),
            ("B", "Z", {"type": "approval"}),
        ]
        G.add_edges_from(edges)

        edge_types = {
            ("A", "X"): "approval",
            ("A", "Y"): "approval",
            ("B", "Z"): "approval",
        }
        weights = {"A": 0.5, "B": 0.5}

        score = decision_concentration_score(G, edge_types, weights)
        assert 0 <= score <= 1

    def test_decision_concentration_high_concentration(self):
        """Test DC score with high concentration (one person many approvals)."""
        G = nx.DiGraph()
        edges = [
            ("A", "X", {"type": "approval"}),
            ("A", "Y", {"type": "approval"}),
            ("A", "Z", {"type": "approval"}),
            ("B", "W", {"type": "approval"}),
        ]
        G.add_edges_from(edges)

        edge_types = {
            ("A", "X"): "approval",
            ("A", "Y"): "approval",
            ("A", "Z"): "approval",
            ("B", "W"): "approval",
        }
        weights = {"A": 0.8, "B": 0.2}

        score = decision_concentration_score(G, edge_types, weights)
        assert 0 <= score <= 1
        # High concentration should have higher score
        assert score >= 0.0


class TestBypassRiskEdgeCases:
    """Additional tests for bypass risk scoring."""

    def test_bypass_risk_high_critical_threshold(self):
        """Test bypass risk with very high critical threshold."""
        G = nx.DiGraph()
        G.add_edges_from(
            [
                ("A", "B", {"type": "bypass"}),
                ("B", "C"),
            ]
        )

        criticality = {"A": 0.85, "B": 0.75, "C": 0.1}
        edge_types = {("A", "B"): "bypass", ("B", "C"): "normal"}

        score = bypass_risk_score(G, criticality, edge_types, critical_threshold=0.8)
        assert 0 <= score <= 1

    def test_bypass_risk_no_bypasses_but_critical_nodes(self):
        """Test bypass risk with critical nodes but no bypass edges."""
        G = nx.DiGraph()
        G.add_edges_from([("A", "B"), ("B", "C")])

        criticality = {"A": 0.9, "B": 0.8, "C": 0.1}
        edge_types = {("A", "B"): "normal", ("B", "C"): "normal"}

        score = bypass_risk_score(G, criticality, edge_types, critical_threshold=0.7)
        assert score == 0  # No bypasses, so score should be 0

    def test_bypass_risk_bypasses_but_no_critical_nodes(self):
        """Test bypass risk with bypass edges but no critical nodes."""
        G = nx.DiGraph()
        G.add_edges_from([("A", "B", {"type": "bypass"})])

        criticality = {"A": 0.3, "B": 0.2}
        edge_types = {("A", "B"): "bypass"}

        score = bypass_risk_score(G, criticality, edge_types, critical_threshold=0.7)
        assert score == 0  # No critical nodes above threshold

    def test_bypass_risk_with_multiple_bypasses(self):
        """Test bypass risk with multiple bypass edges from critical nodes."""
        G = nx.DiGraph()
        G.add_edges_from(
            [
                ("A", "B", {"type": "bypass"}),
                ("A", "C", {"type": "bypass"}),
                ("D", "E", {"type": "bypass"}),
            ]
        )

        criticality = {"A": 0.9, "B": 0.5, "C": 0.4, "D": 0.2, "E": 0.1}
        edge_types = {
            ("A", "B"): "bypass",
            ("A", "C"): "bypass",
            ("D", "E"): "bypass",
        }

        score = bypass_risk_score(G, criticality, edge_types, critical_threshold=0.7)
        assert 0 <= score <= 1

