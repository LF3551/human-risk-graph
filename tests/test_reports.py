"""
Unit tests for report generation consistency.
"""

from src.reports import generate_markdown_report, generate_html_report


def _sample_results():
    return {
        "bus_factor": 0.2,
        "decision_concentration": 0.3,
        "bypass_risk": 0.4,
        "composite_score": 0.45,
        "risk_level": "Moderate",
        "critical_nodes": ["A"],
        "articulation_points": ["A"],
    }


def _sample_metadata():
    return {
        "input_file": "data/example_organization.json",
        "analysis_date": "2026-02-25T10:00:00",
        "organization_size": 5,
        "dependencies_count": 6,
        "person_lookup": {
            "A": {
                "name": "Ivan Petrov",
                "role": "Site Reliability Engineer",
            }
        },
    }


def test_markdown_uses_aligned_metric_weights():
    report = generate_markdown_report(_sample_results(), _sample_metadata())
    assert "| **Bus Factor Risk** | 0.200 | 40%" in report
    assert "| **Decision Concentration** | 0.300 | 30%" in report
    assert "| **Bypass Risk** | 0.400 | 30%" in report


def test_markdown_uses_risk_level_from_results():
    report = generate_markdown_report(_sample_results(), _sample_metadata())
    assert "**Risk Level:** 🟢 **MODERATE**" in report


def test_html_uses_aligned_metric_weights():
    report = generate_html_report(_sample_results(), _sample_metadata())
    assert "Weight: 40%" in report
    assert "Weight: 30%" in report


def test_markdown_displays_human_friendly_critical_people():
    report = generate_markdown_report(_sample_results(), _sample_metadata())
    assert "Ivan Petrov (Site Reliability Engineer)" in report


def test_html_displays_human_friendly_critical_people():
    report = generate_html_report(_sample_results(), _sample_metadata())
    assert "Ivan Petrov (Site Reliability Engineer)" in report
