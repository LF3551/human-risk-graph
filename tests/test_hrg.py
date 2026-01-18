"""
Unit tests for HumanRiskGraph class.
"""

import pytest
from src.hrg import HumanRiskGraph


class TestHumanRiskGraph:
    def test_initialization(self):
        """Test basic HRG initialization."""
        people = [
            {"id": "A", "role": "SRE", "criticality": 0.9},
            {"id": "B", "role": "Security Engineer", "criticality": 0.8},
        ]
        dependencies = [{"from": "A", "to": "B", "type": "approval", "weight": 0.8}]

        hrg = HumanRiskGraph(people, dependencies)
        assert len(hrg.graph.nodes()) == 2
        assert len(hrg.graph.edges()) == 1

    def test_calculate_returns_all_metrics(self):
        """Test that calculate() returns all expected metrics."""
        people = [
            {"id": "A", "role": "SRE", "criticality": 0.9},
            {"id": "B", "role": "Engineer", "criticality": 0.5},
        ]
        dependencies = [{"from": "A", "to": "B", "type": "approval", "weight": 0.8}]

        hrg = HumanRiskGraph(people, dependencies)
        result = hrg.calculate()

        assert "bus_factor" in result
        assert "decision_concentration" in result
        assert "bypass_risk" in result
        assert "composite_score" in result
        assert "risk_level" in result
        assert "critical_nodes" in result
        assert "articulation_points" in result

    def test_analyze_node(self):
        """Test node analysis."""
        people = [
            {"id": "A", "role": "SRE", "criticality": 0.9},
            {"id": "B", "role": "Engineer", "criticality": 0.5},
        ]
        dependencies = [{"from": "A", "to": "B", "type": "approval", "weight": 0.8}]

        hrg = HumanRiskGraph(people, dependencies)
        analysis = hrg.analyze_node("A")

        assert "criticality" in analysis
        assert analysis["criticality"] == 0.9
        assert "is_articulation_point" in analysis
        assert "betweenness_centrality" in analysis

    def test_analyze_invalid_node(self):
        """Test that analyzing invalid node raises error."""
        people = [{"id": "A", "role": "SRE", "criticality": 0.9}]
        dependencies = []

        hrg = HumanRiskGraph(people, dependencies)

        with pytest.raises(ValueError):
            hrg.analyze_node("Z")

    def test_simulate_node_removal(self):
        """Test node removal simulation."""
        people = [
            {"id": "A", "role": "SRE", "criticality": 0.9},
            {"id": "B", "role": "Engineer", "criticality": 0.7},
            {"id": "C", "role": "Manager", "criticality": 0.6},
        ]
        dependencies = [
            {"from": "A", "to": "B", "type": "approval", "weight": 0.8},
            {"from": "B", "to": "C", "type": "escalation", "weight": 0.7},
        ]

        hrg = HumanRiskGraph(people, dependencies)
        impact = hrg.simulate_node_removal("B")

        assert "original_score" in impact
        assert "new_score" in impact
        assert "score_change" in impact
        assert "disconnected_nodes" in impact

    def test_get_critical_dependencies(self):
        """Test identification of critical dependencies."""
        people = [
            {"id": "A", "role": "SRE", "criticality": 0.9},
            {"id": "B", "role": "Engineer", "criticality": 0.5},
        ]
        dependencies = [{"from": "A", "to": "B", "type": "approval", "weight": 0.8}]

        hrg = HumanRiskGraph(people, dependencies)
        critical_deps = hrg.get_critical_dependencies()

        # A is critical (0.9 >= 0.7), so this edge should be critical
        assert len(critical_deps) > 0
