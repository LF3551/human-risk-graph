"""
HRG model v2 (``hrg-2``), the default since 0.5.0.

Three metrics in [0, 1], combined so that one severe weakness is not averaged away:

- Key-person risk K: for every person, the share of connections between the others that
  depend on them, weighted by their criticality; K is the maximum.
- Approval concentration D: Herfindahl-Hirschman index of approval weight; 1/D is the
  effective number of approvers.
- Override exposure B: weighted share of critical approvals that someone can override
  through a bypass dependency.

Composite risk (normalised noisy-OR):
R = (1 - (1 - aK)(1 - bD)(1 - cB)) / (1 - (1 - a)(1 - b)(1 - c)), score = 100 * (1 - R).
"""

from math import prod
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

MODEL_V1 = "hrg-1"
MODEL_V2 = "hrg-2"
MODEL_V3 = "hrg-3"
MODELS = (MODEL_V2, MODEL_V3, MODEL_V1)

# Herfindahl-Hirschman thresholds: below 4 effective approvers is concentrated, below 2 severe.
CONCENTRATION_WARNING = 0.25
CONCENTRATION_ERROR = 0.5

# A break-glass bypass (reviewed after use) can still be misused, but misuse is caught.
BREAK_GLASS_FACTOR = 0.5

Edge = Tuple[str, str]


def _pairs(n: int) -> int:
    return n * (n - 1) // 2


def support_graph(graph: nx.DiGraph) -> nx.Graph:
    """
    Undirected graph of the dependencies that keep people connected.

    Bypass dependencies are left out: being able to override someone does not make the
    organization less dependent on them, it is counted as override exposure instead.
    """
    support = nx.Graph()
    support.add_nodes_from(graph.nodes)
    support.add_edges_from(
        (u, v) for u, v, data in graph.edges(data=True) if data.get("edge_type") != "bypass"
    )
    return support


def separations(graph: nx.Graph) -> Dict[Any, List[int]]:
    """
    For every articulation point of an undirected graph, the sizes of the parts its
    component splits into when it is removed (largest first), from one depth-first search
    with Tarjan's low-link: O(V + E) instead of a search per articulation point.

    In the DFS tree, a child subtree whose low-link does not reach above a vertex is cut off
    when the vertex is removed; for a vertex other than the root, the rest of the component
    stays together. The root is an articulation point when it has two or more children.
    Self-loops are ignored.
    """
    disc: Dict[Any, int] = {}
    low: Dict[Any, int] = {}
    size: Dict[Any, int] = {}
    result: Dict[Any, List[int]] = {}
    for root in graph:
        if root in disc:
            continue
        cut = _dfs_cuts(graph, root, disc, low, size)
        for node, parts in cut.items():
            if node == root:
                if len(parts) >= 2:
                    result[node] = sorted(parts, reverse=True)
                continue
            rest = size[root] - 1 - sum(parts)
            result[node] = sorted(parts + ([rest] if rest else []), reverse=True)
    return result


def _dfs_cuts(graph, root, disc, low, size) -> Dict[Any, List[int]]:
    """Iterative DFS from ``root``: sizes of the child subtrees each vertex cuts off."""
    cut: Dict[Any, List[int]] = {}
    disc[root] = low[root] = len(disc)
    size[root] = 1
    stack = [(root, None, iter(graph[root]))]
    while stack:
        node, parent, neighbours = stack[-1]
        child = next(neighbours, None)
        if child is not None:
            if child == node or child == parent:
                continue
            if child in disc:
                low[node] = min(low[node], disc[child])
            else:
                disc[child] = low[child] = len(disc)
                size[child] = 1
                stack.append((child, node, iter(graph[child])))
            continue
        stack.pop()
        if parent is not None:
            size[parent] += size[node]
            low[parent] = min(low[parent], low[node])
            if low[node] >= disc[parent]:
                cut.setdefault(parent, []).append(size[node])
    return cut


def key_person_impacts(graph: nx.DiGraph) -> Dict[str, Dict[str, float]]:
    """
    Impact of losing each single point of failure.

    For a person v, ``impact`` is the share of connected pairs among the other people that
    are disconnected when v is removed, and ``cut_off`` is the number of people separated
    from the largest remaining group. Only articulation points have a non-zero impact,
    so only they are returned. Bypass dependencies are ignored (see ``support_graph``).
    """
    undirected = support_graph(graph)
    components = list(nx.connected_components(undirected))
    total_pairs = sum(_pairs(len(c)) for c in components)
    component_size = {node: len(comp) for comp in components for node in comp}

    impacts = {}
    for person, parts in separations(undirected).items():
        size = component_size[person]
        pairs_among_others = total_pairs - (size - 1)
        lost = _pairs(size - 1) - sum(_pairs(p) for p in parts)
        impacts[person] = {
            "impact": lost / pairs_among_others if pairs_among_others else 0.0,
            "cut_off": sum(parts[1:]),
        }
    return impacts


def bus_factor_people(graph: nx.DiGraph) -> Optional[int]:
    """
    Smallest number of people whose loss splits the largest group (node connectivity).

    Returns None when the largest group has fewer than three people. Bypass dependencies
    are ignored (see ``support_graph``).
    """
    undirected = support_graph(graph)
    if undirected.number_of_nodes() == 0:
        return None
    largest = max(nx.connected_components(undirected), key=len)
    if len(largest) < 3:
        return None
    sub = undirected.subgraph(largest)
    if any(True for _ in nx.articulation_points(sub)):
        return 1
    return nx.node_connectivity(sub)


