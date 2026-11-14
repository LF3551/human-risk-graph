"""
Self-contained HTML report: no external resources, works offline, prints to PDF.

Sections: score and verdict, metrics, fix plan, dependency map (SVG laid out in Python,
with a small script for the details panel), people, findings with related controls,
methodology, and an audit appendix.
"""

import json
import math
from html import escape
from string import Template
from typing import Any, Dict, List, Optional, Set

import networkx as nx

from . import __version__
from .findings import FRAMEWORKS, RULES, Finding
from .model_v2 import MODEL_V1, MODEL_V2, MODEL_V3, grade_for_score, support_graph
from .model_v3 import calculate_v3, describe as describe_v3
from .reports import (
    CONTROLS_DISCLAIMER,
    METRIC_KEYS,
    RISK_INTERPRETATION,
    _formula,
    _metric_labels,
    _weights,
    privacy_text,
    unconfirmed_text,
)

GRADE_COLORS = {"A": "#15803d", "B": "#4d7c0f", "C": "#a16207", "D": "#c2410c", "F": "#b91c1c"}
MAP_WIDTH, MAP_HEIGHT, MAP_MARGIN = 820, 500, 56
LABEL_LIMIT = 60  # above this, only key and critical people are labelled on the map
LINK_VERBS = {
    "approval": ("Approves", "Approved by"),
    "escalation": ("Escalates to", "Escalation from"),
    "bypass": ("Can bypass", "Can be bypassed by"),
}
EDGE_VERBS = {"approval": "approves", "escalation": "escalates to", "bypass": "can bypass"}
# Label box estimate at the 14px label font of the map.
CHAR_WIDTH, LABEL_HEIGHT = 7.6, 16
SPREAD_LIMIT = 300  # above this many people the layout is not post-processed
MAP_LIMIT = 400  # above this many people the map is not drawn: unreadable and slow to lay out
WHAT_IF_LIMIT = 40  # people for whom the report precomputes the hrg-3 score without them


def _e(value: Any) -> str:
    return escape(str(value))


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _level(value: float, moderate: float = 0.3, high: float = 0.7) -> str:
    return "High" if value >= high else "Moderate" if value >= moderate else "Low"


def _names(metadata: Dict[str, Any], hrg) -> Dict[str, Dict[str, Any]]:
    people: Dict[str, Dict[str, Any]] = {}
    for p in getattr(hrg, "people", []) or []:
        people[p["id"]] = {
            "name": p.get("name") or p["id"],
            "role": p.get("role", ""),
            "criticality": p.get("criticality", 0.5),
        }
    for pid, info in metadata.get("person_lookup", {}).items():
        people.setdefault(
            pid,
            {
                "name": info.get("name") or pid,
                "role": info.get("role", ""),
                "criticality": info.get("criticality", 0.5),
            },
        )
    return people


# Hero and metrics


def _ring(score: int, color: str) -> str:
    circumference = 2 * math.pi * 52
    filled = circumference * max(0, min(100, score)) / 100
    return f"""<svg class="ring" viewBox="0 0 120 120" role="img" aria-label="Score {score} of 100">
  <circle cx="60" cy="60" r="52" class="ring-track"/>
  <circle cx="60" cy="60" r="52" class="ring-value" stroke="{color}"
          stroke-dasharray="{filled:.1f} {circumference:.1f}" transform="rotate(-90 60 60)"/>
  <text x="60" y="62" class="ring-score">{score}</text>
  <text x="60" y="82" class="ring-max">/ 100</text>
</svg>"""


def _verdict(results: Dict[str, Any], tiles: List[Dict[str, str]]) -> str:
    weights = _weights(results)
    contributions = [w * results[k] for w, k in zip(weights, METRIC_KEYS)]
    if max(contributions) <= 0:
        return "No structural weakness found in the dependency data."
    tile = tiles[contributions.index(max(contributions))]
    detail = tile["detail"]
    separator = ". " if detail[:1].isupper() else " "
    return f"Main driver: {tile['label'].lower()} — {tile['headline']}{separator}{detail}"


