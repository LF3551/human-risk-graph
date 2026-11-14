"""
Human Risk Graph - Main interface class.

This module provides the primary API for building and analyzing
Human Risk Graphs.
"""

import networkx as nx
import numpy as np
from typing import Dict, List, Optional, Set, Tuple
from .metrics import (
    bus_factor_score,
    decision_concentration_score,
    bypass_risk_score,
    composite_hrg_score,
    interpret_risk_level,
)
from .graph_analysis import (
    find_articulation_points,
    compute_betweenness_centrality,
)
from .activity import parse_activity
from .model_v2 import (
    MODEL_V1,
    MODEL_V2,
    MODEL_V3,
    MODELS,
    calculate_v2,
    risk_level_from_score,
    score_and_grade,
)
from .model_v3 import SEPARATION_REQUIRED, SEPARATION_VALUES, calculate_v3, fix_plan_v3

REVIEW_VALUES = ("none", "after")


def _check_unit_interval(value, where: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"{where} must be a number between 0 and 1, got {value!r}")


def _validate(people, dependencies) -> None:
    if not isinstance(people, list) or not isinstance(dependencies, list):
        raise ValueError("'people' and 'dependencies' must be lists")
    ids: Set[str] = set()
    for i, person in enumerate(people):
        _validate_person(person, i, ids)
        ids.add(person["id"])
    for i, dep in enumerate(dependencies):
        _validate_dependency(dep, i, ids)


def _validate_person(person, i: int, ids: Set[str]) -> None:
    if not isinstance(person, dict) or "id" not in person:
        raise ValueError(f"people[{i}] must be an object with an 'id'")
    if not isinstance(person["id"], str) or not person["id"]:
        raise ValueError(f"people[{i}].id must be a non-empty string, got {person['id']!r}")
    if person["id"] in ids:
        raise ValueError(f"people[{i}]: duplicate id {person['id']!r}")
    if "criticality" in person:
        _check_unit_interval(person["criticality"], f"people[{i}].criticality")
    try:
        parse_activity(person.get("last_active"))
    except ValueError as e:
        raise ValueError(f"people[{i}].last_active {e}") from None


def _validate_dependency(dep, i: int, ids: Set[str]) -> None:
    if not isinstance(dep, dict) or "from" not in dep or "to" not in dep:
        raise ValueError(f"dependencies[{i}] must be an object with 'from' and 'to'")
    for end in ("from", "to"):
        if dep[end] not in ids:
            raise ValueError(f"dependencies[{i}].{end}: unknown person id {dep[end]!r}")
    if "weight" in dep:
        _check_unit_interval(dep["weight"], f"dependencies[{i}].weight")
    if dep.get("review", "none") not in REVIEW_VALUES:
        raise ValueError(
            f"dependencies[{i}].review must be one of {', '.join(REVIEW_VALUES)}, "
            f"got {dep['review']!r}"
        )


def _validate_functions(functions, ids) -> None:
    if not isinstance(functions, list):
        raise ValueError("'functions' must be a list")
    seen: Set[str] = set()
    for i, f in enumerate(functions):
        where = f"functions[{i}]"
        if not isinstance(f, dict) or not isinstance(f.get("id"), str) or not f["id"]:
            raise ValueError(f"{where} must be an object with a non-empty string 'id'")
        if f["id"] in seen:
            raise ValueError(f"{where}: duplicate function id {f['id']!r}")
        seen.add(f["id"])
        _validate_function_settings(f, where)
        for key in ("performers", "alone"):
            _validate_members(f.get(key) or [], f"{where}.{key}", ids)


def _validate_function_settings(f, where: str) -> None:
    if "criticality" in f:
        _check_unit_interval(f["criticality"], f"{where}.criticality")
    requires = f.get("requires", 1)
    if isinstance(requires, bool) or not isinstance(requires, int) or requires < 1:
        raise ValueError(f"{where}.requires must be a whole number of at least 1")
    if f.get("separation", SEPARATION_REQUIRED) not in SEPARATION_VALUES:
        raise ValueError(f"{where}.separation must be one of {', '.join(SEPARATION_VALUES)}")


