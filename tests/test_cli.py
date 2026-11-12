import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from human_risk_graph import __version__
from human_risk_graph.cli import cli


def test_version_matches_package():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_invalid_input_fails(tmp_path):
    data = {
        "people": [{"id": "A", "criticality": 0.9}],
        "dependencies": [{"from": "A", "to": "Z", "type": "bypass", "weight": 0.5}],
    }
    path = tmp_path / "org.json"
    path.write_text(json.dumps(data))

    result = CliRunner().invoke(cli, ["analyze", str(path), "--format", "json", "--no-visualize"])

    assert result.exit_code == 1
    assert "unknown person id 'Z'" in result.output
    assert not (tmp_path / "org_report.json").exists()


EXAMPLE = Path(__file__).resolve().parent.parent / "data" / "example_organization.json"


def run(*args):
    return CliRunner().invoke(cli, [str(a) for a in args])


@pytest.fixture
def org(tmp_path):
    path = tmp_path / "org.json"
    shutil.copy(EXAMPLE, path)
    return path


def test_ci_formats_and_threshold(org):
    result = run(
        "analyze",
        org,
        "--format",
        "sarif",
        "--format",
        "junit",
        "--no-visualize",
        "--fail-above",
        "0.2",
    )

    assert result.exit_code == 3, result.output
    assert "above --fail-above 0.200" in result.output
    sarif = json.loads((org.parent / "org_report.sarif").read_text())
    assert sarif["runs"][0]["results"][-1]["ruleId"] == "HRG004"
    assert (org.parent / "org_report.junit.xml").exists()
    assert not (org.parent / "org_report.json").exists()


def test_below_threshold_passes(org):
    result = run("analyze", org, "--format", "json", "--no-visualize", "--fail-above", "0.5")

    assert result.exit_code == 0, result.output
    report = json.loads((org.parent / "org_report.json").read_text())
    assert [f["rule_id"] for f in report["findings"]].count("HRG003") == 3


def test_all_plus_sarif(org):
    result = run("analyze", org, "--format", "all", "--format", "sarif", "--no-visualize")

    assert result.exit_code == 0, result.output
    for ext in (".json", ".md", ".html", ".sarif"):
        assert (org.parent / f"org_report{ext}").exists(), ext
    assert "Findings and Related Controls" in (org.parent / "org_report.md").read_text()


def test_html_report_escapes_names(tmp_path):
    path = tmp_path / "org.yaml"
    path.write_text(
        "people:\n"
        "  - {id: a, name: '<script>x</script>', criticality: 0.9}\n"
        "  - {id: b}\n"
        "  - {id: c}\n"
        "dependencies:\n"
        "  - {from: b, to: a}\n"
        "  - {from: a, to: c}\n"
    )

    result = run("analyze", path, "--format", "html", "--no-visualize")

    assert result.exit_code == 0, result.output
    html = (tmp_path / "org_report.html").read_text()
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_yaml_id_must_be_string(tmp_path):
    path = tmp_path / "org.yaml"
    path.write_text("people:\n  - id: 1\ndependencies: []\n")

    result = run("analyze", path, "--format", "json", "--no-visualize")

    assert result.exit_code == 1
    assert "people[0].id must be a non-empty string" in result.output


def test_diff(org, tmp_path):
    data = json.loads(org.read_text())
    ines = next(p for p in data["people"] if p["id"] == "ines.silva")
    ines["criticality"] = 0.95  # a single point of failure becomes more critical
    new = tmp_path / "new.json"
    new.write_text(json.dumps(data))

    result = run("diff", org, new, "--format", "markdown")
    assert result.exit_code == 0, result.output
    assert "~ person ines.silva: criticality 0.55 => 0.95" in result.output

    result = run("diff", org, new, "--fail-on-increase")
    assert result.exit_code == 3

    result = run("diff", new, org, "--fail-on-increase", "--format", "json")
    assert result.exit_code == 0
    assert json.loads(result.output)["metrics"]["composite_score"]["delta"] < 0


def test_schema_command():
    result = run("schema")
    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "Human Risk Graph organization"
