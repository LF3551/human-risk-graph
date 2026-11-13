import json
import shutil
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from human_risk_graph.cli import cli
from human_risk_graph.config import (
    Acceptance,
    ConfigError,
    apply_acceptances,
    load_config,
    parse_config,
)
from human_risk_graph.findings import Finding

EXAMPLE = Path(__file__).resolve().parent.parent / "data" / "example_organization.json"
BYPASS = 'rule = "HRG003"\ntarget = "luca.rossi->carlos.garcia"\nreason = "Break-glass"\n'


def run(*args):
    return CliRunner().invoke(cli, [str(a) for a in args])


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    shutil.copy(EXAMPLE, tmp_path / "org.json")
    monkeypatch.chdir(tmp_path)
    return tmp_path


# Loading and validation


def test_no_config_is_empty(tmp_path):
    config = load_config(directory=tmp_path)
    assert config.path is None and config.accept == [] and config.calculate_kwargs() == {}


def test_hrg_toml_wins_over_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.hrg]\nmin-score = 50\n")
    assert load_config(directory=tmp_path).min_score == 50
    (tmp_path / "hrg.toml").write_text("min-score = 80\n")
    assert load_config(directory=tmp_path).min_score == 80


def test_full_config(tmp_path):
    (tmp_path / "hrg.toml").write_text(
        'model = "hrg-1"\nmin-score = 70\nfail-above = 0.4\nfixes = 5\n'
        "critical-threshold = 0.6\n"
        "[weights]\nkey-person = 0.5\nconcentration = 0.25\noverride = 0.25\n"
        f'[[accept]]\n{BYPASS}ticket = "SEC-1"\nexpires = 2027-03-01\n'
    )
    config = load_config(directory=tmp_path)
    assert (config.model, config.min_score, config.fail_above, config.fixes) == (
        "hrg-1",
        70,
        0.4,
        5,
    )
    assert config.calculate_kwargs() == {
        "alpha": 0.5, "beta": 0.25, "gamma": 0.25, "critical_threshold": 0.6,
    }  # fmt: skip
    assert config.accept == [
        Acceptance("HRG003", "Break-glass", "luca.rossi->carlos.garcia", "SEC-1", date(2027, 3, 1))
    ]


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"min-scor": 70}, "unknown key"),
        ({"model": "hrg-9"}, "model must be"),
        ({"min-score": 170}, "min-score must be"),
        ({"weights": {"key-person": 1.0}}, "needs all of"),
        ({"weights": {"key-person": 0.5, "concentration": 0.5, "override": 0.5}}, "add up to 1"),
        ({"accept": [{"rule": "HRG009", "reason": "x"}]}, "rule must be one of"),
        ({"accept": [{"rule": "HRG001"}]}, "reason is required"),
        ({"accept": [{"rule": "HRG001", "reason": "x", "expires": "2027-01-01"}]}, "unquoted"),
        ({"accept": [{"rule": "HRG001", "reason": "x", "owner": "me"}]}, "unknown key"),
    ],
)
def test_invalid_config(raw, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(raw, Path("hrg.toml"))


# Acceptances


def test_apply_acceptances():
    findings = [
        Finding("HRG001", "warning", "spof", person="a"),
        Finding("HRG003", "warning", "bypass", person="x", dependency=("x", "y")),
    ]
    accept = [
        Acceptance("HRG003", "ok", target="x->y", expires=date(2026, 1, 1)),
        Acceptance("HRG002", "unused"),
        Acceptance("HRG001", "all spofs"),
    ]
    result, unused = apply_acceptances(findings, accept, today=date(2026, 6, 1))

    assert result[0].accepted
    assert result[1].acceptance is not None and result[1].acceptance_expired
    assert not result[1].accepted
    assert unused == [accept[1]]
    assert result[0].to_dict()["acceptance"]["reason"] == "all spofs"


# CLI


def test_config_sets_threshold_and_cli_overrides_it(workdir):
    (workdir / "hrg.toml").write_text("min-score = 70\n")
    assert run("analyze", "org.json", "--format", "json", "--no-visualize", "-q").exit_code == 3
    result = run(
        "analyze", "org.json", "--format", "json", "--no-visualize", "-q", "--min-score", "50"
    )
    assert result.exit_code == 0, result.output


def test_accepted_findings_in_every_output(workdir):
    (workdir / "hrg.toml").write_text(f'[[accept]]\n{BYPASS}ticket = "SEC-123"\n')

    result = run("analyze", "org.json", "--format", "all", "--format", "sarif", "--format", "junit",
                 "--no-visualize")  # fmt: skip

    assert result.exit_code == 0, result.output
    output = " ".join(result.output.split())  # undo terminal wrapping
    assert "config hrg.toml" in output
    assert "1 accepted" in output
    sarif = json.loads((workdir / "org_report.sarif").read_text())
    suppressed = [r for r in sarif["runs"][0]["results"] if "suppressions" in r]
    assert len(suppressed) == 1
    assert suppressed[0]["suppressions"][0]["justification"] == "Break-glass; SEC-123"
    report = json.loads((workdir / "org_report.json").read_text())
    assert sum(f["accepted"] for f in report["findings"]) == 1
    assert report["metadata"]["config_file"] == "hrg.toml"
    assert "## ✅ Accepted Risks" in (workdir / "org_report.md").read_text()
    assert "Accepted risks" in (workdir / "org_report.html").read_text()
    junit = ET.fromstring((workdir / "org_report.junit.xml").read_text())
    case = next(c for c in junit.iter("testcase") if c.get("name").startswith("HRG003"))
    assert "Accepted:" in case.find("system-out").text
    assert "2 finding(s)" in case.find("failure").get("message")


def test_accepted_threshold_breach_passes_until_it_expires(workdir):
    (workdir / "hrg.toml").write_text(
        'min-score = 70\n[[accept]]\nrule = "HRG004"\nreason = "Hiring a deputy in Q1"\n'
        "expires = 2999-01-01\n"
    )
    assert run("analyze", "org.json", "--format", "json", "--no-visualize", "-q").exit_code == 0

    (workdir / "hrg.toml").write_text(
        'min-score = 70\n[[accept]]\nrule = "HRG004"\nreason = "Hiring a deputy in Q1"\n'
        "expires = 2020-01-01\n"
    )
    result = run("analyze", "org.json", "--format", "json", "--no-visualize", "-q")
    assert result.exit_code == 3
    assert "expired on 2020-01-01" in result.output


def test_unused_acceptance_warns(workdir):
    (workdir / "hrg.toml").write_text(
        '[[accept]]\nrule = "HRG003"\ntarget = "a->b"\nreason = "x"\n'
    )
    result = run("analyze", "org.json", "--format", "json", "--no-visualize", "-q")
    assert result.exit_code == 0
    assert "matches no finding" in result.output


def test_config_weights_change_the_score(workdir):
    base = run("analyze", "org.json", "--format", "json", "--no-visualize", "-q")
    assert base.exit_code == 0
    score = json.loads((workdir / "org_report.json").read_text())["results"]["score"]
    (workdir / "hrg.toml").write_text(
        "[weights]\nkey-person = 0.8\nconcentration = 0.1\noverride = 0.1\n"
    )
    run("analyze", "org.json", "--format", "json", "--no-visualize", "-q")
    results = json.loads((workdir / "org_report.json").read_text())["results"]
    assert results["weights"] == {"alpha": 0.8, "beta": 0.1, "gamma": 0.1}
    assert results["score"] != score


def test_invalid_config_is_an_error(workdir):
    (workdir / "hrg.toml").write_text("min-score = [\n")
    result = run("analyze", "org.json", "--no-visualize", "-q")
    assert result.exit_code == 1
    assert "invalid TOML" in result.output


def test_explicit_config_path(workdir):
    (workdir / "ci.toml").write_text("min-score = 99\n")
    result = run(
        "analyze", "org.json", "--format", "json", "--no-visualize", "-q", "--config", "ci.toml"
    )
    assert result.exit_code == 3
