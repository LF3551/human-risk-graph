import json
from pathlib import Path

import pytest

from human_risk_graph.loader import load_organization, organization_schema

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = [ROOT / "data" / "example_organization.json", ROOT / "examples" / "organization.yaml"]


def test_load_json_and_yaml_agree(tmp_path):
    data = {"people": [{"id": "a"}], "dependencies": []}
    (tmp_path / "org.json").write_text(json.dumps(data))
    (tmp_path / "org.yml").write_text("people:\n  - id: a\ndependencies: []\n")

    assert load_organization(tmp_path / "org.json") == data
    assert load_organization(tmp_path / "org.yml") == data


@pytest.mark.parametrize(
    "name, content, message",
    [
        ("org.json", "{not json", "invalid JSON"),
        ("org.yaml", "people: [", "invalid YAML"),
        ("org.json", "[]", "expected an object"),
        ("org.yaml", "people: []\n", "expected an object"),
    ],
)
def test_load_rejects_malformed_files(tmp_path, name, content, message):
    path = tmp_path / name
    path.write_text(content)
    with pytest.raises(ValueError, match=message):
        load_organization(path)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_examples_match_schema(path):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(load_organization(path), json.loads(organization_schema()))


@pytest.mark.parametrize(
    "data",
    [
        {"people": [{"id": 1}], "dependencies": []},
        {"people": [{"id": "a", "criticality": 2}], "dependencies": []},
        {"people": [{"id": "a"}], "dependencies": [{"from": "a"}]},
        {"people": [{"id": "a"}], "dependencies": [{"from": "a", "to": "a", "weight": -1}]},
        {"people": []},
    ],
)
def test_schema_rejects_invalid_data(data):
    jsonschema = pytest.importorskip("jsonschema")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, json.loads(organization_schema()))


def test_schema_is_draft_07_with_published_id():
    schema = json.loads(organization_schema())
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["$id"].endswith("/src/human_risk_graph/organization.schema.json")