def approval_shares(edge_types: Dict[Edge, str], weights: Dict[Edge, float]) -> Dict[str, float]:
    """Share of the total approval weight held by each approver (the ``from`` side)."""
    held: Dict[str, float] = {}
    for edge, edge_type in edge_types.items():
        if edge_type == "approval":
            held[edge[0]] = held.get(edge[0], 0.0) + weights.get(edge, 0.0)
    total = sum(held.values())
    return {person: w / total for person, w in held.items()} if total else {}


def overridable_approvals(
    edge_types: Dict[Edge, str], weights: Dict[Edge, float], critical: Set[str]
) -> Tuple[List[Edge], List[Edge]]:
    """
    Critical approvals, and those among them that someone can override.

    An approval (a, t) is critical if a or t is critical. A bypass (x, a) means x can
    override the controls a enforces, so every approval a gives can be overridden.
    """
    overriders: Dict[str, Set[str]] = {}
    for (source, target), edge_type in edge_types.items():
        if edge_type == "bypass" and source != target:
            overriders.setdefault(target, set()).add(source)

    critical_approvals = sorted(
        edge
        for edge, edge_type in edge_types.items()
        if edge_type == "approval" and (edge[0] in critical or edge[1] in critical)
    )
    overridable = [edge for edge in critical_approvals if overriders.get(edge[0])]
    return critical_approvals, overridable


def override_factors(edge_types: Dict[Edge, str], reviewed: Set[Edge]) -> Dict[str, float]:
    """
    How fully each approver can be overridden: 1 through an unreviewed bypass, or
    ``BREAK_GLASS_FACTOR`` when every bypass of them is reviewed after use.
    """
    factors: Dict[str, float] = {}
    for (source, target), edge_type in edge_types.items():
        if edge_type == "bypass" and source != target:
            factor = BREAK_GLASS_FACTOR if (source, target) in reviewed else 1.0
            factors[target] = max(factors.get(target, 0.0), factor)
    return factors


def composite_risk(metrics: Tuple[float, ...], weights: Tuple[float, ...]) -> float:
    """
    Normalised noisy-OR: R = (1 - prod(1 - w_i m_i)) / (1 - prod(1 - w_i)).

    Each weakness is an independent way to fail, so a severe one dominates instead of being
    averaged away; R is 0 with no weaknesses and 1 when every metric is 1.
    """
    worst = 1.0 - prod(1.0 - w for w in weights)
    return (1.0 - prod(1.0 - w * m for m, w in zip(metrics, weights))) / worst


def grade_for_score(score: int) -> str:
    for grade, floor in (("A", 90), ("B", 80), ("C", 70), ("D", 50)):
        if score >= floor:
            return grade
    return "F"


def score_and_grade(risk: float) -> Tuple[int, str]:
    score = round(100 * (1 - risk))
    return score, grade_for_score(score)


def risk_level_from_score(score: int) -> str:
    for level, floor in (("Low", 70), ("Moderate", 50), ("High", 30)):
        if score >= floor:
            return level
    return "Critical"


def calculate_v2(
    graph: nx.DiGraph,
    criticality: Dict[str, float],
    edge_types: Dict[Edge, str],
    weights: Dict[Edge, float],
    alpha: float,
    beta: float,
    gamma: float,
    critical_threshold: float,
    with_bus_factor: bool = True,
    reviewed: Optional[Set[Edge]] = None,
) -> Dict:
    critical = {node for node, crit in criticality.items() if crit >= critical_threshold}

    impacts = key_person_impacts(graph)
    key_people: List[Dict[str, Any]] = sorted(
        (
            {
                "id": person,
                "criticality": criticality.get(person, 0.5),
                "impact": data["impact"],
                "cut_off": data["cut_off"],
                "risk": criticality.get(person, 0.5) * data["impact"],
            }
            for person, data in impacts.items()
        ),
        key=lambda p: (-p["risk"], p["id"]),
    )
    key_person_risk: float = key_people[0]["risk"] if key_people else 0.0

    shares = approval_shares(edge_types, weights)
    concentration = sum(s * s for s in shares.values())

    critical_approvals, overridable = overridable_approvals(edge_types, weights, critical)
    factors = override_factors(edge_types, reviewed or set())
    total_weight = sum(weights.get(e, 0.0) for e in critical_approvals)
    override_exposure = (
        sum(weights.get(e, 0.0) * factors[e[0]] for e in overridable) / total_weight
        if total_weight
        else 0.0
    )

    risk = composite_risk((key_person_risk, concentration, override_exposure), (alpha, beta, gamma))
    score, grade = score_and_grade(risk)

    return {
        "model": MODEL_V2,
        "weights": {"alpha": alpha, "beta": beta, "gamma": gamma},
        "critical_threshold": critical_threshold,
        "bus_factor": key_person_risk,
        "decision_concentration": concentration,
        "bypass_risk": override_exposure,
        "composite_score": risk,
        "score": score,
        "grade": grade,
        "bus_factor_people": bus_factor_people(graph) if with_bus_factor else None,
        "key_people": key_people,
        "approval_shares": dict(sorted(shares.items(), key=lambda kv: (-kv[1], kv[0]))),
        "effective_approvers": 1 / concentration if concentration else 0.0,
        "critical_approvals": len(critical_approvals),
        "overridable_approvals": [list(e) for e in overridable],
        "break_glass_approvals": [list(e) for e in overridable if factors[e[0]] < 1],
        "critical_nodes": sorted(critical),
        "articulation_points": sorted(impacts),
    }