def _tiles(results: Dict[str, Any], people: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    labels = _metric_labels(results)
    k, d, b = (results[key] for key in METRIC_KEYS)

    def name(pid: str) -> str:
        return people.get(pid, {}).get("name", pid)

    if results.get("model") == MODEL_V1:
        return [
            {"label": labels[0], "value": k, "level": _level(k), "headline": f"{k:.3f}",
             "detail": "criticality of single points of failure per person"},
            {"label": labels[1], "value": d, "level": _level(d), "headline": f"{d:.3f}",
             "detail": "Gini coefficient of approval weight"},
            {"label": labels[2], "value": b, "level": _level(b), "headline": f"{b:.3f}",
             "detail": "share of critical paths with a bypass shortcut"},
        ]  # fmt: skip

    if results.get("model") == MODEL_V3:
        levels = (_level(k, 0.15, 0.5), _level(d, 0.25, 0.5), _level(b))
        return [
            {"label": label, "value": value, "level": level, "headline": headline, "detail": detail}
            for label, value, level, (headline, detail) in zip(
                labels, (k, d, b), levels, describe_v3(results, name)
            )
        ]

    key_people = results.get("key_people", [])
    bus = results.get("bus_factor_people")
    if key_people:
        top = key_people[0]
        cut = top["cut_off"]
        key = {
            "headline": f"Bus factor {bus}" if bus else "Single point of failure",
            "detail": f"Losing {name(top['id'])} cuts off {cut} "
            f"{'person' if cut == 1 else 'people'} and {_pct(top['impact'])} of connections.",
        }
    else:
        key = {
            "headline": f"Bus factor {bus}" if bus else "No single point of failure",
            "detail": "Nobody's absence disconnects the others.",
        }

    shares = results.get("approval_shares", {})
    if shares:
        top_id, top_share = next(iter(shares.items()))
        approvals = {
            "headline": f"{results['effective_approvers']:.1f} effective approvers",
            "detail": f"of {len(shares)}; {name(top_id)} holds {_pct(top_share)} of approval weight.",
        }
    else:
        approvals = {"headline": "No approvals", "detail": "No approval dependencies in the data."}

    overridable, critical = len(results.get("overridable_approvals", [])), results.get(
        "critical_approvals", 0
    )
    break_glass = len(results.get("break_glass_approvals", []))
    overrides = {
        "headline": f"{overridable} of {critical} critical approvals",
        "detail": "can be overridden through a bypass"
        + (
            f"; {break_glass} only through a break-glass bypass reviewed after use."
            if break_glass
            else "."
        ),
    }
    return [
        {"label": labels[0], "value": k, "level": _level(k, 0.15, 0.5), **key},
        {"label": labels[1], "value": d, "level": _level(d, 0.25, 0.5), **approvals},
        {"label": labels[2], "value": b, "level": _level(b), **overrides},
    ]


def _tiles_html(tiles: List[Dict[str, Any]], weights) -> str:
    out = []
    for tile, weight in zip(tiles, weights):
        out.append(f"""<article class="tile">
  <header><span class="tile-label">{_e(tile['label'])}</span>
    <span class="chip chip-{tile['level'].lower()}">{tile['level']}</span></header>
  <p class="tile-headline">{_e(tile['headline'])}</p>
  <p class="tile-detail">{_e(tile['detail'])}</p>
  <div class="meter meter-{tile['level'].lower()}" title="{tile['value']:.3f}"><span style="width:{tile['value'] * 100:.1f}%"></span></div>
  <footer><span>{tile['value']:.3f}</span><span>weight {weight:.0%}</span></footer>
</article>""")  # fmt: skip
    return "\n".join(out)


# Fix plan


def _fix_targets(fix: Dict[str, Any], results: Dict[str, Any]) -> List[str]:
    """People a fix is about, for highlighting them on the map."""
    target = fix.get("target")
    if fix.get("action") in ("backup", "two-person"):
        f = next((f for f in results.get("functions", []) if f["id"] == target), None)
        return list(f["performers"]) if f else []
    targets = [str(t) for t in target] if isinstance(target, list) else [str(target)]
    # A simulated deputy is not on the map; show the person they stand in for.
    return list(dict.fromkeys(t.removesuffix("~deputy") for t in targets))


def _fixes_html(
    fixes: List[Dict[str, Any]], score: int, v3: bool = False, results: Optional[Dict] = None
) -> str:
    if not fixes:
        return """<p class="muted">No simulated remediation raises the score by at least half
        a point. Keep the data current and re-run after organizational changes.</p>"""
    final = fixes[-1]["score_after"]
    cards = []
    for i, fix in enumerate(fixes, 1):
        gain = fix["score_after"] - fix["score_before"]
        kind = FIX_KINDS.get(fix["action"], fix["action"])
        targets = _e(json.dumps(_fix_targets(fix, results or {})))
        cards.append(f"""<li class="fix" data-targets="{targets}" tabindex="0" role="button"
    title="Show on the map">
  <span class="fix-step">{i}</span>
  <div class="fix-body"><span class="fix-kind">{kind}</span>
    <p class="fix-title">{_e(fix['title'])}</p>
    <p class="fix-why">{_e(fix['reason'])}</p></div>
  <div class="fix-score"><span class="gain">+{gain}</span>
    <span class="muted">{fix['score_before']} → {fix['score_after']}</span></div>
</li>""")  # fmt: skip
    return f"""<p class="lead">Doing all {len(fixes)} raises the score from <strong>{score}</strong>
  to <strong>{final}</strong> (grade {grade_for_score(score)} → {grade_for_score(final)}).</p>
<ol class="fixes">{''.join(cards)}</ol>
<p class="muted small">{FIX_NOTE_V3 if v3 else FIX_NOTE}</p>"""


FIX_KINDS = {
    "deputy": "Deputy",
    "control-bypass": "Bypass control",
    "backup": "Backup",
    "two-person": "Two-person rule",
}
FIX_NOTE = (
    "Simulated on the model: a deputy shares the person's approvals and escalations; a bypass "
    "control means no single person can override, so the bypass is removed."
)
FIX_NOTE_V3 = (
    "Simulated on the model: a backup is one more trained and authorized performer; a "
    "two-person rule means nobody can complete the function alone. Whether it is feasible "
    "is for you to judge."
)


# Dependency map


def _layout(graph: nx.DiGraph) -> Dict[str, tuple]:
    undirected = graph.to_undirected()
    if undirected.number_of_nodes() == 0:
        return {}
    if undirected.number_of_nodes() <= 1:
        return {n: (0.5, 0.5) for n in undirected}
    try:
        if nx.is_connected(undirected) and undirected.number_of_nodes() <= 200:
            pos = nx.kamada_kawai_layout(undirected)
        else:
            pos = nx.spring_layout(undirected, seed=7, iterations=300)
    except Exception:  # layout is cosmetic; never fail the report because of it
        pos = nx.circular_layout(undirected)
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    span_x, span_y = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1
    scaled = {
        n: (
            MAP_MARGIN + (x - min(xs)) / span_x * (MAP_WIDTH - 2 * MAP_MARGIN),
            MAP_MARGIN + (y - min(ys)) / span_y * (MAP_HEIGHT - 2 * MAP_MARGIN - 16),
        )
        for n, (x, y) in pos.items()
    }
    return _spread(scaled) if len(scaled) <= SPREAD_LIMIT else scaled


def _spread(pos: Dict[str, tuple], iterations: int = 120) -> Dict[str, tuple]:
    """Push apart nodes that are too close to label, keeping them inside the map."""
    area = (MAP_WIDTH - 2 * MAP_MARGIN) * (MAP_HEIGHT - 2 * MAP_MARGIN)
    min_dist = min(110.0, 0.75 * math.sqrt(area / max(1, len(pos))))
    pts = {n: [x, y] for n, (x, y) in sorted(pos.items())}
    names = list(pts)
    for _ in range(iterations):
        moved = False
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                dx, dy = pts[b][0] - pts[a][0], pts[b][1] - pts[a][1]
                dist = math.hypot(dx, dy)
                if dist >= min_dist:
                    continue
                if dist < 1e-6:
                    dx, dy, dist = 1.0, 0.0, 1.0
                push = (min_dist - dist) / 2
                pts[a][0] -= dx / dist * push
                pts[a][1] -= dy / dist * push
                pts[b][0] += dx / dist * push
                pts[b][1] += dy / dist * push
                moved = True
        for p in pts.values():
            p[0] = min(max(p[0], MAP_MARGIN), MAP_WIDTH - MAP_MARGIN)
            p[1] = min(max(p[1], MAP_MARGIN), MAP_HEIGHT - MAP_MARGIN - 16)
        if not moved:
            break
    return {n: (x, y) for n, (x, y) in pts.items()}


def _overlap(a, b) -> float:
    """Overlapping area of two rectangles (x1, y1, x2, y2)."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _crosses(segment, rect) -> bool:
    (x1, y1), (x2, y2) = segment
    for i in range(13):
        t = i / 12
        x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
            return True
    return False


def _place_labels(order, names, pos, radii, segments) -> Dict[str, tuple]:
    """
    Greedy label placement: for each person, in order of importance, the first of eight
    positions around the node that overlaps the fewest labels, nodes and edges.

    Returns person id -> (x, y, text-anchor).
    """
    placed: List[tuple] = []
    circles = [
        (x - radii[n], y - radii[n], x + radii[n], y + radii[n]) for n, (x, y) in pos.items()
    ]
    out = {}
    for pid in order:
        x, y = pos[pid]
        r, w, h = radii[pid], len(names[pid]) * CHAR_WIDTH, LABEL_HEIGHT
        candidates = [
            ("middle", x, y + r + 14),
            ("middle", x, y - r - 6),
            ("start", x + r + 5, y + 5),
            ("end", x - r - 5, y + 5),
            ("start", x + r * 0.6, y + r + 12),
            ("end", x - r * 0.6, y + r + 12),
            ("start", x + r * 0.6, y - r - 4),
            ("end", x - r * 0.6, y - r - 4),
        ]
        options = []
        for rank, (anchor, tx, ty) in enumerate(candidates):
            left = {"middle": tx - w / 2, "start": tx, "end": tx - w}[anchor]
            rect = (left, ty - h + 4, left + w, ty + 4)
            outside = max(0, -rect[0]) + max(0, rect[2] - MAP_WIDTH) + max(0, -rect[1])
            outside += max(0, rect[3] - MAP_HEIGHT)
            cost = (
                outside * 50
                + sum(_overlap(rect, p) for p in placed) * 4
                + sum(_overlap(rect, c) for c in circles) * 2
                + sum(30 for s in segments if _crosses(s, rect))
                + rank
            )
            options.append((cost, (tx, ty, anchor), rect))
        _, out[pid], rect = min(options, key=lambda o: o[0])
        placed.append(rect)
    return out


def _cut_off(hrg, people) -> Dict[str, List[str]]:
    """For each person, who is separated from the largest remaining group without them."""
    support = support_graph(hrg.graph)
    out: Dict[str, List[str]] = {}
    for pid in people:
        component = nx.node_connected_component(support, pid) - {pid}
        parts = sorted(
            nx.connected_components(support.subgraph(component)),
            key=lambda part: (-len(part), min(part)),
        )
        out[pid] = sorted(set().union(*parts[1:])) if len(parts) > 1 else []
    return out


def _score_without_v3(hrg, results: Dict[str, Any], pid: str) -> int:
    """hrg-3 score if the person were unavailable: they leave every function."""
    functions = [
        {
            **f,
            "performers": [p for p in f.get("performers") or [] if p != pid],
            "alone": [p for p in f.get("alone") or [] if p != pid],
        }
        for f in hrg.functions
    ]
    w = results.get("weights", {})
    return calculate_v3(
        functions,
        hrg.criticality,
        w.get("alpha", 0.4),
        w.get("beta", 0.3),
        w.get("gamma", 0.3),
        results.get("critical_threshold", 0.7),
    )["score"]


def _person_rows(results, people, hrg, findings) -> Dict[str, Dict[str, Any]]:
    impacts = {p["id"]: p for p in results.get("key_people", [])}
    shares = results.get("approval_shares", {})
    critical = set(results.get("critical_nodes", []))
    spof = set(results.get("articulation_points", []))
    rows: Dict[str, Dict[str, Any]] = {}
    for pid, info in people.items():
        rows[pid] = {
            "id": pid,
            "name": info["name"],
            "role": info["role"],
            "criticality": info["criticality"],
            "impact": impacts.get(pid, {}).get("impact", 0.0),
            "cut_off": impacts.get(pid, {}).get("cut_off", 0),
            "share": shares.get(pid, 0.0),
            "critical": pid in critical,
            "spof": pid in spof,
            "findings": [f"{f.rule_id}: {f.message}" for f in findings if f.person == pid],
            "links": [],
            "cut": [],
        }
    if hrg is None:
        return rows
    if results.get("model") == MODEL_V3:
        _add_function_losses(rows, results, hrg)
    else:
        _add_connection_losses(rows, hrg, spof)
    for (source, target), edge_type in sorted(hrg.edge_types.items()):
        if source in rows and target in rows and source != target:
            out_verb, in_verb = LINK_VERBS.get(edge_type, (f"{edge_type} →", f"{edge_type} ←"))
            rows[source]["links"].append(f"{out_verb} {rows[target]['name']}")
            rows[target]["links"].append(f"{in_verb} {rows[source]['name']}")
    return rows


def _add_connection_losses(rows: Dict[str, Dict[str, Any]], hrg, spof: Set[str]) -> None:
    """hrg-1/hrg-2: who is cut off, and whose only approver each person is."""
    for pid, cut in _cut_off(hrg, spof).items():
        if pid in rows:
            rows[pid]["cut"] = [c for c in cut if c in rows]
    approvers: Dict[str, set] = {}
    for (source, target), edge_type in hrg.edge_types.items():
        if edge_type == "approval" and source != target:
            approvers.setdefault(target, set()).add(source)
    for pid, row in rows.items():
        row["orphaned"] = sorted(
            rows[t]["name"] for t, who in approvers.items() if who == {pid} and t in rows
        )


def _add_function_losses(rows: Dict[str, Dict[str, Any]], results, hrg) -> None:
    """hrg-3: the functions each key person's absence stops, and the score without them."""
    names = {f["id"]: f["name"] for f in results.get("functions", [])}
    for person in results.get("key_people", []):
        if person["id"] in rows:
            rows[person["id"]]["stops"] = [names.get(f, f) for f in person["functions"]]
    for pid in sorted(set(results.get("articulation_points", [])))[:WHAT_IF_LIMIT]:
        if pid in rows:
            rows[pid]["without_score"] = _score_without_v3(hrg, results, pid)


def _map_html(hrg, rows: Dict[str, Dict[str, Any]]) -> str:
    if hrg is None or hrg.graph.number_of_nodes() == 0:
        return '<p class="muted">The dependency map is available when the report is generated by <code>hrg analyze</code>.</p>'
    if hrg.graph.number_of_nodes() > MAP_LIMIT:
        return (
            f'<p class="muted">The map is drawn for up to {MAP_LIMIT} people; this organization '
            f"has {hrg.graph.number_of_nodes()}. The people table and the findings cover everyone, "
            "and <code>hrg visualize</code> draws the whole graph.</p>"
        )
    pos = _layout(hrg.graph)
    max_impact = max((r["impact"] for r in rows.values()), default=0) or 1
    many = len(rows) > LABEL_LIMIT

    def radius(row):
        return 7 + 9 * row["criticality"] + 10 * row["impact"] / max_impact

    edges, segments = [], []
    for (source, target), edge_type in sorted(hrg.edge_types.items()):
        if source == target or source not in pos or target not in pos:
            continue
        (x1, y1), (x2, y2) = pos[source], pos[target]
        length = math.hypot(x2 - x1, y2 - y1) or 1
        r1, r2 = radius(rows[source]), radius(rows[target]) + 6
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        kind = edge_type if edge_type in ("approval", "escalation", "bypass") else "other"
        coords = (
            f'x1="{x1 + ux * r1:.1f}" y1="{y1 + uy * r1:.1f}" '
            f'x2="{x2 - ux * r2:.1f}" y2="{y2 - uy * r2:.1f}"'
        )
        ends = f'data-from="{_e(source)}" data-to="{_e(target)}"'
        verb = EDGE_VERBS.get(edge_type, edge_type)
        weight = hrg.weights.get((source, target), 0.5)
        review = ", reviewed after use" if (source, target) in hrg.reviewed_bypasses else ""
        segments.append(((x1, y1), (x2, y2)))
        edges.append(
            f'<line class="edge edge-{kind}" {ends} {coords} marker-end="url(#arrow-{kind})"/>'
            # Moving dots from source to target show the direction at a glance.
            f'<line class="flow flow-{kind}" {ends} {coords}/>'
            # A wide invisible line makes thin edges easy to hover.
            f'<line class="edge-hit" {ends} {coords}><title>{_e(rows[source]["name"])} {_e(verb)} '
            f"{_e(rows[target]['name'])} · weight {weight:.2f}{review}</title></line>"
        )

    labelled = [pid for pid in pos if not many or rows[pid]["spof"] or rows[pid]["critical"]]
    order = sorted(labelled, key=lambda p: (-rows[p]["impact"], -rows[p]["criticality"], p))
    labels = _place_labels(
        order, {p: rows[p]["name"] for p in pos}, pos, {p: radius(rows[p]) for p in pos}, segments
    )

    nodes = []
    for pid, (x, y) in sorted(pos.items(), key=lambda kv: rows[kv[0]]["impact"]):
        row = rows[pid]
        cls = (
            "node"
            + (" node-spof" if row["spof"] else "")
            + (" node-critical" if row["critical"] else "")
        )
        label = ""
        if pid in labels:
            tx, ty, anchor = labels[pid]
            label = (
                f'<text x="{tx:.1f}" y="{ty:.1f}" class="node-label" '
                f'style="text-anchor:{anchor}">{_e(row["name"])}</text>'
            )
        nodes.append(
            f'<g class="{cls}" data-id="{_e(pid)}" tabindex="0" role="button">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius(row):.1f}"/>{label}'
            f"<title>{_e(row['name'])}{' · ' + _e(row['role']) if row['role'] else ''}</title></g>"
        )

    markers = "".join(
        f'<marker id="arrow-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="arrow-{k}"/></marker>'
        for k in ("approval", "escalation", "bypass", "other")
    )
    return f"""<div class="map-wrap">
  <div class="map-box">
  <svg class="map" viewBox="0 0 {MAP_WIDTH} {MAP_HEIGHT}" role="img" aria-label="Dependency map">
    <defs>{markers}</defs>
    <g class="edges">{''.join(edges)}</g>
    <g class="nodes">{''.join(nodes)}</g>
  </svg>
  <div class="zoom" role="group" aria-label="Zoom">
    <button type="button" data-zoom="in" aria-label="Zoom in">+</button>
    <button type="button" data-zoom="out" aria-label="Zoom out">−</button>
    <button type="button" data-zoom="fit" aria-label="Fit the whole map">⤢</button>
  </div>
  </div>
  <aside class="panel" id="panel" aria-live="polite">
    <p class="muted">Select a person on the map or in the table to see who depends on them
      and what happens if they are unavailable.</p>
  </aside>
</div>
<div class="legend">
  <span><i class="dot dot-spof-critical"></i>Critical single point of failure</span>
  <span><i class="dot dot-spof"></i>Single point of failure</span>
  <span><i class="dot dot-critical"></i>Critical (≥ threshold)</span>
  <span><i class="dot"></i>Other</span>
  <span><i class="line line-approval"></i>Approval</span>
  <span><i class="line line-escalation"></i>Escalation</span>
  <span><i class="line line-bypass"></i>Bypass</span>
  <span class="muted">Moving dots run from who approves, escalates or bypasses to whom · Select a key person: the people cut off without them pulse red · Node size: criticality and impact · Drag to pan when zoomed</span>
</div>"""  # fmt: skip


def _people_html(rows: Dict[str, Dict[str, Any]], labels: Dict[str, Any]) -> str:
    ordered = sorted(rows.values(), key=lambda r: (-r["impact"], -r["criticality"], r["name"]))
    body = []
    for r in ordered:
        flags = "".join(
            [
                '<span class="chip chip-high">SPOF</span>' if r["spof"] else "",
                '<span class="chip chip-moderate">critical</span>' if r["critical"] else "",
            ]
        )
        body.append(
            f'<tr data-id="{_e(r["id"])}"><td><strong>{_e(r["name"])}</strong>'
            f'<div class="muted small">{_e(r["role"])}</div></td>'
            f'<td data-label="Criticality" data-v="{r["criticality"]}">{r["criticality"]:.2f}</td>'
            f'<td data-label="{labels["impact"]}" data-v="{r["impact"]}">{_pct(r["impact"]) if r["impact"] else "—"}</td>'
            f'<td data-label="{labels["cut"]}" data-v="{r["cut_off"]}">{r["cut_off"] or "—"}</td>'
            f'<td data-label="{labels["share"]}" data-v="{r["share"]}">{_pct(r["share"]) if r["share"] else "—"}</td>'
            f'<td class="flags">{flags}</td></tr>'
        )  # fmt: skip
    return f"""<p class="muted">{labels['intro']}</p>
<table class="people sortable">
  <thead><tr><th data-sort="text">Person</th><th data-sort="num">Criticality</th>
  <th data-sort="num">{labels['impact']}</th><th data-sort="num">{labels['cut']}</th>
  <th data-sort="num">{labels['share']}</th><th>Flags</th></tr></thead>
  <tbody>{''.join(body)}</tbody>
</table>"""


PEOPLE_LABELS = {
    "intro": "Impact is the share of connections between the others that depend on the person.",
    "impact": "Impact",
    "cut": "Cuts off",
    "units": ["person", "people"],
    "share": "Approval share",
}
PEOPLE_LABELS_V3 = {
    "intro": "Weight lost is the share of function weight that stops if the person is unavailable.",
    "impact": "Weight lost",
    "cut": "Functions lost",
    "units": ["function", "functions"],
    "share": "Function share",
}


def _functions_html(results: Dict[str, Any], people: Dict[str, Dict[str, Any]]) -> str:
    functions = results.get("functions") or []
    if not functions:
        return ""

    def names(ids):
        return ", ".join(_e(people.get(i, {}).get("name", i)) for i in ids) or "—"

    def alone(f):
        policy = f["alone"] and f.get("separation") == "not-required"
        return names(f["alone"]) + (' <span class="muted">(by policy)</span>' if policy else "")

    body = "".join(
        f'<tr><td><strong>{_e(f["name"])}</strong></td>'
        f'<td data-label="Criticality">{f["criticality"]:.2f}</td>'
        f'<td data-label="Requires">{f["requires"]}</td>'
        f'<td data-label="Performers">{names(f["performers"])}</td>'
        f'<td data-label="Margin"><span class="chip chip-{"high" if f["margin"] <= 1 else "low"}">{f["margin"]}</span></td>'
        f'<td data-label="Alone">{alone(f)}</td></tr>'
        for f in functions
    )  # fmt: skip
    return f"""<h3>Critical functions</h3>
<p class="muted">Margin: how many performers can be unavailable before the function stops.
  Alone: who can complete it without a second person; (by policy): allowed, not counted as
  solo control.</p>
<table class="people functions">
  <thead><tr><th>Function</th><th>Criticality</th><th>Requires</th><th>Performers</th>
  <th>Margin</th><th>Alone</th></tr></thead>
  <tbody>{body}</tbody>
</table>"""


# Findings


def _accepted_html(accepted: List[Finding]) -> str:
    if not accepted:
        return ""
    rows = "".join(
        f'<tr><td><span class="rule">{f.rule_id}</span>{_e(f.message)}</td>'
        f"<td>{_e(a.reason)}</td><td>{_e(a.ticket or '—')}</td>"
        f"<td>{_e(a.expires.isoformat() if a.expires else '—')}</td></tr>"
        for f in accepted
        if (a := f.acceptance) is not None
    )
    return f"""<h3 class="accepted-title">Accepted risks <span class="count">{len(accepted)}</span></h3>
<table class="accepted"><thead><tr><th>Finding</th><th>Reason</th><th>Ticket</th><th>Expires</th></tr></thead>
<tbody>{rows}</tbody></table>"""  # fmt: skip


def _findings_html(findings: List[Finding]) -> str:
    accepted = [f for f in findings if f.accepted]
    findings = [f for f in findings if not f.accepted]
    if not findings:
        return '<p class="muted">No open findings.</p>' + _accepted_html(accepted)
    groups = []
    for rule in RULES.values():
        items = [f for f in findings if f.rule_id == rule.id]
        if not items:
            continue
        level = "error" if any(f.level == "error" for f in items) else "warning"
        controls = "".join(
            f'<div class="controls"><span class="fw">{_e(FRAMEWORKS[fw])}</span>'
            + "".join(
                f'<span class="control" title="{_e(title)}">{_e(ref)}</span>' for ref, title in refs
            )
            + "</div>"
            for fw, refs in rule.controls.items()
        )
        lis = "".join(
            f'<li><span class="sev sev-{f.level}">{f.level}</span>{_e(f.message)}</li>'
            for f in items
        )
        groups.append(f"""<details class="finding finding-{level}" open>
  <summary><span class="rule">{rule.id}</span> {_e(rule.title)}
    <span class="count">{len(items)}</span></summary>
  <ul>{lis}</ul>
  <p class="remediation"><strong>Remediation.</strong> {_e(rule.remediation)}</p>
  {controls}
</details>""")  # fmt: skip
    return (
        f'<p class="muted small">{_e(CONTROLS_DISCLAIMER)}</p>'
        + "".join(groups)
        + _accepted_html(accepted)
    )


# Methodology and audit


def _method_html(results: Dict[str, Any]) -> str:
    labels = _metric_labels(results)
    rows = "".join(
        f"<tr><td>{_e(label)}</td><td>{results[key]:.3f}</td><td>{weight:.0%}</td></tr>"
        for key, label, weight in zip(METRIC_KEYS, labels, _weights(results))
    )
    if results.get("model") == MODEL_V1:
        definitions = """<li><strong>Bus factor risk</strong>: sum of criticality of articulation
          points divided by the number of people.</li>
        <li><strong>Decision concentration</strong>: Gini coefficient of approval weight.</li>
        <li><strong>Bypass risk</strong>: share of critical paths with a bypass shortcut.</li>"""
    elif results.get("model") == MODEL_V3:
        definitions = """<li><strong>Function loss L</strong>: the largest share of function weight
          that stops when one person is unavailable (a function stops when fewer performers are
          left than it requires).</li>
        <li><strong>Authority concentration D</strong>: Herfindahl-Hirschman index of function
          weight, each function's criticality split among its performers.</li>
        <li><strong>Solo control S</strong>: weighted share of critical functions one person can
          complete alone, the SLSA Source Level 4 two-party question. Model hrg-3 is experimental.</li>"""
    else:
        definitions = """<li><strong>Key-person risk K</strong>: the largest criticality × impact,
          where impact is the share of connections between the others that are lost without the person.</li>
        <li><strong>Approval concentration D</strong>: Herfindahl-Hirschman index of approval
          weight; 1/D is the effective number of approvers.</li>
        <li><strong>Override exposure B</strong>: weighted share of critical approvals whose
          approver can be bypassed.</li>"""
    return f"""<ul class="defs">{definitions}</ul>
<p class="formula">{_e(_formula(results))}</p>
<table class="kv"><thead><tr><th>Metric</th><th>Value</th><th>Weight</th></tr></thead>
  <tbody>{rows}<tr><td><strong>Composite risk</strong></td>
  <td><strong>{results['composite_score']:.3f}</strong></td><td></td></tr></tbody></table>
<p class="muted small">Grades: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 50, F below 50. Full definitions and
  properties: <a href="https://github.com/LF3551/human-risk-graph/blob/main/docs/model.md">docs/model.md</a>.</p>"""


def _audit_html(results: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    w = results.get("weights", {})
    items = [
        ("Input file", metadata.get("input_name") or metadata.get("input_file", "")),
        ("Input SHA-256", metadata.get("input_sha256", "not recorded")),
        ("Generated", metadata.get("analysis_date", "")),
        ("Tool", f"human-risk-graph {metadata.get('tool_version', __version__)}"),
        ("Model", results.get("model", MODEL_V2)),
        ("Weights", f"α {w.get('alpha', 0.4)} · β {w.get('beta', 0.3)} · γ {w.get('gamma', 0.3)}"),
        ("Critical threshold", results.get("critical_threshold", 0.7)),
        ("Config", metadata.get("config_file") or "none"),
        ("Unconfirmed dependencies", metadata.get("unconfirmed_dependencies", 0)),
        ("Data gaps", len(metadata.get("coverage_gaps") or [])),
        ("People / dependencies", f"{metadata.get('organization_size', '')} / {metadata.get('dependencies_count', '')}"),
    ]  # fmt: skip
    rows = "".join(f"<tr><th>{_e(k)}</th><td><code>{_e(v)}</code></td></tr>" for k, v in items)
    return f'<table class="kv audit">{rows}</table>'


def _confirmed_only_text(confirmed_only: Optional[Dict[str, Any]]) -> str:
    if not confirmed_only:
        return ""
    return (
        f" On confirmed data only: <strong>{_e(confirmed_only['score'])}/100</strong> "
        f"(grade {_e(confirmed_only['grade'])}, {_e(confirmed_only['dependencies'])} "
        "dependencies)."
    )


def _gaps_html(gaps: List[str]) -> str:
    if not gaps:
        return ""
    items = "".join(f"<li>{_e(gap)}</li>" for gap in gaps)
    return (
        f'<details class="notice"><summary>{len(gaps)} data '
        f"{'gap' if len(gaps) == 1 else 'gaps'}: what the scan could not see is not evidence "
        f"that it does not exist</summary><ul>{items}</ul></details>"
    )


def _json_for_script(data: Any) -> str:
    # Inside <script>, "<" must not appear raw or "</script>" in a name could end the block.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def render(
    results: Dict[str, Any],
    metadata: Dict[str, Any],
    findings: Optional[List[Finding]] = None,
    fixes: Optional[List[Dict[str, Any]]] = None,
    hrg=None,
) -> str:
    findings = findings or []
    fixes = fixes or []
    people = _names(metadata, hrg)
    rows = _person_rows(results, people, hrg, findings)
    tiles = _tiles(results, people)
    grade = results["grade"]
    v3 = results.get("model") == MODEL_V3
    people_labels = PEOPLE_LABELS_V3 if v3 else PEOPLE_LABELS
    color = GRADE_COLORS.get(grade, "#334155")
    open_findings = [f for f in findings if not f.accepted]
    errors = sum(1 for f in open_findings if f.level == "error")
    accepted = len(findings) - len(open_findings)
    warnings = len(open_findings) - errors
    finding_summary = (
        f"{errors} error{'s' if errors != 1 else ''} · {warnings} warning{'s' if warnings != 1 else ''}"
        + (f" · {accepted} accepted" if accepted else "")
    )

    return TEMPLATE.substitute(
        title=_e(f"Human Risk Graph · {metadata.get('input_name') or 'report'}"),
        css=CSS,
        js=JS,
        input_name=_e(metadata.get("input_name") or metadata.get("input_file", "")),
        generated=_e(str(metadata.get("analysis_date", ""))[:16].replace("T", " ")),
        size=_e(metadata.get("organization_size", len(rows))),
        deps=_e(metadata.get("dependencies_count", "")),
        model=_e(results.get("model", MODEL_V2)),
        version=_e(metadata.get("tool_version", __version__)),
        ring=_ring(results["score"], color),
        grade=_e(grade),
        grade_color=color,
        risk_level=_e(results["risk_level"]),
        interpretation=_e(RISK_INTERPRETATION.get(results["risk_level"], "")),
        verdict=_e(_verdict(results, tiles)),
        finding_summary=finding_summary,
        unconfirmed=(
            f'<p class="notice">{_e(privacy_text(metadata))}</p>' if privacy_text(metadata) else ""
        )
        + (
            f'<p class="notice">{_e(unconfirmed_text(metadata))} (from '
            "<code>hrg scan</code>): review them before relying on the score."
            + _confirmed_only_text(metadata.get("confirmed_only"))
            + "</p>"
            if unconfirmed_text(metadata)
            else ""
        )
        + _gaps_html(metadata.get("coverage_gaps") or []),
        tiles=_tiles_html(tiles, _weights(results)),
        fixes=_fixes_html(fixes, results["score"], v3, results),
        map=_map_html(hrg, rows),
        people=_people_html(rows, people_labels) + _functions_html(results, people),
        findings=_findings_html(findings),
        method=_method_html(results),
        audit=_audit_html(results, metadata),
        data=_json_for_script({"people": rows, "labels": people_labels, "score": results["score"]}),
    )


CSS = """
:root {
  --bg: #f6f7f9; --card: #ffffff; --text: #0f172a; --muted: #64748b; --line: #e2e8f0;
  --accent: #4f46e5; --error: #b91c1c; --warn: #b45309; --ok: #15803d;
  --node: #94a3b8; --critical: #d97706; --spof: #dc2626;
  --approval: #4f46e5; --escalation: #94a3b8; --bypass: #dc2626; --other: #cbd5e1;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #0b1120; --card: #111827; --text: #e5e7eb; --muted: #94a3b8; --line: #1f2937;
          --node: #64748b; --escalation: #64748b; --other: #334155; --accent: #818cf8;
          --approval: #818cf8; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); line-height: 1.5;
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
  font-variant-numeric: tabular-nums; }
.wrap { max-width: 1120px; margin: 0 auto; padding: 32px 24px 64px; }
a { color: var(--accent); }
code { font: 12.5px ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; }
.muted { color: var(--muted); } .small { font-size: 13px; }
.top { display: flex; justify-content: space-between; align-items: baseline; gap: 16px;
  flex-wrap: wrap; margin-bottom: 20px; }
.brand { font-weight: 700; letter-spacing: -0.01em; }
.brand span { color: var(--muted); font-weight: 500; }
nav a { color: var(--muted); text-decoration: none; margin-left: 16px; font-size: 14px; }
nav a:hover { color: var(--text); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 16px;
  padding: 24px; margin-bottom: 20px; }
h2 { font-size: 18px; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 + .muted { margin: 0 0 18px; }
.hero { display: grid; grid-template-columns: 200px 1fr; gap: 28px; align-items: center; }
.ring { width: 180px; height: 180px; }
.ring-track { fill: none; stroke: var(--line); stroke-width: 10; }
.ring-value { fill: none; stroke-width: 10; stroke-linecap: round; }
.ring-score { font-size: 34px; font-weight: 750; text-anchor: middle; fill: var(--text); }
.ring-max { font-size: 11px; text-anchor: middle; fill: var(--muted); }
.grade { display: inline-flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.grade b { font-size: 28px; width: 44px; height: 44px; border-radius: 12px; color: #fff;
  display: inline-grid; place-items: center; }
.grade span { font-size: 22px; font-weight: 650; }
.verdict { font-size: 17px; margin: 6px 0; }
.notice { border: 1px solid var(--warn); color: var(--warn); border-radius: 10px;
  padding: 8px 12px; font-size: 14px; margin: 10px 0 0; }
details.notice summary { cursor: pointer; }
details.notice ul { margin: 6px 0 0; padding-left: 18px; }
.meta { display: flex; gap: 18px; flex-wrap: wrap; color: var(--muted); font-size: 13px; margin-top: 12px; }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.tile { border: 1px solid var(--line); border-radius: 14px; padding: 16px; display: flex;
  flex-direction: column; gap: 6px; }
.tile header, .tile footer { display: flex; justify-content: space-between; align-items: center; }
.tile-label { font-size: 13px; color: var(--muted); font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.04em; }
.tile-headline { font-size: 20px; font-weight: 700; margin: 0; }
.tile-detail { margin: 0; color: var(--muted); flex: 1; }
.tile footer { font-size: 12px; color: var(--muted); }
.meter { height: 6px; background: var(--line); border-radius: 99px; overflow: hidden; }
.meter span { display: block; height: 100%; background: var(--ok); }
.meter-moderate span { background: var(--warn); } .meter-high span { background: var(--error); }
.chip { font-size: 11.5px; font-weight: 650; padding: 2px 8px; border-radius: 99px;
  border: 1px solid transparent; white-space: nowrap; margin-right: 4px; }
.chip-low { color: var(--ok); border-color: currentColor; }
.chip-moderate { color: var(--warn); border-color: currentColor; }
.chip-high { color: var(--error); border-color: currentColor; }
.lead { font-size: 16px; margin: 0 0 14px; }
.fixes { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
.fix { display: grid; grid-template-columns: 36px 1fr auto; gap: 14px; align-items: center;
  border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }
.fix-step { width: 32px; height: 32px; border-radius: 50%; background: var(--accent); color: #fff;
  display: grid; place-items: center; font-weight: 700; }
.fix-kind { font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
.fix-title { margin: 2px 0; font-weight: 650; }
.fix-why { margin: 0; color: var(--muted); font-size: 14px; }
.fix-score { text-align: right; display: flex; flex-direction: column; }
.gain { color: var(--ok); font-size: 20px; font-weight: 750; }
.map-wrap { display: grid; grid-template-columns: 1fr 280px; gap: 16px; align-items: start; }
.map { width: 100%; height: auto; border: 1px solid var(--line); border-radius: 12px; background: var(--bg); }
.edge { stroke-width: 1.6; }
.edge-approval { stroke: var(--approval); }
.edge-escalation { stroke: var(--escalation); stroke-dasharray: 4 4; }
.edge-bypass { stroke: var(--bypass); stroke-dasharray: 7 4; stroke-width: 2; }
.edge-other { stroke: var(--other); }
.flow { fill: none; stroke-width: 2.6; stroke-linecap: round; stroke-dasharray: 0.1 13;
  pointer-events: none; opacity: 0.55; animation: hrg-flow 2.4s linear infinite; }
.flow-approval { stroke: var(--approval); } .flow-escalation { stroke: var(--escalation); }
.flow-bypass { stroke: var(--bypass); stroke-width: 3.4; animation-duration: 1.1s; }
.flow-other { stroke: var(--other); }
@keyframes hrg-flow { to { stroke-dashoffset: -13.1; } }
@keyframes hrg-pulse { 50% { stroke-width: 8; } }
.arrow-approval { fill: var(--approval); } .arrow-escalation { fill: var(--escalation); }
.arrow-bypass { fill: var(--bypass); } .arrow-other { fill: var(--other); }
.node circle { fill: var(--node); stroke: var(--card); stroke-width: 2.5; cursor: pointer; }
.node-critical circle { stroke: var(--critical); stroke-width: 3.5; }
.node-spof circle { fill: var(--critical); }
.node-spof.node-critical circle { fill: var(--spof); stroke: var(--card); stroke-width: 2.5; }
.edge-hit { stroke: transparent; stroke-width: 12; pointer-events: stroke; cursor: help; }
.map-box { position: relative; }
.map-box .map { touch-action: none; }
.map.panning { cursor: grabbing; }
.zoom { position: absolute; top: 8px; right: 8px; display: flex; gap: 4px; }
.zoom button { width: 30px; height: 30px; border-radius: 8px; border: 1px solid var(--line);
  background: var(--card); color: var(--text); font-size: 16px; cursor: pointer; }
.zoom button:hover { border-color: var(--accent); }
.fix[data-targets] { cursor: pointer; }
.fix[data-targets]:hover, .fix[data-targets]:focus-visible { border-color: var(--accent); outline: none; }
.node.hint circle { stroke: var(--accent); stroke-width: 4; }
.whatif { border: 1px solid var(--line); border-left: 3px solid var(--spof); border-radius: 10px;
  padding: 8px 12px; margin: 10px 0; }
.whatif strong { display: block; margin-bottom: 4px; }
.whatif .score-drop { font-size: 18px; font-weight: 750; color: var(--spof); }
.node-label { font-size: 14px; font-weight: 550; text-anchor: middle; fill: var(--text); pointer-events: none;
  paint-order: stroke; stroke: var(--bg); stroke-width: 4px; }
.map.focus .edge, .map.focus .node { opacity: 0.18; transition: opacity .15s; }
.map.focus .is-on { opacity: 1; }
.map.focus .flow { opacity: 0; }
.map.focus .flow.is-on { opacity: 1; animation-duration: 1s; }
.map.focus .flow-bypass.is-on { animation-duration: 0.55s; }
.node.cut circle { stroke: var(--spof); stroke-width: 3; animation: hrg-pulse 1.2s ease-in-out infinite; }
.edge.cut { stroke: var(--spof); } .flow.cut { stroke: var(--spof); }
@media (prefers-reduced-motion: reduce) {
  .flow, .node.cut circle { animation: none; }
  .flow { stroke-dasharray: none; opacity: 0.25; }
}
.node.selected circle { stroke: var(--text); stroke-width: 3; }
.panel { border: 1px solid var(--line); border-radius: 12px; padding: 16px; font-size: 14px;
  max-height: 540px; overflow: auto; }
.panel h3 { margin: 0; font-size: 17px; }
.panel dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; margin: 12px 0; }
.panel dt { color: var(--muted); } .panel dd { margin: 0; font-weight: 600; }
.panel ul { padding-left: 18px; margin: 6px 0 12px; }
.legend { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--muted); margin-top: 12px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 11px; height: 11px; border-radius: 50%; background: var(--node); display: inline-block; }
.dot-spof { background: var(--critical); } .dot-spof-critical { background: var(--spof); }
.dot-critical { background: var(--node); box-shadow: 0 0 0 2px var(--critical); }
.line { width: 22px; height: 0; border-top: 2px solid; display: inline-block; }
.line-approval { border-color: var(--approval); }
.line-escalation { border-color: var(--escalation); border-top-style: dashed; }
.line-bypass { border-color: var(--bypass); border-top-style: dashed; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
th[data-sort] { cursor: pointer; user-select: none; }
th[data-sort]:hover { color: var(--text); }
.people tbody tr { cursor: pointer; } .people tbody tr:hover { background: var(--bg); }
.people tbody tr.selected { background: var(--bg); box-shadow: inset 3px 0 var(--accent); }
.finding { border: 1px solid var(--line); border-left: 4px solid var(--warn); border-radius: 12px;
  padding: 12px 16px; margin-top: 12px; }
.finding-error { border-left-color: var(--error); }
.finding summary { cursor: pointer; font-weight: 650; }
.rule { font: 12.5px ui-monospace, Menlo, monospace; color: var(--muted); margin-right: 6px; }
.count { float: right; color: var(--muted); font-weight: 500; }
.finding ul { padding-left: 0; list-style: none; margin: 10px 0; }
.finding li { padding: 4px 0; }
.sev { font-size: 11px; font-weight: 700; text-transform: uppercase; margin-right: 8px; }
.sev-error { color: var(--error); } .sev-warning { color: var(--warn); }
.remediation { margin: 6px 0 10px; }
.accepted-title { font-size: 15px; margin: 22px 0 6px; }
.accepted td { color: var(--muted); }
.controls { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 4px 0; font-size: 13px; }
.fw { color: var(--muted); min-width: 230px; }
.control { border: 1px solid var(--line); border-radius: 6px; padding: 1px 7px;
  font: 12px ui-monospace, Menlo, monospace; cursor: help; }
.defs { padding-left: 18px; } .defs li { margin: 4px 0; }
.formula { font: 13px ui-monospace, Menlo, monospace; background: var(--bg);
  border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; overflow-x: auto; }
.kv { max-width: 640px; } .audit th { width: 220px; text-transform: none; letter-spacing: 0; font-size: 13px; }
footer.page { color: var(--muted); font-size: 13px; text-align: center; margin-top: 28px; }
.hero > *, .map-wrap > *, .tiles > *, .fix > * { min-width: 0; }
@media (max-width: 860px) {
  .hero, .map-wrap { grid-template-columns: 1fr; } .tiles { grid-template-columns: 1fr; }
  .ring { margin: 0 auto; display: block; } .fw { min-width: 0; width: 100%; }
}
@media (max-width: 640px) {
  body { font-size: 14px; }
  .wrap { padding: 16px 12px 40px; }
  .card { padding: 16px; border-radius: 14px; }
  nav { display: flex; flex-wrap: wrap; gap: 4px 14px; } nav a { margin-left: 0; }
  .ring { width: 150px; height: 150px; }
  .hero { gap: 12px; text-align: center; } .grade, .meta { justify-content: center; }
  .fix { grid-template-columns: 32px 1fr; padding: 12px; }
  .fix-score { grid-column: 2; flex-direction: row; gap: 10px; align-items: baseline; text-align: left; }
  .node-label { font-size: 26px; stroke-width: 7px; }
  .people thead { display: none; }
  .people, .people tbody, .people tr, .people td { display: block; width: 100%; }
  .people tr { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 12px; padding: 12px 4px;
    border-bottom: 1px solid var(--line); }
  .people td { border: 0; padding: 2px 0; }
  .people td:first-child, .people td.flags { grid-column: 1 / -1; }
  .people td[data-label]::before { content: attr(data-label) ": "; color: var(--muted); }
  .audit th, .audit td { display: block; width: auto; border: 0; padding: 2px 0; }
  .audit tr { display: block; padding: 8px 0; border-bottom: 1px solid var(--line); }
  .count { float: none; margin-left: 6px; }
}
@media print {
  body { background: #fff; } nav, .panel, th[data-sort]::after, .flow, .zoom { display: none; }
  .card { break-inside: avoid; border-color: #ddd; } .map-wrap { grid-template-columns: 1fr; }
  details { display: block; } details > summary { list-style: none; }
}
"""

JS = """
(function () {
  var payload = JSON.parse(document.getElementById('hrg-data').textContent);
  var data = payload.people, L = payload.labels;
  var map = document.querySelector('.map');
  var panel = document.getElementById('panel');
  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }
  function pct(v) { return v ? Math.round(v * 100) + '%' : '—'; }
  function show(id, focus) {
    var p = data[id];
    if (!p || !panel) return;
    panel.replaceChildren();
    panel.appendChild(el('h3', p.name));
    if (p.role) panel.appendChild(el('div', p.role, 'muted'));
    var dl = el('dl');
    [['Criticality', p.criticality.toFixed(2)], [L.impact, pct(p.impact)],
     [L.cut, p.cut_off ? p.cut_off + ' ' + L.units[p.cut_off === 1 ? 0 : 1] : '—'],
     [L.share, pct(p.share)],
     ['Status', (p.spof ? 'Single point of failure' : '') + (p.spof && p.critical ? ' · ' : '') +
       (p.critical ? 'Critical' : '') || '—']].forEach(function (kv) {
      dl.appendChild(el('dt', kv[0])); dl.appendChild(el('dd', kv[1]));
    });
    panel.appendChild(dl);
    function list(title, items) {
      if (!items.length) return;
      panel.appendChild(el('strong', title));
      var ul = el('ul');
      items.forEach(function (t) { ul.appendChild(el('li', t)); });
      panel.appendChild(ul);
    }
    list('Dependencies', p.links);
    var names = function (ids) { return (ids || []).map(function (n) { return data[n] ? data[n].name : n; }); };
    if ((p.cut || []).length || (p.orphaned || []).length || (p.stops || []).length ||
        p.without_score !== undefined) {
      var box = el('div', undefined, 'whatif');
      box.appendChild(el('strong', 'If ' + p.name + ' is unavailable'));
      if (p.without_score !== undefined && p.without_score !== payload.score) {
        box.appendChild(el('div', 'Score ' + payload.score + ' \u2192 ' + p.without_score, 'score-drop'));
      }
      [['Cut off', names(p.cut)], ['No approver left for', p.orphaned || []],
       ['Stops', p.stops || []]].forEach(function (kv) {
        if (kv[1].length) box.appendChild(el('div', kv[0] + ': ' + kv[1].join(', ')));
      });
      panel.appendChild(box);
    }
    list('Findings', p.findings);
    if (map && focus !== false) {
      map.classList.add('focus');
      map.querySelectorAll('.is-on, .selected, .cut, .hint').forEach(function (n) { n.classList.remove('is-on', 'selected', 'cut', 'hint'); });
      map.querySelectorAll('.edge, .flow').forEach(function (e) {
        if (e.dataset.from === id || e.dataset.to === id) {
          e.classList.add('is-on');
          [e.dataset.from, e.dataset.to].forEach(function (n) {
            var node = map.querySelector('.node[data-id="' + CSS.escape(n) + '"]');
            if (node) node.classList.add('is-on');
          });
        }
      });
      var node = map.querySelector('.node[data-id="' + CSS.escape(id) + '"]');
      if (node) node.classList.add('is-on', 'selected');
      (p.cut || []).forEach(function (n) {
        var cut = map.querySelector('.node[data-id="' + CSS.escape(n) + '"]');
        if (cut) cut.classList.add('is-on', 'cut');
      });
      var island = new Set(p.cut || []);
      map.querySelectorAll('.edge, .flow').forEach(function (e) {
        if (island.has(e.dataset.from) && island.has(e.dataset.to)) e.classList.add('is-on', 'cut');
      });
    }
    document.querySelectorAll('.people tr.selected').forEach(function (r) { r.classList.remove('selected'); });
    var row = document.querySelector('.people tr[data-id="' + CSS.escape(id) + '"]');
    if (row) row.classList.add('selected');
  }
  document.querySelectorAll('.node').forEach(function (n) {
    n.addEventListener('click', function (ev) { ev.stopPropagation(); show(n.dataset.id); });
    n.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') show(n.dataset.id); });
  });
  if (map) map.addEventListener('click', function () {
    if (dragged) { dragged = false; return; }
    map.classList.remove('focus');
    map.querySelectorAll('.selected, .cut, .hint').forEach(function (n) { n.classList.remove('selected', 'cut', 'hint'); });
  });
  document.querySelectorAll('.fix[data-targets]').forEach(function (f) {
    function go() {
      var targets = JSON.parse(f.dataset.targets).filter(function (t) { return data[t]; });
      if (!targets.length || !map) return;
      show(targets[0]);
      var all = new Set(targets);
      targets.forEach(function (t) {
        var node = map.querySelector('.node[data-id="' + CSS.escape(t) + '"]');
        if (node) node.classList.add('is-on', 'hint');
      });
      map.querySelectorAll('.edge, .flow').forEach(function (e) {
        if (all.has(e.dataset.from) && all.has(e.dataset.to)) e.classList.add('is-on');
      });
      map.scrollIntoView({behavior: 'smooth', block: 'center'});
    }
    f.addEventListener('click', go);
    f.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') go(); });
  });
  var full = map ? map.viewBox.baseVal : null;
  var W = full ? full.width : 0, H = full ? full.height : 0;
  var view = {x: 0, y: 0, w: W, h: H}, drag = null, dragged = false;
  function setView(x, y, w) {
    w = Math.min(W, Math.max(W / 6, w));
    var h = w * H / W;
    view = {x: Math.min(Math.max(x, 0), W - w), y: Math.min(Math.max(y, 0), H - h), w: w, h: h};
    map.setAttribute('viewBox', [view.x, view.y, view.w, view.h].map(function (v) { return v.toFixed(1); }).join(' '));
  }
  function zoom(factor) {
    var cx = view.x + view.w / 2, cy = view.y + view.h / 2, w = view.w * factor;
    setView(cx - w / 2, cy - w * H / W / 2, w);
  }
  document.querySelectorAll('.zoom button').forEach(function (b) {
    b.addEventListener('click', function () {
      if (b.dataset.zoom === 'in') zoom(0.75);
      else if (b.dataset.zoom === 'out') zoom(1 / 0.75);
      else setView(0, 0, W);
    });
  });
  if (map) {
    map.addEventListener('pointerdown', function (ev) {
      if (view.w >= W || ev.target.closest('.node')) return;
      drag = {x: ev.clientX, y: ev.clientY, vx: view.x, vy: view.y};
    });
    map.addEventListener('pointermove', function (ev) {
      if (!drag) return;
      var k = view.w / map.getBoundingClientRect().width;
      var dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
      if (!dragged && Math.abs(dx) + Math.abs(dy) < 4) return;
      if (!dragged) { dragged = true; map.setPointerCapture(ev.pointerId); map.classList.add('panning'); }
      setView(drag.vx - dx * k, drag.vy - dy * k, view.w);
    });
    ['pointerup', 'pointercancel'].forEach(function (type) {
      map.addEventListener(type, function () {
        drag = null; map.classList.remove('panning');
        setTimeout(function () { dragged = false; }, 0);
      });
    });
  }
  document.querySelectorAll('.people tbody tr').forEach(function (r) {
    r.addEventListener('click', function () {
      show(r.dataset.id);
      if (map) map.scrollIntoView({behavior: 'smooth', block: 'center'});
    });
  });
  document.querySelectorAll('th[data-sort]').forEach(function (th, index) {
    var asc = th.dataset.sort === 'num';  // numbers sort high-to-low on the first click
    th.addEventListener('click', function () {
      var tbody = th.closest('table').querySelector('tbody');
      var rows = Array.prototype.slice.call(tbody.rows);
      asc = !asc;
      rows.sort(function (a, b) {
        var x = a.cells[index], y = b.cells[index];
        var r = th.dataset.sort === 'num'
          ? parseFloat(x.dataset.v) - parseFloat(y.dataset.v)
          : x.textContent.localeCompare(y.textContent);
        return asc ? r : -r;
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
    });
  });
  var printLink = document.getElementById('print');
  if (printLink) printLink.addEventListener('click', function (ev) { ev.preventDefault(); window.print(); });
  var ids = Object.keys(data).filter(function (id) { return data[id].impact > 0; });
  ids.sort(function (a, b) { return data[b].impact * data[b].criticality - data[a].impact * data[a].criticality; });
  if (ids.length) show(ids[0], false);
})();
"""

TEMPLATE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="human-risk-graph $version">
<title>$title</title>
<style>$css</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="brand">Human Risk Graph <span>· $input_name</span></div>
    <nav><a href="#fixes">Fixes</a><a href="#map">Map</a><a href="#people">People</a>
      <a href="#findings">Findings</a><a href="#method">Method</a><a href="#audit">Audit</a>
      <a href="#" id="print">Save as PDF</a></nav>
  </div>

  <section class="card hero">
    $ring
    <div>
      <div class="grade"><b style="background:$grade_color">$grade</b><span>$risk_level risk</span></div>
      <p class="verdict">$verdict</p>
      <p class="muted">$interpretation</p>
      $unconfirmed
      <div class="meta"><span>$size people</span><span>$deps dependencies</span>
        <span>$finding_summary</span><span>model $model</span><span>$generated</span></div>
    </div>
  </section>

  <section class="tiles">$tiles</section>

  <section class="card" id="fixes" style="margin-top:20px">
    <h2>Top fixes</h2>
    <p class="muted">Remediations simulated on your data, ranked by how much they raise the score.</p>
    $fixes
  </section>

  <section class="card" id="map">
    <h2>Dependency map</h2>
    <p class="muted">Who approves, escalates to and can bypass whom. Select a person for details.</p>
    $map
  </section>

  <section class="card" id="people">
    <h2>People</h2>
    $people
  </section>

  <section class="card" id="findings">
    <h2>Findings</h2>
    <p class="muted">$finding_summary, with related ISO/IEC 27001, SOC 2 and DORA controls.</p>
    $findings
  </section>

  <section class="card" id="method">
    <h2>How the score is calculated</h2>
    <p class="muted">Model $model.</p>
    $method
  </section>

  <section class="card" id="audit">
    <h2>Audit trail</h2>
    <p class="muted">Enough to reproduce this result.</p>
    $audit
  </section>

  <footer class="page">Generated by <a href="https://github.com/LF3551/human-risk-graph">Human Risk Graph</a>
    $version · <a href="https://doi.org/10.5281/zenodo.18288055">doi:10.5281/zenodo.18288055</a></footer>
</div>
<script type="application/json" id="hrg-data">$data</script>
<script>$js</script>
</body>
</html>
""")
