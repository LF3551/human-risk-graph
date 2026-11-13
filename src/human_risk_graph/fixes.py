"""
Fix plan: simulate remediations and rank them by how much they improve the score.

Two kinds of remediation are simulated:

- ``deputy``: add a deputy for a person who shares their approvals (each approval's weight
  is split between the two), has the same escalations, and can be overridden by the same
  bypasses, but does not get the person's own bypass powers.
- ``control-bypass``: put a second-person check on a bypass, so that it is no longer a
  single-person override; modelled as removing the bypass.

The plan is greedy: apply the best remediation, re-evaluate, repeat.
"""

from typing import Any, Dict, List, Optional, Tuple

MAX_DEPUTY_CANDIDATES = 8
MAX_BYPASS_CANDIDATES = 8


def _label(people_by_id: Dict[str, Dict], person_id: str) -> str:
    return people_by_id.get(person_id, {}).get("name") or person_id


def _risk(people, dependencies, calculate_kwargs) -> Tuple[float, Dict[str, Any]]:
    from .hrg import HumanRiskGraph

    result = HumanRiskGraph(people, dependencies).calculate(
        with_bus_factor=False, **calculate_kwargs
    )
    return result["composite_score"], result


def _with_deputy(people, dependencies, person_id: str):
    deputy_id = f"{person_id}~deputy"
    while any(p["id"] == deputy_id for p in people):
        deputy_id += "~"
    original = next(p for p in people if p["id"] == person_id)
    deputy = {
        "id": deputy_id,
        "name": f"Deputy for {original.get('name') or person_id}",
        "criticality": original.get("criticality", 0.5),
    }
    new_deps = []
    for dep in dependencies:
        dep_type = dep.get("type")
        touches = person_id in (dep["from"], dep["to"]) and dep["from"] != dep["to"]
        if not touches or (dep_type == "bypass" and dep["from"] == person_id):
            new_deps.append(dep)
            continue
        copy = {
            **dep,
            "from": deputy_id if dep["from"] == person_id else dep["from"],
            "to": deputy_id if dep["to"] == person_id else dep["to"],
        }
        if dep_type == "approval":
            # The deputy shares the approvals, so total approval weight stays the same.
            half = dep.get("weight", 0.5) / 2
            new_deps += [{**dep, "weight": half}, {**copy, "weight": half}]
        else:
            new_deps += [dep, copy]
    return people + [deputy], new_deps


def _with_controlled_bypass(dependencies, edge: Tuple[str, str]):
    return [
        dep
        for dep in dependencies
        if not ((dep["from"], dep["to"]) == edge and dep.get("type") == "bypass")
    ]


def _candidates(people, dependencies, result, original_ids):
    people_by_id = {p["id"]: p for p in people}
    critical = set(result["critical_nodes"])
    deputies: Dict[str, str] = {}

    for person in result.get("key_people", []):
        if person["id"] in original_ids:
            deputies.setdefault(
                person["id"],
                f"single point of failure, cuts off {person['cut_off']} "
                f"{'person' if person['cut_off'] == 1 else 'people'}",
            )
    for person_id, share in list(result.get("approval_shares", {}).items())[:3]:
        if person_id in original_ids:
            deputies.setdefault(person_id, f"holds {share:.0%} of approval weight")

    for person_id, reason in list(deputies.items())[:MAX_DEPUTY_CANDIDATES]:
        yield (
            "deputy",
            person_id,
            f"Add a deputy for {_label(people_by_id, person_id)}",
            reason,
            _with_deputy(people, dependencies, person_id),
        )

    overridden_by_target: Dict[str, int] = {}
    for approver, _ in result.get("overridable_approvals", []):
        overridden_by_target[approver] = overridden_by_target.get(approver, 0) + 1
    bypasses = sorted(
        (
            (dep["from"], dep["to"])
            for dep in dependencies
            if dep.get("type") == "bypass" and (dep["from"] in critical or dep["to"] in critical)
        ),
        key=lambda edge: (-overridden_by_target.get(edge[1], 0), edge),
    )
    for edge in bypasses[:MAX_BYPASS_CANDIDATES]:
        yield (
            "control-bypass",
            list(edge),
            f"Require a second person for {_label(people_by_id, edge[0])}'s bypass of "
            f"{_label(people_by_id, edge[1])}",
            "bypass involving a critical person",
            (people, _with_controlled_bypass(dependencies, edge)),
        )


def fix_plan(
    people: List[Dict],
    dependencies: List[Dict],
    steps: int = 3,
    min_gain: float = 0.005,
    **calculate_kwargs,
) -> List[Dict[str, Any]]:
    """
    Greedy remediation plan.

    Args:
        people, dependencies: Organization data.
        steps: Maximum number of remediations.
        min_gain: Smallest risk reduction (0-1 scale) worth proposing.
        calculate_kwargs: Passed to ``HumanRiskGraph.calculate`` (model, weights, threshold).
    """
    from .model_v2 import score_and_grade

    original_ids = {p["id"] for p in people}
    risk, result = _risk(people, dependencies, calculate_kwargs)
    plan: List[Dict[str, Any]] = []
    seen = set()

    for _ in range(steps):
        best: Optional[Tuple[float, Any]] = None
        for action, target, title, reason, (new_people, new_deps) in _candidates(
            people, dependencies, result, original_ids
        ):
            key = (action, str(target))
            if key in seen:
                continue
            new_risk, new_result = _risk(new_people, new_deps, calculate_kwargs)
            if best is None or new_risk < best[0] - 1e-12:
                best = (new_risk, (action, target, title, reason, new_people, new_deps, new_result))
        if best is None or risk - best[0] < min_gain:
            break

        new_risk, (action, target, title, reason, people, dependencies, result) = best
        seen.add((action, str(target)))
        plan.append(
            {
                "action": action,
                "target": target,
                "title": title,
                "reason": reason,
                "score_before": score_and_grade(risk)[0],
                "score_after": score_and_grade(new_risk)[0],
                "risk_before": risk,
                "risk_after": new_risk,
            }
        )
        risk = new_risk

    return plan
