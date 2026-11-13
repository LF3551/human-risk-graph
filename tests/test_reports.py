"""
Unit tests for report generation consistency.
"""

import json

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
    report = generate_html_report(results, _metadata(), fixes=fixes)

    assert "Weight: 40%" in report
    assert "Weight: 30%" in report
    assert f"GRADE {results['grade']}" in report
    assert f"model {model}" in report


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
    assert "Ivan Petrov (Site Reliability Engineer)" in report
