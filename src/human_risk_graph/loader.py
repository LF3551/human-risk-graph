"""Load organization data from JSON or YAML files."""

import json
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Union

import yaml

YAML_SUFFIXES = {".yaml", ".yml"}
SCHEMA_URL = (
    "https://raw.githubusercontent.com/LF3551/human-risk-graph/main/"
    "src/human_risk_graph/organization.schema.json"
)


def load_organization(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Read an organization file with ``people`` and ``dependencies``.

    Files ending in ``.yaml`` or ``.yml`` are parsed as YAML, everything else as JSON.
    The content itself is validated by ``HumanRiskGraph``.

    Raises:
        ValueError: If the file cannot be parsed or lacks the two top-level keys.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    is_yaml = path.suffix.lower() in YAML_SUFFIXES
    try:
        data = yaml.safe_load(text) if is_yaml else json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise ValueError(f"{path}: invalid {'YAML' if is_yaml else 'JSON'}: {e}") from e

    if not isinstance(data, dict) or "people" not in data or "dependencies" not in data:
        raise ValueError(f"{path}: expected an object with 'people' and 'dependencies' keys")
    # YAML reads an unquoted 2026-03-01 as a date; keep it as text like JSON does.
    for person in data["people"] if isinstance(data["people"], list) else []:
        if isinstance(person, dict) and isinstance(person.get("last_active"), date):
            person["last_active"] = person["last_active"].isoformat()
    return data


def organization_schema() -> str:
    """Return the JSON Schema for organization files."""
    return (
        resources.files("human_risk_graph")
        .joinpath("organization.schema.json")
        .read_text(encoding="utf-8")
    )
