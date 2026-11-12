import json

from human_risk_graph.diff import compare, format_markdown, format_text, risk_increased

OLD = {
    "people": [
        {"id": "a", "criticality": 0.9},
        {"id": "b", "criticality": 0.5},
        {"id": "c", "criticality": 0.5},
    ],
    "dependencies": [
        {"from": "a", "to": "b", "type": "approval", "weight": 0.5},
        {"from": "a", "to": "c", "type": "approval", "weight": 0.5},
    ],
}

NEW = {
    "people": [
        {"id": "a", "criticality": 0.9},
        {"id": "b", "criticality": 0.5},
        {"id": "d", "criticality": 0.5},
    ],
    "dependencies": [
        {"from": "a", "to": "b", "type": "bypass", "weight": 0.9},
        {"from": "b", "to": "d", "type": "approval", "weight": 0.5},
    ],
}


def test_compare_structure():
    diff = compare(OLD, NEW)

    assert diff["people"]["added"] == ["d"]
    assert diff["people"]["removed"] == ["c"]
    assert diff["people"]["changed"] == []
    assert [(d["from"], d["to"]) for d in diff["dependencies"]["added"]] == [("b", "d")]
    assert [(d["from"], d["to"]) for d in diff["dependencies"]["removed"]] == [("a", "c")]
    [changed] = diff["dependencies"]["changed"]
    assert changed["old"]["type"] == "approval" and changed["new"]["type"] == "bypass"
    assert diff["single_points_of_failure"] == {"introduced": ["b"], "resolved": ["a"]}
    json.dumps(diff)


def test_identical_snapshots():
    diff = compare(OLD, OLD)
    assert all(m["delta"] == 0 for m in diff["metrics"].values())
    assert not risk_increased(diff)
    assert "No structural changes." in format_text(diff)
    assert "No structural changes." in format_markdown(diff)


def test_risk_increased_ignores_float_noise():
    diff = compare(OLD, OLD)
    diff["metrics"]["composite_score"]["delta"] = 1e-12
    assert not risk_increased(diff)
    diff["metrics"]["composite_score"]["delta"] = 0.01
    assert risk_increased(diff)


def test_formats_list_changes():
    diff = compare(OLD, NEW)
    text = format_text(diff)
    markdown = format_markdown(diff)

    for line in ("+ person d", "- person c", "+ single point of failure b"):
        assert line in text
        assert line in markdown
    assert "~ dependency a -> b (approval, 0.50) => a -> b (bypass, 0.90)" in text
    assert markdown.startswith("## Human Risk Graph changes")
    assert "```diff" in markdown
