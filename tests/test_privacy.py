"""Pseudonymization: no identifying data in reports, stable keyed pseudonyms, re-identification."""

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from human_risk_graph.cli import cli
from human_risk_graph.config import Acceptance, parse_config, ConfigError
from human_risk_graph.privacy import (
    KEY_ENV,
    PREFIX,
    Pseudonymizer,
    PseudonymKeyError,
    load_key,
)

KEY = b"k" * 32
ORG = {
    "coverage": {
        "source": "github acme/api",
        "review_required": True,
        "gaps": ["Members of team @acme/core are not visible; kept as one node.",
                 "alice.smith can bypass rules"],
    },
    "people": [
        {"id": "alice.smith", "name": "Alice Smith", "role": "CTO", "criticality": 0.9,
         "email": "alice@acme.example", "evidence": "approved 9 PRs by bob", "source": "github"},
        {"id": "bob", "name": "Bob Jones", "role": "Developer", "criticality": 0.4},
        {"id": "@acme/core", "criticality": 0.5},
    ],
    "dependencies": [
        {"from": "alice.smith", "to": "bob", "type": "approval", "weight": 0.8,
         "evidence": "approved 8 of 10 merged PRs by bob", "confirmed": False},
        {"from": "@acme/core", "to": "bob", "type": "approval", "weight": 0.4},
        {"from": "bob", "to": "alice.smith", "type": "bypass", "weight": 1.0,
         "review": "after"},
    ],
    "functions": [
        {"id": "release", "name": "Publish a release", "criticality": 0.9,
         "performers": ["alice.smith"], "evidence": "published 30 releases: alice.smith"},
        {"id": "merge", "requires": 2, "performers": ["alice.smith", "bob"],
         "alone": ["alice.smith"], "separation": "required"},
    ],
}  # fmt: skip
IDENTIFYING = ("alice", "Alice", "Smith", "bob", "Bob", "Jones", "CTO", "acme/core", "@acme")


def _no_identifiers(text):
    # Whole words only: the bundled graph library contains e.g. "aliceblue" and base64 data.
    leaks = [w for w in IDENTIFYING if re.search(rf"(?<![\w+/]){re.escape(w)}(?![\w+/])", text)]
    assert not leaks, f"identifying text in output: {leaks}"


# Pseudonymizer


def test_pseudonyms_are_keyed_stable_and_distinct():
    a, b = Pseudonymizer(KEY), Pseudonymizer(KEY)
    ids = ["alice.smith", "bob", "@acme/core"]
    assert a.learn(ids) == b.learn(reversed(ids))
    assert len(set(a.mapping.values())) == 3
    assert all(p.startswith(PREFIX) and len(p) == len(PREFIX) + 8 for p in a.mapping.values())
    assert Pseudonymizer(b"other-key-0123456789").learn(ids) != a.mapping


def test_without_a_key_pseudonyms_change():
    first, second = Pseudonymizer(), Pseudonymizer()
    assert not first.stable
    assert first.learn(["alice"]) != second.learn(["alice"])


def test_collisions_get_longer_pseudonyms(monkeypatch):
    pz = Pseudonymizer(KEY)
    monkeypatch.setattr(pz, "_digest", lambda pid: "abcdef0123456789" + pid.encode().hex())
    mapping = pz.learn(["x", "y"])
    assert mapping["x"] == "P-abcdef01"
    assert mapping["y"] == "P-abcdef012345"


def test_organization_keeps_structure_and_drops_identifying_fields():
    pz = Pseudonymizer(KEY)
    out = pz.organization(ORG)
    alice, bob, team = (pz.person(i) for i in ("alice.smith", "bob", "@acme/core"))

    assert out["people"][0] == {
        "id": alice, "name": alice, "criticality": 0.9, "source": "github",
    }  # fmt: skip
    assert [(d["from"], d["to"], d["type"]) for d in out["dependencies"]] == [
        (alice, bob, "approval"), (team, bob, "approval"), (bob, alice, "bypass"),
    ]  # fmt: skip
    assert out["dependencies"][0] == {
        "from": alice, "to": bob, "type": "approval", "weight": 0.8, "confirmed": False,
    }  # fmt: skip
    assert out["dependencies"][2]["review"] == "after"
    assert out["functions"][1] == {
        "id": "merge", "requires": 2, "performers": [alice, bob], "alone": [alice],
        "separation": "required",
    }  # fmt: skip
    assert "evidence" not in out["functions"][0]
    assert out["coverage"]["gaps"] == [
        f"Members of team {team} are not visible; kept as one node.",
        f"{alice} can bypass rules",
    ]
    _no_identifiers(json.dumps(out))
    assert ORG["people"][0]["name"] == "Alice Smith"  # the input is not modified


