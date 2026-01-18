"""
Risk metrics for Human Risk Graph.

This module implements the three core HRG metrics:
1. Bus Factor Score (BF) - organizational fragility
2. Decision Concentration Score (DC) - authority distribution
3. Bypass Risk Score (BR) - control circumvention risk
"""

import numpy as np
import networkx as nx
from typing import Dict
from .graph_analysis import find_articulation_points, find_critical_paths, is_path_bypassable


def bus_factor_score(
    graph: nx.DiGraph, criticality: Dict[str, float], critical_threshold: float = 0.7
) -> float:
    """
    Compute Bus Factor Score using articulation point analysis.

    BF(G) = (1/|V|) * Σ C(v) for v in AP(G)

    where AP(G) is the set of articulation points and C(v) is
    the criticality of node v.

    Time complexity: O(|V| + |E|)

    Args:
        graph: NetworkX directed graph
        criticality: Dict mapping node ID -> criticality score [0,1]
        critical_threshold: Minimum criticality to be considered critical

    Returns:
        Bus factor score in [0,1], where higher means more fragile
    """
    if len(graph.nodes()) == 0:
        return 0.0

    # Find articulation points
    articulation_points = find_articulation_points(graph)

    if not articulation_points:
        return 0.0

    # Sum criticality of articulation points
    total_criticality = sum(criticality.get(node, 0.0) for node in articulation_points)

    # Normalize by graph size
    return total_criticality / len(graph.nodes())


def decision_concentration_score(
    graph: nx.DiGraph, edge_types: Dict[tuple, str], weights: Dict[tuple, float]
) -> float:
    """
    Compute Decision Concentration Score using Gini coefficient.

    DC(G) measures inequality in the distribution of approval authority.
    Uses the Gini coefficient: higher values indicate more concentration.

    DC(G) = Σ(2i - n - 1) * w_i / (n * Σw_i)

    Time complexity: O(|E| + |V| log |V|)

    Args:
        graph: NetworkX directed graph
        edge_types: Dict mapping (u, v) -> edge type
        weights: Dict mapping (u, v) -> edge weight [0,1]

    Returns:
        Decision concentration score in [0,1]
        0 = perfectly equal distribution
        1 = maximum concentration
    """
    # Collect approval weights per person
    approval_weights = {}

    for edge, edge_type in edge_types.items():
        if edge_type == "approval":
            from_node = edge[0]
            weight = weights.get(edge, 0.0)
            approval_weights[from_node] = approval_weights.get(from_node, 0.0) + weight

    if not approval_weights:
        return 0.0

    # Get sorted weights
    w = sorted(approval_weights.values())
    n = len(w)

    if n == 0:
        return 0.0

    w_sum = sum(w)
    if w_sum == 0:
        return 0.0

    # Compute Gini coefficient
    numerator = sum((2 * i - n - 1) * w[i - 1] for i in range(1, n + 1))
    gini = numerator / (n * w_sum)

    return gini


def decision_concentration_entropy(
    graph: nx.DiGraph, edge_types: Dict[tuple, str], weights: Dict[tuple, float]
) -> float:
    """
    Alternative DC metric using Shannon entropy.

    DC_entropy(G) = 1 - H(w) / H_max

    where H(w) = -Σ p_i log₂(p_i)

    Args:
        graph: NetworkX directed graph
        edge_types: Dict mapping (u, v) -> edge type
        weights: Dict mapping (u, v) -> edge weight

    Returns:
        Entropy-based concentration score in [0,1]
    """
    # Collect approval weights per person
    approval_weights = {}

    for edge, edge_type in edge_types.items():
        if edge_type == "approval":
            from_node = edge[0]
            weight = weights.get(edge, 0.0)
            approval_weights[from_node] = approval_weights.get(from_node, 0.0) + weight

    if not approval_weights:
        return 0.0

    w = list(approval_weights.values())
    w_sum = sum(w)

    if w_sum == 0:
        return 0.0

    # Compute probabilities
    p = [w_i / w_sum for w_i in w]

    # Compute Shannon entropy
    entropy = -sum(p_i * np.log2(p_i) if p_i > 0 else 0 for p_i in p)

    # Maximum entropy (uniform distribution)
    max_entropy = np.log2(len(p)) if len(p) > 1 else 1.0

    # Concentration = 1 - normalized entropy
    if max_entropy == 0:
        return 0.0

    return 1.0 - (entropy / max_entropy)


def bypass_risk_score(
    graph: nx.DiGraph,
    criticality: Dict[str, float],
    edge_types: Dict[tuple, str],
    critical_threshold: float = 0.7,
) -> float:
    """
    Compute Bypass Risk Score through critical path analysis.

    BR(G) = |{P ∈ CP(G) : P is bypassable}| / |CP(G)|

    where CP(G) is the set of critical paths.

    Time complexity: O(|V| * |E|)

    Args:
        graph: NetworkX directed graph
        criticality: Dict mapping node ID -> criticality score
        edge_types: Dict mapping (u, v) -> edge type
        critical_threshold: Minimum criticality for a node to be critical

    Returns:
        Bypass risk score in [0,1]
        0 = no critical paths bypassable
        1 = all critical paths bypassable
    """
    # Identify critical nodes
    critical_nodes = {node for node, crit in criticality.items() if crit >= critical_threshold}

    if not critical_nodes:
        return 0.0

    # Find all critical paths
    critical_paths = find_critical_paths(graph, critical_nodes, edge_types)

    if not critical_paths:
        return 0.0

    # Count bypassable paths
    bypassable_count = sum(
        1 for path in critical_paths if is_path_bypassable(path, graph, edge_types)
    )

    return bypassable_count / len(critical_paths)


def composite_hrg_score(
    bus_factor: float,
    decision_concentration: float,
    bypass_risk: float,
    alpha: float = 0.4,
    beta: float = 0.3,
    gamma: float = 0.3,
) -> float:
    """
    Compute composite HRG risk score.

    HRG(G) = α * BF(G) + β * DC(G) + γ * BR(G)

    Default weights: α=0.4, β=0.3, γ=0.3

    Args:
        bus_factor: Bus factor score [0,1]
        decision_concentration: Decision concentration score [0,1]
        bypass_risk: Bypass risk score [0,1]
        alpha: Weight for bus factor (default 0.4)
        beta: Weight for decision concentration (default 0.3)
        gamma: Weight for bypass risk (default 0.3)

    Returns:
        Composite HRG score in [0,1]
    """
    if not np.isclose(alpha + beta + gamma, 1.0):
        raise ValueError("Weights must sum to 1.0")

    return alpha * bus_factor + beta * decision_concentration + gamma * bypass_risk


def interpret_risk_level(hrg_score: float) -> str:
    """
    Interpret HRG score into risk level category.

    Args:
        hrg_score: Composite HRG score [0,1]

    Returns:
        Risk level: 'Low', 'Moderate', 'High', or 'Critical'
    """
    if hrg_score < 0.3:
        return "Low"
    elif hrg_score < 0.5:
        return "Moderate"
    elif hrg_score < 0.7:
        return "High"
    else:
        return "Critical"
