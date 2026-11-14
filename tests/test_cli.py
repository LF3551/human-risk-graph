import io
import json
import re
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from human_risk_graph import __version__
from human_risk_graph.cli import _tolerate_encoding, cli


def test_non_utf8_console_does_not_crash():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    _tolerate_encoding([stream])
    stream.write("Score \u2588\u2588\u2591 \u00b7 \u25b2 HRG001")
    stream.flush()
    assert raw.getvalue() == "Score ??? \u00b7 ? HRG001".encode("cp1252")


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


def test_confirmed_only_score(tmp_path):
    path = tmp_path / "org.yaml"
    path.write_text(
        "people:\n"
        "  - {id: boss, criticality: 0.9}\n"
        "  - {id: dev}\n"
        "  - {id: ops}\n"
        "dependencies:\n"
        "  - {from: boss, to: dev, type: approval, weight: 1.0}\n"
        "  - {from: ops, to: boss, type: bypass, confirmed: false}\n"
    )
    result = run("analyze", path, "--format", "json", "--no-visualize", "--fixes", "0")
    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "org_report.json").read_text())
    only = report["metadata"]["confirmed_only"]
    assert only["dependencies"] == 1
    assert only["score"] > report["results"]["score"]
    assert f"On confirmed data only: {only['score']}/100" in " ".join(result.output.split())

    path.write_text(path.read_text().replace(", confirmed: false", ""))
    run("analyze", path, "--format", "json", "--no-visualize", "--fixes", "0")
    report = json.loads((tmp_path / "org_report.json").read_text())
    assert report["metadata"]["confirmed_only"] is None


FUNCTIONS = Path(__file__).resolve().parent.parent / "examples" / "functions.yaml"