def test_scrub_replaces_ids_and_names_as_whole_words():
    pz = Pseudonymizer(KEY)
    pz.organization(ORG)
    alice, bob = pz.person("alice.smith"), pz.person("bob")
    assert pz.scrub("Alice Smith and @bob agreed") == f"{alice} and {bob} agreed"
    assert pz.scrub("bobcat and bob.") == f"bobcat and {bob}."
    assert pz.scrub("bob-org.yaml, alice.smith_report") == f"{bob}-org.yaml, {alice}_report"
    assert pz.scrub("") == ""


def test_acceptances_follow_the_pseudonyms():
    pz = Pseudonymizer(KEY)
    pz.organization(ORG)
    accepted = pz.acceptances(
        [
            Acceptance(
                rule="HRG003", reason="Break-glass for Bob Jones", target="bob->alice.smith"
            ),
            Acceptance(rule="HRG006", reason="ok", target="merge"),
            Acceptance(rule="HRG002", reason="ok"),
        ]
    )
    assert accepted[0].target == f"{pz.person('bob')}->{pz.person('alice.smith')}"
    assert accepted[0].reason == f"Break-glass for {pz.person('bob')}"
    assert (accepted[1].target, accepted[2].target) == ("merge", None)


def test_load_key(tmp_path, monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    assert load_key() is None
    monkeypatch.setenv(KEY_ENV, "  " + "s" * 20 + "\n")
    assert load_key() == b"s" * 20
    path = tmp_path / "key"
    path.write_text("f" * 32 + "\n")
    assert load_key(path) == b"f" * 32
    monkeypatch.setenv(KEY_ENV, "short")
    with pytest.raises(PseudonymKeyError, match="at least 16 characters"):
        load_key()


def test_config_setting():
    assert parse_config({"pseudonymize": True}, Path("hrg.toml")).pseudonymize is True
    with pytest.raises(ConfigError, match="pseudonymize must be true or false"):
        parse_config({"pseudonymize": "yes"}, Path("hrg.toml"))


# Command line


@pytest.fixture
def org_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(KEY_ENV, "0123456789abcdef0123456789abcdef")
    path = tmp_path / "org.json"
    path.write_text(json.dumps(ORG, indent=2))
    return path


def test_analyze_pseudonymized_reports_identify_nobody(org_file):
    (org_file.parent / "hrg.toml").write_text(
        '[[accept]]\nrule = "HRG003"\ntarget = "bob->alice.smith"\nreason = "Reviewed by Bob Jones"\n'
    )
    result = CliRunner().invoke(
        cli,
        ["analyze", str(org_file), "--pseudonymize", "--format", "all", "--format", "sarif",
         "--format", "junit"],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "Privacy: People are pseudonymized" in result.output
    _no_identifiers(result.output.replace(str(org_file), ""))

    reports = {p.suffix: p.read_text() for p in org_file.parent.glob("org_*")}
    assert set(reports) == {".json", ".md", ".html", ".sarif", ".xml"}
    for name, text in reports.items():
        _no_identifiers(text)
    report = json.loads(reports[".json"])
    assert report["metadata"]["pseudonymized"] == {"method": "HMAC-SHA256", "stable": True}
    assert any(f["accepted"] for f in report["findings"])  # the acceptance still matched
    assert "**Privacy:** People are pseudonymized" in reports[".md"]

    sarif = json.loads(reports[".sarif"])
    lines = org_file.read_text().splitlines()
    for res in sarif["runs"][0]["results"]:
        line = res["locations"][0]["physicalLocation"]["region"]["startLine"]
        assert line > 1, res["message"]["text"]  # located in the original file
        assert "P-" in res["message"]["text"] or res["ruleId"] in ("HRG004", "HRG006")
    assert lines  # the SARIF points into the file, which keeps its own ids


def test_pseudonyms_are_stable_across_runs_and_match_the_table(org_file):
    runner = CliRunner()
    args = ["analyze", str(org_file), "--pseudonymize", "--format", "json", "--no-visualize", "-q"]
    first = runner.invoke(cli, args)
    report_one = (org_file.parent / "org_report.json").read_text()
    runner.invoke(cli, args)
    report_two = (org_file.parent / "org_report.json").read_text()
    assert first.exit_code == 0
    people = lambda r: json.loads(r)["metadata"]["person_lookup"].keys()  # noqa: E731
    assert people(report_one) == people(report_two)

    table = runner.invoke(cli, ["pseudonyms", str(org_file)])
    assert table.exit_code == 0
    rows = [line.split(",") for line in table.output.strip().splitlines()]
    assert rows[0] == ["pseudonym", "id", "name"]
    assert {r[0] for r in rows[1:]} == set(people(report_one))
    assert ["alice.smith", "Alice Smith"] in [r[1:] for r in rows]


def test_pseudonymize_from_config_and_override(org_file):
    (org_file.parent / "hrg.toml").write_text("pseudonymize = true\n")
    runner = CliRunner()
    base = ["analyze", str(org_file), "--format", "json", "--no-visualize", "-q"]
    assert runner.invoke(cli, base).exit_code == 0
    _no_identifiers((org_file.parent / "org_report.json").read_text())
    assert runner.invoke(cli, [*base, "--no-pseudonymize"]).exit_code == 0
    assert "Alice Smith" in (org_file.parent / "org_report.json").read_text()


def test_without_key_warns_and_pseudonyms_command_refuses(org_file, monkeypatch):
    monkeypatch.delenv(KEY_ENV)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["analyze", str(org_file), "--pseudonymize", "--format", "json", "--no-visualize"]
    )
    assert result.exit_code == 0
    assert "no pseudonym key" in result.output
    assert (
        json.loads((org_file.parent / "org_report.json").read_text())["metadata"]["pseudonymized"][
            "stable"
        ]
        is False
    )
    refused = runner.invoke(cli, ["pseudonyms", str(org_file)])
    assert refused.exit_code == 1 and f"set {KEY_ENV}" in refused.output


def test_input_file_name_is_pseudonymized(org_file):
    named = org_file.parent / "bob-org.json"
    named.write_text(org_file.read_text())
    result = CliRunner().invoke(
        cli, ["analyze", str(named), "--pseudonymize", "--format", "all", "--no-visualize", "-q"]
    )
    assert result.exit_code == 0, result.output
    reports = [p for p in org_file.parent.iterdir() if "_report." in p.name]
    assert len(reports) == 3
    for report in reports:
        _no_identifiers(report.name)
        _no_identifiers(report.read_text())


def test_bad_key_is_an_error(org_file, monkeypatch):
    monkeypatch.setenv(KEY_ENV, "short")
    result = CliRunner().invoke(cli, ["analyze", str(org_file), "--pseudonymize", "-q"])
    assert result.exit_code == 1 and "at least 16 characters" in result.output


def test_diff_and_visualize_pseudonymized(org_file):
    runner = CliRunner()
    new = org_file.parent / "new.json"
    changed = json.loads(org_file.read_text())
    changed["people"].append({"id": "carol", "name": "Carol King", "criticality": 0.6})
    changed["dependencies"].append({"from": "carol", "to": "bob", "type": "approval"})
    new.write_text(json.dumps(changed))
    result = runner.invoke(cli, ["diff", str(org_file), str(new), "--pseudonymize"])
    assert result.exit_code == 0, result.output
    _no_identifiers(result.output)
    assert "Carol" not in result.output and "carol" not in result.output

    graph = org_file.parent / "graph.html"
    result = runner.invoke(
        cli, ["visualize", str(org_file), "--output", str(graph), "--pseudonymize"]
    )
    assert result.exit_code == 0, result.output
    _no_identifiers(graph.read_text())
