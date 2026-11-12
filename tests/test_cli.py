import json

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
