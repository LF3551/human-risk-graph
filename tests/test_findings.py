import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from human_risk_graph import HumanRiskGraph
from human_risk_graph.ci_reports import generate_junit_report, generate_sarif_report
from human_risk_graph.findings import FRAMEWORKS, RULES, collect_findings
from human_risk_graph.loader import load_organization

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "data" / "example_organization.json"
YAML_EXAMPLE = ROOT / "examples" / "organization.yaml"


def analyze(path, fail_above=None):
    data = load_organization(path)
    hrg = HumanRiskGraph(data["people"], data["dependencies"])
    results = hrg.calculate()
    return hrg, results, collect_findings(hrg, results, fail_above)


def test_example_findings():
    _, results, findings = analyze(EXAMPLE)
    keys = [f.key for f in findings]

    assert keys == [
        "HRG001:anna.mueller",
        "HRG001:ines.silva",
        "HRG001:johan.lindberg",
        "HRG001:luca.rossi",
        "HRG001:marie.dubois",
        "HRG002:luca.rossi",
        "HRG003:elena.popescu->anna.mueller",
        "HRG003:luca.rossi->carlos.garcia",
        "HRG003:marie.dubois->carlos.garcia",
    ]
    # Single points of failure at or above the critical threshold are errors.
    assert [f.level for f in findings[:5]] == ["error", "warning", "warning", "error", "error"]
    assert "44% of the approval weight" in findings[5].message


def test_critical_single_point_of_failure_is_error():
    people = [{"id": "a"}, {"id": "hub", "criticality": 0.9}, {"id": "b"}]
    deps = [{"from": "a", "to": "hub"}, {"from": "hub", "to": "b"}]
    hrg = HumanRiskGraph(people, deps)

    findings = collect_findings(hrg, hrg.calculate())

    assert [(f.rule_id, f.level, f.person) for f in findings] == [("HRG001", "error", "hub")]


def test_break_glass_bypass_finding():
    people = [{"id": "boss", "criticality": 0.9}, {"id": "dev"}, {"id": "ops"}]
    deps = [
        {"from": "boss", "to": "dev", "type": "approval"},
        {"from": "ops", "to": "boss", "type": "bypass", "review": "after"},
    ]
    hrg = HumanRiskGraph(people, deps)
    [finding] = [f for f in collect_findings(hrg, hrg.calculate()) if f.rule_id == "HRG003"]
    assert "break-glass" in finding.message


def test_threshold_finding():
    _, results, findings = analyze(EXAMPLE, fail_above=0.2)
    assert findings[-1].rule_id == "HRG004"
    assert findings[-1].level == "error"

    _, _, findings = analyze(EXAMPLE, fail_above=0.9)
    assert all(f.rule_id != "HRG004" for f in findings)


def test_every_rule_maps_to_all_frameworks():
    for rule in RULES.values():
        assert set(rule.controls) == set(FRAMEWORKS), rule.id
        assert all(ref and title for refs in rule.controls.values() for ref, title in refs)


def test_finding_to_dict():
    _, _, findings = analyze(EXAMPLE)
    d = findings[6].to_dict()
    assert d["dependency"] == {"from": "elena.popescu", "to": "anna.mueller"}
    assert {"id": "A.5.3", "title": "Segregation of duties"} in d["controls"]["iso27001"]


@pytest.mark.parametrize("path", [EXAMPLE, YAML_EXAMPLE], ids=lambda p: p.suffix)
def test_sarif_points_at_the_right_lines(path):
    _, _, findings = analyze(path, fail_above=0.0)
    text = path.read_text()
    log = json.loads(generate_sarif_report(findings, path.name, text))
    run = log["runs"][0]
    lines = text.splitlines()

    assert log["version"] == "2.1.0"
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == list(RULES)
    for finding, result in zip(findings, run["results"]):
        assert run["tool"]["driver"]["rules"][result["ruleIndex"]]["id"] == result["ruleId"]
        line = lines[result["locations"][0]["physicalLocation"]["region"]["startLine"] - 1]
        if finding.dependency:
            assert finding.dependency[0] in line
        elif finding.person:
            assert finding.person in line
        assert result["partialFingerprints"]["hrgFinding/v1"] == finding.key


def test_sarif_rule_metadata():
    log = json.loads(generate_sarif_report([], "org.json", ""))
    rule = log["runs"][0]["tool"]["driver"]["rules"][0]
    assert "dora/Art.10(1)" in rule["properties"]["tags"]
    assert "ISO/IEC 27001:2022" in rule["help"]["markdown"]
    assert log["runs"][0]["results"] == []


def test_junit_report():
    _, results, findings = analyze(EXAMPLE)
    root = ET.fromstring(generate_junit_report(findings, results))
    suite = root.find("testsuite")
    cases = {c.get("name").split()[0]: c for c in suite.findall("testcase")}

    assert suite.get("tests") == "4"
    assert suite.get("failures") == "3"
    assert suite.get("skipped") == "1"
    assert cases["HRG001"].find("failure").get("type") == "error"
    assert cases["HRG004"].find("skipped") is not None


def test_junit_report_passes_without_findings():
    hrg = HumanRiskGraph([{"id": "a"}], [])
    results = hrg.calculate()
    root = ET.fromstring(generate_junit_report([], results, fail_above=0.5))
    assert root.get("failures") == "0"
    assert root.find("testsuite").get("skipped") == "0"
