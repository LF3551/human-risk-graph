import json

from human_risk_graph import gha

REPORT = {
    "metadata": {
        "input_name": "org|<x>.yaml",
        "organization_size": 5,
        "dependencies_count": 6,
        "unconfirmed_dependencies": 2,
        "confirmed_only": {"score": 61, "grade": "D", "dependencies": 4},
        "coverage_gaps": ["Members of team @acme/core are not visible."],
    },
    "results": {
        "score": 25,
        "grade": "F",
        "risk_level": "Critical",
        "model": "hrg-2",
        "bus_factor": 0.6,
        "decision_concentration": 0.59,
        "bypass_risk": 0.67,
    },
    "findings": [
        {"rule_id": "HRG001", "level": "error", "message": "Alice | is a <b>key</b> person"},
        {"rule_id": "HRG002", "level": "warning", "message": "Concentrated"},
        {"rule_id": "HRG003", "level": "warning", "message": "Bypass", "accepted": True},
    ],
    "fix_plan": [{"title": "Add a deputy for Alice", "score_before": 25, "score_after": 45}],
}


def test_outputs():
    assert gha.outputs(REPORT) == ("score=25\ngrade=F\nrisk-level=Critical\nerrors=1\nwarnings=1\n")


def test_summary():
    text = gha.summary(REPORT)
    assert text.startswith("## Human Risk Graph: 25/100 \u00b7 grade F \u00b7 Critical risk")
    assert "`org\\|&lt;x&gt;.yaml` \u00b7 5 people \u00b7 6 dependencies" in text
    assert "2 of 6 dependencies are unconfirmed; on confirmed data only the score is 61/100" in text
    assert "1 data gap:" in text
    assert "| Key-person risk | 0.60 |" in text
    assert "**Findings:** 1 errors \u00b7 1 warnings \u00b7 1 accepted" in text
    assert "| error | HRG001 | Alice \\| is a &lt;b&gt;key&lt;/b&gt; person |" in text
    assert "Bypass" not in text
    assert "1. Add a deputy for Alice: 25 \u2192 45" in text


def test_summary_minimal_and_truncated():
    findings = [{"rule_id": "HRG001", "level": "warning", "message": f"m{i}"} for i in range(12)]
    text = gha.summary({"results": {"score": 90, "grade": "A"}, "findings": findings})
    assert "[!WARNING]" not in text and "[!NOTE]" not in text
    assert "2 more in the full report." in text
    assert "Top fixes" not in text


def test_main(tmp_path, capsys):
    path = tmp_path / "r.json"
    path.write_text(json.dumps(REPORT))
    assert gha.main(["outputs", str(path)]) == 0
    assert capsys.readouterr().out.startswith("score=25\n")
    assert gha.main(["nope"]) == 2