def _validate_members(members, where: str, ids) -> None:
    if not isinstance(members, list):
        raise ValueError(f"{where} must be a list of person ids")
    for member in members:
        if member not in ids:
            raise ValueError(f"{where}: unknown person id {member!r}")


class HumanRiskGraph:
    """
    Main class for Human Risk Graph analysis.

    A HRG represents organizational security risk through a directed
    graph where nodes are people and edges are dependency relationships.

    Example:
        >>> people = [
        ...     {"id": "A", "role": "SRE", "criticality": 0.9},
        ...     {"id": "B", "role": "Security Engineer", "criticality": 0.8}
        ... ]
        >>> dependencies = [
        ...     {"from": "A", "to": "B", "type": "approval", "weight": 0.8}
        ... ]
        >>> hrg = HumanRiskGraph(people, dependencies)
        >>> scores = hrg.calculate()
    """

    def __init__(
        self, people: List[Dict], dependencies: List[Dict], functions: Optional[List[Dict]] = None
    ):
        """
        Initialize a Human Risk Graph.

        Args:
            people: List of person dicts with keys:
                - id: unique identifier (str)
                - role: job role (str)
                - criticality: importance score [0,1] (float)
            dependencies: List of dependency dicts with keys:
                - from: source person ID (str)
                - to: target person ID (str)
                - type: 'approval', 'escalation', or 'bypass' (str)
                - weight: dependency strength [0,1] (float)
            functions: Optional critical functions for model hrg-3, each with id,
                criticality, requires, performers and alone.

        Raises:
            ValueError: If the input is malformed, for example a duplicate or unknown
                person ID, or a criticality or weight outside [0, 1].
        """
        _validate(people, dependencies)
        self.functions = functions or []
        _validate_functions(self.functions, {p["id"] for p in people})
        self.people = people
        self.dependencies = dependencies

        # Build NetworkX graph
        self.graph = nx.DiGraph()

        # Add nodes with attributes
        for person in people:
            self.graph.add_node(
                person["id"],
                role=person.get("role", "Unknown"),
                criticality=person.get("criticality", 0.5),
            )

        # Add edges with attributes
        for dep in dependencies:
            self.graph.add_edge(
                dep["from"],
                dep["to"],
                edge_type=dep.get("type", "unknown"),
                type=dep.get("type", "unknown"),
                weight=dep.get("weight", 0.5),
            )

        # Build lookup dictionaries for efficient access
        self.criticality = {p["id"]: p.get("criticality", 0.5) for p in people}
        self.edge_types = {
            (dep["from"], dep["to"]): dep.get("type", "unknown") for dep in dependencies
        }
        self.weights = {(dep["from"], dep["to"]): dep.get("weight", 0.5) for dep in dependencies}
        # Break-glass bypasses: every use is reviewed afterwards.
        self.reviewed_bypasses = {
            (dep["from"], dep["to"])
            for dep in dependencies
            if dep.get("type") == "bypass" and dep.get("review") == "after"
        }

    def calculate(
        self,
        alpha: float = 0.4,
        beta: float = 0.3,
        gamma: float = 0.3,
        critical_threshold: float = 0.7,
        model: str = MODEL_V2,
        with_bus_factor: bool = True,
    ) -> Dict:
        """
        Calculate all HRG risk metrics.

        Args:
            alpha: Weight for bus factor / key-person risk (default 0.4)
            beta: Weight for decision concentration (default 0.3)
            gamma: Weight for bypass risk / override exposure (default 0.3)
            critical_threshold: Minimum criticality for critical nodes (default 0.7)
            model: "hrg-2" (default) or "hrg-1", the original model from the paper
            with_bus_factor: Compute ``bus_factor_people`` (hrg-2 only; the slowest part)

        Returns:
            Dict containing at least:
                - model: model identifier
                - bus_factor, decision_concentration, bypass_risk: metrics in [0,1]
                - composite_score: overall risk in [0,1]
                - score: 0-100, higher is better; grade: A-F
                - risk_level: 'Low', 'Moderate', 'High', or 'Critical'
                - critical_nodes: List of critical node IDs
                - articulation_points: List of articulation point IDs
            hrg-2 adds key_people, bus_factor_people, approval_shares,
            effective_approvers, critical_approvals and overridable_approvals.
        """
        if model not in MODELS:
            raise ValueError(f"Unknown model {model!r}; expected one of {', '.join(MODELS)}")

        if model == MODEL_V3:
            if not np.isclose(alpha + beta + gamma, 1.0):
                raise ValueError("Weights must sum to 1.0")
            if not self.functions:
                raise ValueError("Model hrg-3 needs a 'functions' section in the organization")
            result = calculate_v3(
                self.functions, self.criticality, alpha, beta, gamma, critical_threshold
            )
            result["risk_level"] = risk_level_from_score(result["score"])
            return result

        if model == MODEL_V2:
            if not np.isclose(alpha + beta + gamma, 1.0):
                raise ValueError("Weights must sum to 1.0")
            result = calculate_v2(
                self.graph,
                self.criticality,
                self.edge_types,
                self.weights,
                alpha,
                beta,
                gamma,
                critical_threshold,
                with_bus_factor,
                self.reviewed_bypasses,
            )
            result["risk_level"] = risk_level_from_score(result["score"])
            return result

        return self._calculate_v1(alpha, beta, gamma, critical_threshold)

    def _calculate_v1(
        self, alpha: float, beta: float, gamma: float, critical_threshold: float
    ) -> Dict:
        # Calculate individual metrics
        bf = bus_factor_score(self.graph, self.criticality, critical_threshold)
        dc = decision_concentration_score(self.graph, self.edge_types, self.weights)
        br = bypass_risk_score(self.graph, self.criticality, self.edge_types, critical_threshold)

        # Calculate composite score
        composite = composite_hrg_score(bf, dc, br, alpha, beta, gamma)

        # Identify critical nodes
        critical_nodes = [
            node for node, crit in self.criticality.items() if crit >= critical_threshold
        ]

        # Find articulation points
        articulation_pts = sorted(find_articulation_points(self.graph))
        score, grade = score_and_grade(composite)

        return {
            "model": MODEL_V1,
            "weights": {"alpha": alpha, "beta": beta, "gamma": gamma},
            "critical_threshold": critical_threshold,
            "bus_factor": bf,
            "decision_concentration": dc,
            "bypass_risk": br,
            "composite_score": composite,
            "score": score,
            "grade": grade,
            "risk_level": interpret_risk_level(composite),
            "critical_nodes": critical_nodes,
            "articulation_points": articulation_pts,
        }

    def analyze_node(self, node_id: str) -> Dict:
        """
        Analyze risk contribution of a specific node.

        Args:
            node_id: ID of the node to analyze

        Returns:
            Dict with node analysis:
                - criticality: Node's criticality score
                - is_articulation_point: Boolean
                - betweenness_centrality: Centrality score
                - node_risk_score: Weighted local risk heuristic in [0, 1]
                - in_degree: Number of incoming edges
                - out_degree: Number of outgoing edges
        """
        if node_id not in self.graph.nodes():
            raise ValueError(f"Node {node_id} not found in graph")
        return self._node_analysis(
            node_id,
            find_articulation_points(self.graph),
            compute_betweenness_centrality(self.graph),
        )

    def analyze_nodes(self) -> Dict[str, Dict]:
        """
        Analyze every node at once, as ``analyze_node`` does for one.

        The graph-wide measures are computed once, so this is much faster than calling
        ``analyze_node`` for each person.
        """
        articulation_pts = find_articulation_points(self.graph)
        betweenness = compute_betweenness_centrality(self.graph)
        return {
            node: self._node_analysis(node, articulation_pts, betweenness) for node in self.graph
        }

    def _node_analysis(
        self, node_id: str, articulation_pts: Set[str], betweenness: Dict[str, float]
    ) -> Dict:
        criticality = self.criticality.get(node_id, 0.0)
        centrality = betweenness.get(node_id, 0.0)

        # Weighted local node-risk heuristic, normalized to [0, 1].
        node_risk_score = min(1.0, 0.7 * criticality + 0.3 * centrality)

        return {
            "criticality": criticality,
            "is_articulation_point": node_id in articulation_pts,
            "betweenness_centrality": centrality,
            "node_risk_score": node_risk_score,
            "in_degree": self.graph.in_degree(node_id),
            "out_degree": self.graph.out_degree(node_id),
        }

    def get_critical_dependencies(self) -> List[Tuple[str, str, str]]:
        """
        Identify all critical dependencies (edges involving critical nodes).

        Returns:
            List of tuples (from_node, to_node, edge_type)
        """
        critical_nodes = {node for node, crit in self.criticality.items() if crit >= 0.7}

        critical_deps = []
        for (u, v), edge_type in self.edge_types.items():
            if u in critical_nodes or v in critical_nodes:
                critical_deps.append((u, v, edge_type))

        return critical_deps

    def simulate_node_removal(self, node_id: str, model: str = MODEL_V2) -> Dict:
        """
        Simulate the impact of removing a node from the graph.

        Args:
            node_id: ID of node to remove
            model: Model used for both scores

        Returns:
            Dict with impact analysis:
                - original_score: HRG score before removal
                - new_score: HRG score after removal
                - score_change: Difference (new - original)
                - disconnected_nodes: Nodes that become isolated
        """
        if node_id not in self.graph:
            raise ValueError(f"Node {node_id} not found in graph")

        original_score = self.calculate(model=model, with_bus_factor=False)["composite_score"]

        people = [p for p in self.people if p["id"] != node_id]
        dependencies = [d for d in self.dependencies if d["from"] != node_id and d["to"] != node_id]
        reduced = HumanRiskGraph(people, dependencies)
        new_score = reduced.calculate(model=model, with_bus_factor=False)["composite_score"]
        temp_graph = reduced.graph

        # Find disconnected nodes
        if len(temp_graph.nodes()) > 0:
            largest_component = max(nx.weakly_connected_components(temp_graph), key=len)
            disconnected = set(temp_graph.nodes()) - largest_component
        else:
            disconnected = set()

        return {
            "original_score": original_score,
            "new_score": new_score,
            "score_change": new_score - original_score,
            "disconnected_nodes": sorted(disconnected),
        }

    def fix_plan(self, steps: int = 3, **calculate_kwargs) -> List[Dict]:
        """
        Rank remediations by how much they improve the score.

        Each step simulates adding a deputy for a key person or putting a second-person
        check on a bypass, applies the best one, and repeats.

        Returns:
            List of dicts with action, target, title, reason, score_before and score_after.
        """
        from .fixes import fix_plan

        if calculate_kwargs.get("model") == MODEL_V3:
            kwargs = {k: v for k, v in calculate_kwargs.items() if k != "model"}
            return fix_plan_v3(
                self.people,
                self.functions,
                lambda people: {p["id"]: p.get("criticality", 0.5) for p in people},
                steps=steps,
                **kwargs,
            )
        return fix_plan(self.people, self.dependencies, steps=steps, **calculate_kwargs)

    def export_graph(self) -> nx.DiGraph:
        """
        Export the underlying NetworkX graph.

        Returns:
            NetworkX DiGraph object
        """
        return self.graph.copy()
