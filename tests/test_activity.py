"""Last activity, inactive performers (HRG007) and their configuration."""

import json
from datetime import date

import pytest
from click.testing import CliRunner

from human_risk_graph import HumanRiskGraph
from human_risk_graph.activity import (
    NEVER,
    activity_text,
    is_inactive,
    latest,
    parse_activity,
)
from human_risk_graph.cli import cli
from human_risk_graph.config import ConfigError, parse_config
from human_risk_graph.findings import collect_findings, rules_for_model
from human_risk_graph.loader import load_organization
from human_risk_graph.privacy import Pseudonymizer

TODAY = date(2026, 11, 14)
RECENT = "2026-11-01"
OLD = "2026-05-01"  # more than 90 days before TODAY


# activity.py


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ("2026-03-01", date(2026, 3, 1)),
        ("2026-03-01T10:00:00Z", date(2026, 3, 1)),
        (date(2026, 3, 1), date(2026, 3, 1)),
        (NEVER, NEVER),
    ],
)
def test_parse_activity(value, expected):
    assert parse_activity(value) == expected


@pytest.mark.parametrize("value", ["yesterday", "2026-13-01", 20260301, True, ""])
def test_parse_activity_rejects(value):
    with pytest.raises(ValueError, match="2026-03-01"):
        parse_activity(value)


def test_is_inactive():
    assert is_inactive(OLD, 90, TODAY)
    assert not is_inactive(RECENT, 90, TODAY)
    assert is_inactive(NEVER, 90, TODAY)
    assert not is_inactive(None, 90, TODAY)  # unknown is not evidence of absence
    assert not is_inactive("2026-08-16", 90, TODAY)  # exactly 90 days: not over
    assert is_inactive("2026-08-15", 90, TODAY)


def test_latest_and_text():
    assert latest([NEVER, "2026-01-01T00:00:00Z", "2025-05-05", None]) == "2026-01-01"
    assert latest([NEVER, None]) == NEVER
    assert latest([None]) is None
    assert activity_text(OLD) == f"last active {OLD}"
    assert activity_text(NEVER) == "no activity seen"


# HRG007


def _org(functions, activity):
    people = [{"id": pid, **({"last_active": a} if a else {})} for pid, a in activity.items()]
    return HumanRiskGraph(people, [], functions)


def _hrg007(functions, activity, days=90, model="hrg-3"):
    hrg = _org(functions, activity)
    results = hrg.calculate(model=model)
    found = collect_findings(hrg, results, inactive_days=days, today=TODAY)
    return [f for f in found if f.rule_id == "HRG007"]


def test_redundancy_on_paper_is_a_warning():
    found = _hrg007(
        [{"id": "merge", "criticality": 0.8, "requires": 2, "performers": ["a", "b", "c"]}],
        {"a": RECENT, "b": RECENT, "c": OLD},
    )
    assert len(found) == 1
    assert found[0].level == "warning"
    assert found[0].person == "c" and found[0].function == "merge"
    assert found[0].message == (
        f"merge: c (last active {OLD}) has been inactive for over 90 days; "
        "its margin drops from 2 to 1."
    )


def test_dormant_publisher_of_a_one_person_function_is_an_error():
    # Anyone who may publish alone can do so from a dormant, possibly taken-over account.
    found = _hrg007(
        [{"id": "release", "criticality": 0.9, "performers": ["a", "b"]}],
        {"a": RECENT, "b": OLD},
    )
    assert [f.level for f in found] == ["error"]
    assert found[0].message == (
        f"release: b (last active {OLD}) has been inactive for over 90 days; its margin "
        "drops from 2 to 1. b can still complete it alone, which makes that account an "
        "easy target."
    )


def test_function_nobody_active_can_perform_is_an_error():
    found = _hrg007(
        [{"id": "merge", "criticality": 0.8, "requires": 2, "performers": ["a", "b", "c"]}],
        {"a": RECENT, "b": OLD, "c": NEVER},
    )
    assert [f.level for f in found] == ["error"]
    assert found[0].person is None
    assert "b (last active 2026-05-01) and c (no activity seen) have been inactive" in (
        found[0].message
    )
    assert "it needs 2 people and only 1 person active can perform it" in found[0].message


def test_dormant_account_that_can_act_alone_is_an_error():
    found = _hrg007(
        [
            {
                "id": "deploy",
                "criticality": 0.9,
                "requires": 2,
                "performers": ["a", "b", "c"],
                "alone": ["admin"],
            }
        ],
        {"a": RECENT, "b": RECENT, "c": RECENT, "admin": OLD},
    )
    assert [f.level for f in found] == ["error"]
    assert "admin can still complete it alone, which makes that account an easy target" in (
        found[0].message
    )


