"""
Unit tests for report generation consistency.
"""

import html
import json
import math
import re

import pytest

from human_risk_graph import HumanRiskGraph
from human_risk_graph.reports import (
    generate_html_report,
    generate_json_report,
    generate_markdown_report,
)

PEOPLE = [
    {"id": "A", "name": "Ivan Petrov", "role": "Site Reliability Engineer", "criticality": 0.9},
    {"id": "B", "criticality": 0.4},
    {"id": "C", "criticality": 0.4},
    {"id": "D", "criticality": 0.8},
]
DEPENDENCIES = [
    {"from": "A", "to": "B", "type": "approval", "weight": 0.9},
    {"from": "A", "to": "C", "type": "approval", "weight": 0.6},
    {"from": "D", "to": "A", "type": "bypass", "weight": 0.7},
]


def _metadata():
    return {
        "input_file": "data/example_organization.json",
        "analysis_date": "2026-02-25T10:00:00",
        "organization_size": 4,
        "dependencies_count": 3,
        "person_lookup": {
            "A": {"name": "Ivan Petrov", "role": "Site Reliability Engineer", "criticality": 0.9}
        },
    }


def _analyze(model="hrg-2"):
    hrg = HumanRiskGraph(PEOPLE, DEPENDENCIES)
    return hrg.calculate(model=model), hrg.fix_plan(model=model)


def test_markdown_v2_summary_and_metrics():
    results, fixes = _analyze()
    report = generate_markdown_report(results, _metadata(), fixes=fixes)

    assert f"**Score: {results['score']}/100 · grade {results['grade']}" in report
    assert "| **Key-person risk** | " in report
    assert "| **Approval concentration** | 1.000 | 30%" in report
    assert "1.0 effective approvers of 1; Ivan Petrov holds 100% of the approval weight" in report
    assert "2 of 2 critical approvals can be overridden" in report
    assert "## 🛠️ Top Fixes" in report
    assert "Add a deputy for Ivan Petrov" in report


def test_markdown_v1_keeps_original_formula():
    results, _ = _analyze("hrg-1")
    report = generate_markdown_report(results, _metadata())

    assert "| **Bus factor risk** | " in report
    assert "0.4·BF + 0.3·DC + 0.3·BR" in report
    assert "Top Fixes" not in report


@pytest.mark.parametrize("model", ["hrg-2", "hrg-1"])
def test_html_report(model):
    results, fixes = _analyze(model)
    hrg = HumanRiskGraph(PEOPLE, DEPENDENCIES)
    report = generate_html_report(results, _metadata(), fixes=fixes, hrg=hrg)

    assert "weight 40%" in report
    assert "weight 30%" in report
    assert f">{results['grade']}</b>" in report
    assert f"model {model}" in report
    assert f'aria-label="Score {results["score"]} of 100"' in report
    assert len(re.findall(r'<g class="node[ "]', report)) == len(PEOPLE)
    assert 'class="edge edge-bypass"' in report


def test_html_report_is_self_contained():
    results, fixes = _analyze()
    report = generate_html_report(
        results, _metadata(), fixes=fixes, hrg=HumanRiskGraph(PEOPLE, DEPENDENCIES)
    )

    assert "<script src" not in report
    assert "<link" not in report
    assert "@import" not in report


def test_html_report_escapes_input_everywhere():
    people = [{"id": "x", "name": "</script><img src=x onerror=alert(1)>", "criticality": 0.9},
              {"id": "y"}, {"id": "z"}]  # fmt: skip
    deps = [{"from": "y", "to": "x"}, {"from": "x", "to": "z", "type": "<b>bad</b>"}]
    hrg = HumanRiskGraph(people, deps)
    results = hrg.calculate()
    metadata = {"input_name": "<org>.json", "organization_size": 3, "dependencies_count": 2}

    report = generate_html_report(results, metadata, hrg=hrg)

    assert "<img src=x" not in report
    assert "</script><img" not in report
    assert "<b>bad</b>" not in report
    assert "<org>" not in report
    data = report.split('id="hrg-data">')[1].split("</script>")[0]
    assert json.loads(data)["people"]["x"]["name"].startswith("</script>")


@pytest.mark.parametrize(
    "confirmed_only, expected",
    [
        ({"score": 61, "grade": "D", "dependencies": 2}, "<strong>61/100</strong> (grade D, 2"),
        (None, None),  # metadata from before 0.9.0
    ],
)
def test_html_report_unconfirmed_notice(confirmed_only, expected):
    results, _ = _analyze()
    metadata = {**_metadata(), "unconfirmed_dependencies": 1, "confirmed_only": confirmed_only}
    report = generate_html_report(results, metadata)

    assert "1 of 3 dependencies are unconfirmed" in report
    if expected:
        assert expected in report
    else:
        assert "On confirmed data only" not in report


def test_html_report_panel_data():
    results, _ = _analyze()
    report = generate_html_report(results, _metadata(), hrg=HumanRiskGraph(PEOPLE, DEPENDENCIES))
    people = json.loads(report.split('id="hrg-data">')[1].split("</script>")[0])["people"]

    assert people["A"]["spof"] is True
    assert "Approves B" in people["A"]["links"]
    assert "Can be bypassed by D" in people["A"]["links"]
    assert people["A"]["share"] == 1.0
    # A is the only link between B and C (a tie: either counts as cut off, as in the model);
    # the bypass from D does not hold anyone in.
    assert len(people["A"]["cut"]) == 1 and people["A"]["cut"][0] in ("B", "C")
    assert people["B"]["cut"] == []


