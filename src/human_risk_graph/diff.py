"""Compare two organization snapshots."""

import json
from typing import Any, Dict, List, Tuple

from .hrg import HumanRiskGraph
from .model_v2 import MODEL_V2

METRICS = (
    ("composite_score", "Composite risk"),
    ("bus_factor", "Key-person risk"),
    ("decision_concentration", "Approval concentration"),
    ("bypass_risk", "Override exposure"),
)


def _people(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        p["id"]: {
            "id": p["id"],
            "name": p.get("name"),
            "role": p.get("role"),
            "criticality": p.get("criticality", 0.5),
        }
        for p in data["people"]
    }


def _dependencies(data: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    # Same key and defaults as HumanRiskGraph: the last entry for a (from, to) pair wins.
    return {
        (dep["from"], dep["to"]): {
            "from": dep["from"],
            "to": dep["to"],
            "type": dep.get("type", "unknown"),
            "weight": dep.get("weight", 0.5),
        }
        for dep in data["dependencies"]
    }


def compare(old: Dict[str, Any], new: Dict[str, Any], model: str = MODEL_V2) -> Dict[str, Any]:
    """
    Compare two organizations (dicts with ``people`` and ``dependencies``).

    Returns:
        Dict with score and metric deltas, risk level change, added/removed/changed people,
        added/removed/changed dependencies, and introduced/resolved single points of failure.
    """
    old_results = HumanRiskGraph(old["people"], old["dependencies"]).calculate(model=model)
    new_results = HumanRiskGraph(new["people"], new["dependencies"]).calculate(model=model)

    old_people, new_people = _people(old), _people(new)
    old_deps, new_deps = _dependencies(old), _dependencies(new)
    old_spof = set(old_results["articulation_points"])
    new_spof = set(new_results["articulation_points"])

    def changed(before: Dict[Any, Dict], after: Dict[Any, Dict]) -> List[Dict[str, Any]]:
        return [
            {"old": before[key], "new": after[key]}
            for key in sorted(before.keys() & after.keys())
            if before[key] != after[key]
        ]

    return {
        "metrics": {
            key: {
                "old": old_results[key],
                "new": new_results[key],
                "delta": new_results[key] - old_results[key],
            }
            for key, _ in METRICS
        },
        "risk_level": {"old": old_results["risk_level"], "new": new_results["risk_level"]},
        "score": {
            "old": old_results["score"],
            "new": new_results["score"],
            "delta": new_results["score"] - old_results["score"],
            "old_grade": old_results["grade"],
            "new_grade": new_results["grade"],
        },
        "people": {
            "added": sorted(new_people.keys() - old_people.keys()),
            "removed": sorted(old_people.keys() - new_people.keys()),
            "changed": changed(old_people, new_people),
        },
        "dependencies": {
            "added": [new_deps[k] for k in sorted(new_deps.keys() - old_deps.keys())],
            "removed": [old_deps[k] for k in sorted(old_deps.keys() - new_deps.keys())],
            "changed": changed(old_deps, new_deps),
        },
        "single_points_of_failure": {
            "introduced": sorted(new_spof - old_spof),
            "resolved": sorted(old_spof - new_spof),
        },
    }


def risk_increased(diff: Dict[str, Any]) -> bool:
    # Rounded like the reports, so float noise does not fail a pipeline.
    return round(diff["metrics"]["composite_score"]["delta"], 3) > 0


def _dep(dep: Dict[str, Any]) -> str:
    return f"{dep['from']} -> {dep['to']} ({dep['type']}, {dep['weight']:.2f})"


def _person_change(change: Dict[str, Any]) -> str:
    old, new = change["old"], change["new"]
    fields = [
        f"{field} {old[field]!r} => {new[field]!r}"
        for field in ("name", "role", "criticality")
        if old[field] != new[field]
    ]
    return f"~ person {new['id']}: " + ", ".join(fields)


def _change_lines(diff: Dict[str, Any]) -> List[str]:
    lines = []
    for person in diff["people"]["added"]:
        lines.append(f"+ person {person}")
    for person in diff["people"]["removed"]:
        lines.append(f"- person {person}")
    for change in diff["people"]["changed"]:
        lines.append(_person_change(change))
    for dep in diff["dependencies"]["added"]:
        lines.append(f"+ dependency {_dep(dep)}")
    for dep in diff["dependencies"]["removed"]:
        lines.append(f"- dependency {_dep(dep)}")
    for change in diff["dependencies"]["changed"]:
        lines.append(f"~ dependency {_dep(change['old'])} => {_dep(change['new'])}")
    for person in diff["single_points_of_failure"]["introduced"]:
        lines.append(f"+ single point of failure {person}")
    for person in diff["single_points_of_failure"]["resolved"]:
        lines.append(f"- single point of failure {person}")
    return lines


def format_text(diff: Dict[str, Any]) -> str:
    level, score = diff["risk_level"], diff["score"]
    lines = [
        f"{'Score:':<25} {score['old']} ({score['old_grade']}) -> {score['new']} "
        f"({score['new_grade']}) ({score['delta']:+d})"
    ]
    for key, label in METRICS:
        m = diff["metrics"][key]
        lines.append(f"{label + ':':<25} {m['old']:.3f} -> {m['new']:.3f} ({m['delta']:+.3f})")
    lines.append(f"{'Risk level:':<25} {level['old']} -> {level['new']}")
    lines.append("")
    lines.extend(_change_lines(diff) or ["No structural changes."])
    return "\n".join(lines) + "\n"


def format_markdown(diff: Dict[str, Any]) -> str:
    level, score = diff["risk_level"], diff["score"]
    lines = [
        "## Human Risk Graph changes",
        "",
        "| Metric | Old | New | Change |",
        "|---|---:|---:|---:|",
        f"| **Score** | {score['old']} ({score['old_grade']}) | {score['new']} "
        f"({score['new_grade']}) | {score['delta']:+d} |",
    ]
    for key, label in METRICS:
        m = diff["metrics"][key]
        lines.append(f"| {label} | {m['old']:.3f} | {m['new']:.3f} | {m['delta']:+.3f} |")
    lines.append(f"| Risk level | {level['old']} | {level['new']} | |")
    lines.append("")
    changes = _change_lines(diff)
    if changes:
        lines += ["```diff", *changes, "```"]
    else:
        lines.append("No structural changes.")
    return "\n".join(lines) + "\n"


def format_json(diff: Dict[str, Any]) -> str:
    return json.dumps(diff, indent=2, ensure_ascii=False) + "\n"