def test_model_v3_end_to_end(tmp_path):
    path = tmp_path / "functions.yaml"
    shutil.copy(FUNCTIONS, path)
    result = run(
        "analyze", path, "--model", "hrg-3", "--format", "all", "--format", "sarif",
        "--format", "junit", "--no-visualize",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    output = " ".join(result.output.split())
    assert "model hrg-3" in output
    assert "Solo control 2 of 3 critical functions" in output
    assert "1 more can by policy" in output
    assert "integrity" in output

    report = json.loads((tmp_path / "functions_report.json").read_text())
    assert report["results"]["model"] == "hrg-3"
    assert {f["rule_id"] for f in report["findings"]} == {"HRG002", "HRG005", "HRG006", "HRG007"}
    assert "(by policy)" in (tmp_path / "functions_report.md").read_text()
    assert "## 🔑 Critical Functions" in (tmp_path / "functions_report.md").read_text()
    html = (tmp_path / "functions_report.html").read_text()
    assert "Critical functions" in html and "Functions lost" in html
    assert '<span class="muted">(by policy)</span>' in html

    lines = path.read_text().splitlines()
    sarif = json.loads((tmp_path / "functions_report.sarif").read_text())
    for res in sarif["runs"][0]["results"]:
        if res["ruleId"] in ("HRG005", "HRG006"):
            line = lines[res["locations"][0]["physicalLocation"]["region"]["startLine"] - 1]
            assert line.strip().startswith("- id:"), line
    junit = (tmp_path / "functions_report.junit.xml").read_text()
    assert 'tests="5"' in junit and "HRG006" in junit and "HRG001" not in junit


def test_model_v3_needs_functions(org):
    result = run("analyze", org, "--model", "hrg-3", "--format", "json", "--no-visualize")
    assert result.exit_code == 1
    assert "needs a 'functions' section" in result.output


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
    assert "is above the threshold 0.200" in result.output
    sarif = json.loads((org.parent / "org_report.sarif").read_text())
    assert sarif["runs"][0]["results"][-1]["ruleId"] == "HRG004"
    assert (org.parent / "org_report.junit.xml").exists()
    assert not (org.parent / "org_report.json").exists()


def test_summary_shows_score_and_fixes(org):
    result = run("analyze", org, "--format", "json", "--no-visualize")

    assert result.exit_code == 0, result.output
    assert "52/100" in result.output
    assert "D · Moderate risk" in result.output
    assert "Top fixes" in result.output
    assert "52 → 60" in result.output
    report = json.loads((org.parent / "org_report.json").read_text())
    assert report["results"]["score"] == 52
    assert len(report["fix_plan"]) == 3


def test_min_score_and_quiet(org):
    result = run("analyze", org, "--format", "json", "--no-visualize", "-q", "--min-score", "70")

    assert result.exit_code == 3
    assert result.output.strip() == "Error: Score 52 is below the minimum 70."

    result = run("analyze", org, "--format", "json", "--no-visualize", "-q", "--min-score", "50")
    assert result.exit_code == 0
    assert result.output == ""


def test_model_v1_and_no_fixes(org):
    result = run(
        "analyze", org, "--format", "json", "--no-visualize", "--model", "hrg-1", "--fixes", "0"
    )

    assert result.exit_code == 0, result.output
    assert "model hrg-1" in result.output
    assert "Top fixes" not in result.output
    report = json.loads((org.parent / "org_report.json").read_text())
    assert round(report["results"]["composite_score"], 3) == 0.269
    assert report["fix_plan"] == []


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


def test_graph_tooltips_are_plain_text(tmp_path):
    # vis-network renders string titles with innerText: markup would show literally.
    path = tmp_path / "org.yaml"
    path.write_text(
        "people:\n"
        "  - {id: a, name: '<script>x</script>', role: Lead, criticality: 0.9}\n"
        "  - {id: b}\n"
        "  - {id: c}\n"
        "dependencies:\n"
        "  - {from: b, to: a, type: approval}\n"
        "  - {from: a, to: c, type: approval}\n"
        "  - {from: c, to: a, type: bypass}\n"
    )

    result = run("visualize", path)

    assert result.exit_code == 0, result.output
    html = (tmp_path / "org_graph.html").read_text(encoding="utf-8")
    nodes = json.loads(re.search(r"nodes = new vis\.DataSet\((\[.*?\])\);", html).group(1))
    edges = json.loads(re.search(r"edges = new vis\.DataSet\((\[.*?\])\);", html).group(1))
    titles = [item["title"] for item in nodes + edges]
    assert all("<br>" not in t and "<b>" not in t for t in titles)
    lead = next(n for n in nodes if n["id"] == "a")
    assert lead["title"].splitlines()[:2] == ["<script>x</script>", "ID: a"]
    assert "Role: Lead" in lead["title"] and "CRITICAL NODE" in lead["title"]
    bypass = next(e for e in edges if e["from"] == "c")
    assert bypass["title"].splitlines() == [
        "Bypass Route",
        "From: c",
        "To: <script>x</script>",
        "Type: bypass",
        "Weight: 0.50",
    ]
    assert "<script>x</script>" not in html  # names are JSON-escaped inside the page


def test_yaml_id_must_be_string(tmp_path):
    path = tmp_path / "org.yaml"
    path.write_text("people:\n  - id: 1\ndependencies: []\n")

    result = run("analyze", path, "--format", "json", "--no-visualize")

    assert result.exit_code == 1
    assert "people[0].id must be a non-empty string" in result.output


def test_diff(org, tmp_path):
    data = json.loads(org.read_text())
    anna = next(p for p in data["people"] if p["id"] == "anna.mueller")
    anna["criticality"] = 0.95  # the main single point of failure becomes more critical
    new = tmp_path / "new.json"
    new.write_text(json.dumps(data))

    result = run("diff", org, new, "--format", "markdown")
    assert result.exit_code == 0, result.output
    assert "~ person anna.mueller: criticality 0.85 => 0.95" in result.output
    assert "| **Score** | 52 (D) |" in result.output

    result = run("diff", org, new, "--fail-on-increase")
    assert result.exit_code == 3

    result = run("diff", new, org, "--fail-on-increase", "--format", "json")
    assert result.exit_code == 0
    assert json.loads(result.output)["metrics"]["composite_score"]["delta"] < 0


def test_schema_command():
    result = run("schema")
    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "Human Risk Graph organization"