def test_html_report_animates_flow_direction():
    results, _ = _analyze()
    report = generate_html_report(results, _metadata(), hrg=HumanRiskGraph(PEOPLE, DEPENDENCIES))
    edges = report.count('<line class="edge ')
    assert edges == len(DEPENDENCIES)
    assert report.count('<line class="flow ') == edges
    assert 'class="flow flow-bypass" data-from="D" data-to="A"' in report
    assert "prefers-reduced-motion: reduce" in report


def test_html_report_edges_explain_themselves_on_hover():
    results, _ = _analyze()
    report = generate_html_report(results, _metadata(), hrg=HumanRiskGraph(PEOPLE, DEPENDENCIES))
    assert report.count('<line class="edge-hit"') == len(DEPENDENCIES)
    assert "<title>Ivan Petrov approves B · weight 0.90</title>" in report
    assert "<title>D can bypass Ivan Petrov · weight 0.70</title>" in report


def test_html_report_what_if_hrg2():
    results, _ = _analyze()
    report = generate_html_report(results, _metadata(), hrg=HumanRiskGraph(PEOPLE, DEPENDENCIES))
    data = json.loads(report.split('id="hrg-data">')[1].split("</script>")[0])
    assert data["score"] == results["score"]
    assert data["people"]["A"]["orphaned"] == ["B", "C"]  # A is their only approver
    assert data["people"]["D"]["orphaned"] == []  # a bypass is not an approval


def test_html_report_what_if_hrg3():
    people = [{"id": i, "criticality": 0.5} for i in ("a", "b", "c")]
    functions = [
        {"id": "merge", "name": "Merge", "criticality": 0.9, "performers": ["a"]},
        {"id": "release", "criticality": 0.8, "requires": 2, "performers": ["a", "b", "c"]},
    ]
    hrg = HumanRiskGraph(people, [], functions)
    results = hrg.calculate(model="hrg-3")
    fixes = hrg.fix_plan(model="hrg-3")
    report = generate_html_report(results, _metadata(), fixes=fixes, hrg=hrg)
    data = json.loads(report.split('id="hrg-data">')[1].split("</script>")[0])

    assert data["people"]["a"]["stops"] == ["Merge"]
    assert data["people"]["a"]["without_score"] < results["score"]
    assert "without_score" not in data["people"]["b"]
    # A backup for merge points at its performers on the map.
    assert 'data-targets="[&quot;a&quot;]"' in report


def test_html_report_fixes_point_at_the_map():
    results, fixes = _analyze()
    report = generate_html_report(
        results, _metadata(), fixes=fixes, hrg=HumanRiskGraph(PEOPLE, DEPENDENCIES)
    )
    targets = [
        json.loads(html.unescape(t.split('"')[0]))
        for t in report.split('class="fix" data-targets="')[1:]
    ]
    assert len(targets) == len(fixes)
    # A simulated deputy ("A~deputy") is shown as the person they stand in for.
    assert targets == [["A"], ["D", "A"], ["D", "A"]]


def test_map_layout_spreads_nodes_and_labels():
    from human_risk_graph.html_report import _overlap, _place_labels, _spread

    crowded = {str(i): (400 + i * 0.5, 300 + (i % 3)) for i in range(12)}
    spread = _spread(crowded)
    pts = list(spread.values())
    closest = min(math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1 :])  # noqa: E203
    assert closest > 60
    same = _spread({"a": (400, 300), "b": (400, 300)})
    assert same["a"] != same["b"]

    names = {n: f"Person number {n}" for n in spread}
    labels = _place_labels(sorted(spread), names, spread, {n: 10 for n in spread}, [])
    boxes = []
    for n, (x, y, anchor) in labels.items():
        w = len(names[n]) * 7.6
        left = {"middle": x - w / 2, "start": x, "end": x - w}[anchor]
        boxes.append((left, y - 12, left + w, y + 4))
    overlaps = sum(
        1 for i, a in enumerate(boxes) for b in boxes[i + 1 :] if _overlap(a, b)  # noqa: E203
    )
    assert overlaps <= 1


def test_json_report_includes_fix_plan():
    results, fixes = _analyze()
    report = json.loads(generate_json_report(results, _metadata(), fixes=fixes))
    assert report["results"]["model"] == "hrg-2"
    assert report["fix_plan"][0]["score_after"] > report["fix_plan"][0]["score_before"]


def test_markdown_displays_human_friendly_critical_people():
    results, _ = _analyze()
    report = generate_markdown_report(results, _metadata())
    assert "Ivan Petrov (Site Reliability Engineer)" in report


def test_html_displays_human_friendly_critical_people():
    results, _ = _analyze()
    report = generate_html_report(results, _metadata())
    assert "Ivan Petrov" in report
    assert "Site Reliability Engineer" in report


def test_map_is_not_drawn_for_large_organizations():
    from human_risk_graph import HumanRiskGraph
    from human_risk_graph.html_report import MAP_LIMIT, _map_html

    n = MAP_LIMIT + 1
    people = [{"id": f"p{i}"} for i in range(n)]
    deps = [{"from": f"p{i - 1}", "to": f"p{i}", "type": "approval"} for i in range(1, n)]
    html = _map_html(HumanRiskGraph(people, deps), {})
    assert f"has {n}" in html and "<svg" not in html
