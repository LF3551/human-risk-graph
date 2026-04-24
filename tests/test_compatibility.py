"""
Python version compatibility tests for HRG.

Verifies that core functionality works correctly across Python 3.8-3.14,
including features and behaviors that may differ across versions.
"""

import sys
import importlib
import pytest
import networkx as nx
from src.hrg import HumanRiskGraph
from src.metrics import (
    bus_factor_score,
    decision_concentration_score,
    bypass_risk_score,
    composite_hrg_score,
    interpret_risk_level,
)
from src.graph_analysis import find_articulation_points


PYTHON_VERSION = sys.version_info[:2]


class TestPythonVersionInfo:
    """Verify we're running on a supported Python version."""

    def test_python_version_supported(self):
        """HRG supports Python 3.8 through 3.14."""
        assert PYTHON_VERSION >= (3, 8), f"Python {PYTHON_VERSION} is below minimum 3.8"

    def test_version_string_parseable(self):
        """sys.version should be parseable."""
        assert isinstance(sys.version, str)
        assert sys.version.startswith("3.")


class TestImportCompatibility:
    """Verify all modules import cleanly on the current Python version."""

    def test_import_hrg(self):
        mod = importlib.import_module("src.hrg")
        assert hasattr(mod, "HumanRiskGraph")

    def test_import_metrics(self):
        mod = importlib.import_module("src.metrics")
        assert hasattr(mod, "bus_factor_score")
        assert hasattr(mod, "composite_hrg_score")

    def test_import_graph_analysis(self):
        mod = importlib.import_module("src.graph_analysis")
        assert hasattr(mod, "find_articulation_points")

    def test_import_package(self):
        import src
        assert hasattr(src, "__version__")
        assert hasattr(src, "HumanRiskGraph")


class TestTypeHintCompatibility:
    """Test that type annotations and runtime type behavior work across versions."""

    def test_dict_union_in_results(self):
        """Verify calculate() returns a proper dict on all Python versions."""
        people = [
            {"id": "A", "role": "SRE", "criticality": 0.9},
            {"id": "B", "role": "Engineer", "criticality": 0.5},
        ]
        deps = [{"from": "A", "to": "B", "type": "approval", "weight": 0.8}]
        hrg = HumanRiskGraph(people, deps)
        result = hrg.calculate()
        assert isinstance(result, dict)
        for key in ("bus_factor", "decision_concentration", "bypass_risk", "composite_score"):
            assert isinstance(result[key], float)

    def test_list_and_set_results(self):
        """Verify collection types in results are consistent."""
        people = [
            {"id": "A", "role": "SRE", "criticality": 0.9},
            {"id": "B", "role": "Engineer", "criticality": 0.5},
            {"id": "C", "role": "Dev", "criticality": 0.3},
        ]
        deps = [
            {"from": "A", "to": "B", "type": "approval", "weight": 0.8},
            {"from": "A", "to": "C", "type": "bypass", "weight": 0.7},
        ]
        hrg = HumanRiskGraph(people, deps)
        result = hrg.calculate()
        assert isinstance(result["articulation_points"], (list, set))


class TestNetworkXCompatibility:
    """Test that NetworkX operations work on the current Python + NetworkX combination."""

    def test_digraph_creation(self):
        G = nx.DiGraph()
        G.add_node("A", criticality=0.9)
        G.add_node("B", criticality=0.5)
        G.add_edge("A", "B", weight=0.8, type="approval")
        assert G.number_of_nodes() == 2
        assert G.number_of_edges() == 1

    def test_articulation_points_on_undirected(self):
        G = nx.Graph()
        G.add_edges_from([("A", "B"), ("B", "C"), ("C", "D")])
        aps = list(nx.articulation_points(G))
        assert "B" in aps
        assert "C" in aps

    def test_graph_algorithms(self):
        """Core graph algorithms should work consistently."""
        G = nx.DiGraph()
        G.add_edges_from([("A", "B"), ("B", "C"), ("A", "C")])
        assert nx.is_weakly_connected(G)
        components = list(nx.weakly_connected_components(G))
        assert len(components) == 1


class TestNumericConsistency:
    """Verify floating-point and numeric operations are consistent across versions."""

    def test_metric_ranges(self):
        """All metrics should be in [0, 1] regardless of Python version."""
        people = [
            {"id": "A", "role": "SRE", "criticality": 0.95},
            {"id": "B", "role": "Engineer", "criticality": 0.8},
            {"id": "C", "role": "Manager", "criticality": 0.7},
            {"id": "D", "role": "Dev", "criticality": 0.4},
        ]
        deps = [
            {"from": "A", "to": "B", "type": "approval", "weight": 0.9},
            {"from": "C", "to": "A", "type": "bypass", "weight": 0.85},
            {"from": "B", "to": "D", "type": "escalation", "weight": 0.6},
        ]
        hrg = HumanRiskGraph(people, deps)
        result = hrg.calculate()

        assert 0.0 <= result["bus_factor"] <= 1.0
        assert 0.0 <= result["decision_concentration"] <= 1.0
        assert 0.0 <= result["bypass_risk"] <= 1.0
        assert 0.0 <= result["composite_score"] <= 1.0

    def test_interpret_risk_level_values(self):
        """Risk level interpretation should be consistent."""
        assert interpret_risk_level(0.0) in ("Low", "Medium", "High", "Critical")
        assert interpret_risk_level(0.5) in ("Low", "Medium", "High", "Critical")
        assert interpret_risk_level(1.0) in ("Low", "Medium", "High", "Critical")

    def test_composite_score_deterministic(self):
        """Same input should produce same output on any Python version."""
        people = [
            {"id": "A", "role": "SRE", "criticality": 0.9},
            {"id": "B", "role": "Engineer", "criticality": 0.5},
        ]
        deps = [{"from": "A", "to": "B", "type": "approval", "weight": 0.8}]

        results = []
        for _ in range(5):
            hrg = HumanRiskGraph(people, deps)
            results.append(hrg.calculate()["composite_score"])

        assert all(r == results[0] for r in results), "Composite score is not deterministic"


class TestEndToEndCompatibility:
    """Full pipeline test across Python versions."""

    def test_full_analysis_pipeline(self):
        """Run the complete HRG pipeline and verify outputs."""
        people = [
            {"id": "alice", "role": "CISO", "criticality": 0.95},
            {"id": "bob", "role": "SRE Lead", "criticality": 0.85},
            {"id": "carol", "role": "Security Engineer", "criticality": 0.7},
            {"id": "dave", "role": "Developer", "criticality": 0.5},
            {"id": "eve", "role": "Junior Dev", "criticality": 0.3},
        ]
        deps = [
            {"from": "alice", "to": "bob", "type": "approval", "weight": 0.9},
            {"from": "alice", "to": "carol", "type": "approval", "weight": 0.8},
            {"from": "bob", "to": "dave", "type": "bypass", "weight": 0.7},
            {"from": "carol", "to": "dave", "type": "escalation", "weight": 0.6},
            {"from": "dave", "to": "eve", "type": "approval", "weight": 0.5},
        ]

        hrg = HumanRiskGraph(people, deps)
        result = hrg.calculate()

        # All expected keys present
        expected_keys = {
            "bus_factor",
            "decision_concentration",
            "bypass_risk",
            "composite_score",
            "risk_level",
            "critical_nodes",
            "articulation_points",
        }
        assert expected_keys.issubset(set(result.keys()))

        # Risk level is a valid string
        assert result["risk_level"] in ("Low", "Medium", "High", "Critical")

        # Node analysis works
        node_analysis = hrg.analyze_node("alice")
        assert isinstance(node_analysis, dict)
