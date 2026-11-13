"""
HRG model v3 (``hrg-3``, experimental): critical functions and the two-person rule.

A function is something the organization must be able to do (merge to main, publish a
release, change repository settings, restore a database). Each function has a criticality,
the number of people it ``requires`` (2 for a two-person rule), the ``performers`` who can
do it, and the people who can complete it ``alone`` despite the rule.

Three metrics in [0, 1], combined like hrg-2:

- Function loss L: the largest share of function weight that stops when one person is
  unavailable (functions that cannot be performed at all count for everyone).
- Authority concentration D: Herfindahl-Hirschman index of function weight, each function's
  criticality split equally among its performers.
- Solo control S: weighted share of critical functions that one person can complete alone
  (``requires`` 1, or someone in ``alone``), the SLSA Source Level 4 two-party question.
"""

from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from .model_v2 import MODEL_V3, composite_risk, score_and_grade

# Whether one person completing a function alone is a risk (segregation of duties).
SEPARATION_REQUIRED = "required"
SEPARATION_NOT_REQUIRED = "not-required"
SEPARATION_VALUES = (SEPARATION_REQUIRED, SEPARATION_NOT_REQUIRED)


def normalize(functions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Functions with defaults applied; people in ``alone`` are also performers."""
    out = []
    for f in functions:
        alone = set(f.get("alone") or [])
        out.append(
            {
                "id": f["id"],
                "name": f.get("name") or f["id"],
                "criticality": float(f.get("criticality", 0.5)),
                "requires": int(f.get("requires", 1)),
                "performers": set(f.get("performers") or []) | alone,
                "alone": alone,
                "separation": f.get("separation", SEPARATION_REQUIRED),
            }
        )
    return out


def margin(f: Dict[str, Any]) -> int:
    """
    How many people must be unavailable before the function cannot be performed.

    It stops when fewer than ``requires`` performers are left and nobody who can complete it
    alone is left, so the margin is max(|performers| - requires + 1, |alone|).
    """
    return max(0, len(f["performers"]) - f["requires"] + 1, len(f["alone"]))


def stops_without(f: Dict[str, Any], person: str) -> bool:
    return len(f["performers"] - {person}) < f["requires"] and not (f["alone"] - {person})


def solo_people(f: Dict[str, Any]) -> Set[str]:
    """People who can complete the function without anyone else."""
    return set(f["performers"]) if f["requires"] <= 1 else set(f["alone"])


def loss_impacts(functions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """For each person whose absence stops a function: share of weight lost and the functions."""
    total = sum(f["criticality"] for f in functions)
    if not total:
        return {}
    uncovered = [f for f in functions if margin(f) == 0]
    base = sum(f["criticality"] for f in uncovered)
    impacts: Dict[str, Dict[str, Any]] = {}
    for f in functions:
        if margin(f) != 1:
            continue
        for person in f["performers"]:
            if not stops_without(f, person):
                continue
            entry = impacts.setdefault(person, {"weight": base, "functions": []})
            entry["weight"] += f["criticality"]
            entry["functions"].append(f["id"])
    return {
        person: {"impact": e["weight"] / total, "functions": sorted(e["functions"])}
        for person, e in impacts.items()
    }


def function_shares(functions: List[Dict[str, Any]]) -> Dict[str, float]:
    held: Dict[str, float] = {}
    for f in functions:
        if f["performers"]:
            part = f["criticality"] / len(f["performers"])
            for person in f["performers"]:
                held[person] = held.get(person, 0.0) + part
    total = sum(held.values())
    return {p: w / total for p, w in held.items()} if total else {}


def calculate_v3(
    functions: Iterable[Dict[str, Any]],
    criticality: Dict[str, float],
    alpha: float,
    beta: float,
    gamma: float,
    critical_threshold: float,
) -> Dict[str, Any]:
    fns = normalize(functions)
    total = sum(f["criticality"] for f in fns)
    impacts = loss_impacts(fns)
    uncovered = [f["id"] for f in fns if margin(f) == 0]
    base_loss = sum(f["criticality"] for f in fns if margin(f) == 0) / total if total else 0.0
    key_people = sorted(
        (
            {
                "id": person,
                "criticality": criticality.get(person, 0.5),
                "impact": data["impact"],
                "cut_off": len(data["functions"]),
                "risk": data["impact"],
                "functions": data["functions"],
            }
            for person, data in impacts.items()
        ),
        key=lambda p: (-p["risk"], p["id"]),
    )
    loss = key_people[0]["risk"] if key_people else base_loss

    shares = function_shares(fns)
    concentration = sum(s * s for s in shares.values())

    # Solo control only counts functions where completing alone is not the intended policy.
    critical = [f for f in fns if f["criticality"] >= critical_threshold]
    separated = [f for f in critical if f["separation"] == SEPARATION_REQUIRED]
    solo = [f for f in separated if solo_people(f)]
    critical_weight = sum(f["criticality"] for f in separated)
    solo_control = sum(f["criticality"] for f in solo) / critical_weight if critical_weight else 0.0

    weights = (alpha, beta, gamma)
    risk = composite_risk((loss, concentration, solo_control), weights)
    score, grade = score_and_grade(risk)
    availability = composite_risk((loss, concentration), (alpha, beta))
    margins = [margin(f) for f in (critical or fns)]

    return {
        "model": MODEL_V3,
        "weights": {"alpha": alpha, "beta": beta, "gamma": gamma},
        "critical_threshold": critical_threshold,
        "bus_factor": loss,
        "decision_concentration": concentration,
        "bypass_risk": solo_control,
        "composite_score": risk,
        "score": score,
        "grade": grade,
        "scores": {
            "availability": score_and_grade(availability)[0],
            "integrity": round(100 * (1 - solo_control)),
        },
        # Smallest number of people whose absence stops a (critical) function.
        "bus_factor_people": min(margins) if margins else None,
        "key_people": key_people,
        "approval_shares": dict(sorted(shares.items(), key=lambda kv: (-kv[1], kv[0]))),
        "effective_approvers": 1 / concentration if concentration else 0.0,
        "critical_approvals": len(critical),
        "overridable_approvals": [],
        "solo_functions": [f["id"] for f in solo],
        "uncovered_functions": uncovered,
        "functions": [
            {
                "id": f["id"],
                "name": f["name"],
                "criticality": f["criticality"],
                "requires": f["requires"],
                "performers": sorted(f["performers"]),
                "alone": sorted(solo_people(f)),
                "margin": margin(f),
                "single_points": sorted(
                    p for p in f["performers"] if margin(f) == 1 and stops_without(f, p)
                ),
                "critical": f["criticality"] >= critical_threshold,
                "separation": f["separation"],
            }
            for f in fns
        ],
        "critical_nodes": sorted(p for p, c in criticality.items() if c >= critical_threshold),
        "articulation_points": sorted(impacts),
    }


def describe(results: Dict[str, Any], name: Callable[[str], str]) -> List[Tuple[str, str]]:
    """Headline and detail for each metric, used by every report."""
    functions = results.get("functions", [])
    critical = [f for f in functions if f["critical"]]
    key_people = results.get("key_people", [])
    bus = results.get("bus_factor_people")
    uncovered = results.get("uncovered_functions", [])

    if key_people:
        top = key_people[0]
        names = ", ".join(_fname(functions, fid) for fid in top["functions"][:3])
        loss = (
            f"Margin {bus}" if bus is not None else "Single point of failure",
            f"Without {name(top['id'])}, {names} cannot be performed "
            f"({top['impact']:.0%} of function weight).",
        )
    elif uncovered:
        loss = (
            "Not covered",
            f"{', '.join(_fname(functions, f) for f in uncovered[:3])} cannot be performed "
            "with the people listed.",
        )
    else:
        loss = (
            f"Margin {bus}" if bus is not None else "No functions",
            "Every function survives the absence of any one person.",
        )

    shares = results.get("approval_shares", {})
    if shares:
        top_id, top_share = next(iter(shares.items()))
        concentration = (
            f"{results['effective_approvers']:.1f} effective people",
            f"across {len(functions)} functions; {name(top_id)} holds {top_share:.0%} of "
            "the function weight.",
        )
    else:
        concentration = ("No performers", "No function has performers in the data.")

    solo = results.get("solo_functions", [])
    separated = [f for f in critical if f.get("separation") != SEPARATION_NOT_REQUIRED]
    by_policy = len(critical) - len(separated)
    policy_note = f" {by_policy} more can by policy." if by_policy else ""
    if separated:
        detail = (
            f"can be completed by one person: {', '.join(_fname(functions, f) for f in solo[:3])}."
            if solo
            else "need a second person to complete (two-person rule)."
        )
        solo_text = (f"{len(solo)} of {len(separated)} critical functions", detail + policy_note)
    elif critical:
        solo_text = (
            "Solo by policy",
            f"All {len(critical)} critical functions may be completed by one person by policy.",
        )
    else:
        solo_text = ("No critical functions", "No function is at or above the critical threshold.")
    return [loss, concentration, solo_text]


def _fname(functions: List[Dict[str, Any]], fid: str) -> str:
    return next((f["name"] for f in functions if f["id"] == fid), fid)


# Fix plan


def _with_backup(people, functions, fid: str):
    backup = f"{fid}~backup"
    while any(p["id"] == backup for p in people):
        backup += "~"
    f = next(f for f in functions if f["id"] == fid)
    person = {"id": backup, "name": f"Backup for {f.get('name') or fid}", "criticality": 0.5}
    new = [
        {**g, "performers": list(g.get("performers") or []) + [backup]} if g["id"] == fid else g
        for g in functions
    ]
    return people + [person], new


def _with_two_person(functions, fid: str):
    return [
        {**f, "requires": max(2, int(f.get("requires", 1))), "alone": []} if f["id"] == fid else f
        for f in functions
    ]


def _candidates(people, functions, result):
    for f in result["functions"]:
        if f["margin"] <= 1:
            verb = "Add a performer for" if f["margin"] == 0 else "Train a second person for"
            yield (
                "backup",
                f["id"],
                f"{verb} {f['name']}",
                "cannot be performed" if f["margin"] == 0 else "stops if one person is unavailable",
                _with_backup(people, functions, f["id"]),
            )
    for fid in result.get("solo_functions", []):
        f = next(g for g in result["functions"] if g["id"] == fid)
        title = (
            f"Close the way around the two-person rule for {f['name']}"
            if f["requires"] > 1
            else f"Require two people for {f['name']}"
        )
        yield (
            "two-person",
            fid,
            title,
            "critical function one person can complete alone",
            (people, _with_two_person(functions, fid)),
        )


def fix_plan_v3(
    people: List[Dict],
    functions: List[Dict],
    criticality_of: Callable[[List[Dict]], Dict[str, float]],
    alpha: float = 0.4,
    beta: float = 0.3,
    gamma: float = 0.3,
    critical_threshold: float = 0.7,
    steps: int = 3,
    min_gain: float = 0.005,
) -> List[Dict[str, Any]]:
    """Greedy plan of backups and two-person rules, like the hrg-2 fix plan."""

    def evaluate(p, f):
        r = calculate_v3(f, criticality_of(p), alpha, beta, gamma, critical_threshold)
        return r["composite_score"], r

    risk, result = evaluate(people, functions)
    plan: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()
    for _ in range(steps):
        best: Optional[Tuple[float, Any]] = None
        for action, target, title, reason, (new_people, new_functions) in _candidates(
            people, functions, result
        ):
            if (action, target) in seen:
                continue
            new_risk, new_result = evaluate(new_people, new_functions)
            if best is None or new_risk < best[0] - 1e-12:
                best = (
                    new_risk,
                    (action, target, title, reason, new_people, new_functions, new_result),
                )
        if best is None or risk - best[0] < min_gain:
            break
        new_risk, (action, target, title, reason, people, functions, result) = best
        seen.add((action, target))
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