def test_policy_functions_and_low_criticality_are_warnings():
    policy = {
        "id": "restore",
        "criticality": 0.9,
        "separation": "not-required",
        "performers": ["a", "b"],
        "alone": ["b"],
    }
    found = _hrg007([policy], {"a": RECENT, "b": OLD})
    assert [f.level for f in found] == ["warning"]
    assert "alone" not in found[0].message

    minor = {"id": "docs", "criticality": 0.3, "performers": ["a"]}
    assert [f.level for f in _hrg007([minor], {"a": OLD})] == ["warning"]


def test_no_finding_without_evidence_of_inactivity():
    functions = [{"id": "release", "criticality": 0.9, "performers": ["a", "b"]}]
    assert _hrg007(functions, {"a": RECENT, "b": None}) == []
    assert _hrg007(functions, {"a": RECENT, "b": OLD}, days=365) == []
    assert _hrg007(functions, {"a": OLD, "b": OLD}, model="hrg-2") == []


def test_hrg007_is_a_hrg3_rule():
    assert "HRG007" in [r.id for r in rules_for_model("hrg-3")]
    assert "HRG007" not in [r.id for r in rules_for_model("hrg-2")]


def test_last_active_is_validated():
    with pytest.raises(ValueError, match=r"people\[0\]\.last_active must be a date"):
        HumanRiskGraph([{"id": "a", "last_active": "last week"}], [])


def test_yaml_dates_are_read_as_text(tmp_path):
    path = tmp_path / "org.yaml"
    path.write_text(
        "people:\n  - {id: a, last_active: 2026-03-01}\n  - {id: b, last_active: never}\n"
        "dependencies: []\n"
    )
    people = load_organization(path)["people"]
    assert [p["last_active"] for p in people] == ["2026-03-01", NEVER]


def test_pseudonymization_keeps_last_active():
    data = {"people": [{"id": "alice", "name": "Alice", "last_active": OLD}], "dependencies": []}
    person = Pseudonymizer(b"k" * 16).organization(data)["people"][0]
    assert person["last_active"] == OLD and person["name"] != "Alice"


# Configuration and CLI


def test_config_inactive_days(tmp_path):
    assert parse_config({"inactive-days": 30}, tmp_path / "hrg.toml").inactive_days == 30
    with pytest.raises(ConfigError, match="inactive-days"):
        parse_config({"inactive-days": 0}, tmp_path / "hrg.toml")


ORG = f"""
people:
  - {{id: a, last_active: {RECENT}}}
  - {{id: b, last_active: 2020-01-01}}
dependencies: []
functions:
  - {{id: release, criticality: 0.9, performers: [a, b]}}
"""


def test_cli_inactive_days_from_option_and_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "org.yaml").write_text(ORG)
    args = ["analyze", "org.yaml", "--model", "hrg-3", "--format", "json", "--no-visualize"]

    def inactivity(*extra):
        result = CliRunner().invoke(cli, [*args, *extra])
        assert result.exit_code == 0, result.output
        report = json.loads((tmp_path / "org_report.json").read_text())
        return [f["message"] for f in report["findings"] if f["rule_id"] == "HRG007"]

    assert "inactive for over 90 days" in inactivity()[0]
    assert inactivity("--inactive-days", "3650") == []  # 2020-01-01 is within ten years
    (tmp_path / "hrg.toml").write_text("inactive-days = 3650\n")
    assert inactivity() == []
    assert "inactive for over 30 days" in inactivity("--inactive-days", "30")[0]  # CLI wins

    junit_args = ["analyze", "org.yaml", "--model", "hrg-3", "--format", "junit", "--no-visualize"]
    result = CliRunner().invoke(cli, junit_args)
    assert 'tests="5"' in (tmp_path / "org_report.junit.xml").read_text(), result.output


# Hint outside hrg-3


def test_inactivity_hint():
    from human_risk_graph.cli import inactivity_hint

    data = {"people": [{"id": "a", "last_active": "2020-01-01"}, {"id": "b"}], "dependencies": []}
    assert inactivity_hint(data, "hrg-2", 90) == (
        "Note: 1 person has no activity seen for over 90 days (last_active)."
    )
    data["functions"] = [{"id": "release", "performers": ["a"]}]
    assert "run with --model hrg-3 to see which functions rely on them (HRG007)" in (
        inactivity_hint(data, "hrg-1", 90)
    )
    assert inactivity_hint(data, "hrg-3", 90) is None  # HRG007 reports it there
    assert inactivity_hint({"people": [{"id": "b"}]}, "hrg-2", 90) is None


def test_cli_shows_the_hint_under_the_default_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "org.yaml").write_text(ORG)
    args = ["analyze", "org.yaml", "--format", "json", "--no-visualize"]
    output = CliRunner().invoke(cli, args).output
    assert "Note: 1 person has no activity seen for over 90 days" in output
    assert "--model hrg-3" in output
    assert "Note:" not in CliRunner().invoke(cli, [*args, "-q"]).output
    assert "Note:" not in CliRunner().invoke(cli, [*args, "--model", "hrg-3"]).output
