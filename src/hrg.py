"""
Human Risk Graph - Main interface class.

This module provides the primary API for building and analyzing
Human Risk Graphs.
"""

import networkx as nx
from typing import Dict, List, Tuple
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

    def __init__(self, people: List[Dict], dependencies: List[Dict]):
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
        """
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
                weight=dep.get("weight", 0.5),
            )

        # Build lookup dictionaries for efficient access
        self.criticality = {p["id"]: p.get("criticality", 0.5) for p in people}
        self.edge_types = {
            (dep["from"], dep["to"]): dep.get("type", "unknown") for dep in dependencies
        }
        self.weights = {(dep["from"], dep["to"]): dep.get("weight", 0.5) for dep in dependencies}

    def calculate(
        self,
        alpha: float = 0.4,
        beta: float = 0.3,
        gamma: float = 0.3,
        critical_threshold: float = 0.7,
    ) -> Dict:
        """
        Calculate all HRG risk metrics.

        Args:
            alpha: Weight for bus factor score (default 0.4)
            beta: Weight for decision concentration (default 0.3)
            gamma: Weight for bypass risk (default 0.3)
            critical_threshold: Minimum criticality for critical nodes (default 0.7)

        Returns:
            Dict containing:
                - bus_factor: Bus factor score [0,1]
                - decision_concentration: DC score [0,1]
                - bypass_risk: Bypass risk score [0,1]
                - composite_score: Overall HRG score [0,1]
                - risk_level: 'Low', 'Moderate', 'High', or 'Critical'
                - critical_nodes: List of critical node IDs
                - articulation_points: List of articulation point IDs
        """
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
        articulation_pts = list(find_articulation_points(self.graph))

        return {
            "bus_factor": bf,
            "decision_concentration": dc,
            "bypass_risk": br,
            "composite_score": composite,
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
                - in_degree: Number of incoming edges
                - out_degree: Number of outgoing edges
        """
        if node_id not in self.graph.nodes():
            raise ValueError(f"Node {node_id} not found in graph")

        articulation_pts = find_articulation_points(self.graph)
        betweenness = compute_betweenness_centrality(self.graph)

        return {
            "criticality": self.criticality.get(node_id, 0.0),
            "is_articulation_point": node_id in articulation_pts,
            "betweenness_centrality": betweenness.get(node_id, 0.0),
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

    def simulate_node_removal(self, node_id: str) -> Dict:
        """
        Simulate the impact of removing a node from the graph.

        Args:
            node_id: ID of node to remove

        Returns:
            Dict with impact analysis:
                - original_score: HRG score before removal
                - new_score: HRG score after removal
                - score_change: Difference (new - original)
                - disconnected_nodes: Nodes that become isolated
        """
        # Calculate original score
        original_result = self.calculate()
        original_score = original_result["composite_score"]

        # Create copy without the node
        temp_graph = self.graph.copy()
        temp_graph.remove_node(node_id)

        # Calculate new metrics on reduced graph
        temp_criticality = {k: v for k, v in self.criticality.items() if k != node_id}
        temp_edge_types = {
            k: v for k, v in self.edge_types.items() if k[0] != node_id and k[1] != node_id
        }
        temp_weights = {
            k: v for k, v in self.weights.items() if k[0] != node_id and k[1] != node_id
        }

        new_bf = bus_factor_score(temp_graph, temp_criticality)
        new_dc = decision_concentration_score(temp_graph, temp_edge_types, temp_weights)
        new_br = bypass_risk_score(temp_graph, temp_criticality, temp_edge_types)
        new_score = composite_hrg_score(new_bf, new_dc, new_br)

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
            "disconnected_nodes": list(disconnected),
        }

    def export_graph(self) -> nx.DiGraph:
        """
        Export the underlying NetworkX graph.

        Returns:
            NetworkX DiGraph object
        """
        return self.graph.copy()
