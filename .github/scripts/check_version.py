"""Fail if the package, CITATION.cff, .zenodo.json and (optionally) the release tag disagree.

Usage: python .github/scripts/check_version.py [TAG]
"""

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def package_version() -> str:
    tree = ast.parse((ROOT / "src/human_risk_graph/__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets
        ):
            return node.value.value
    sys.exit("__version__ not found in src/human_risk_graph/__init__.py")


def citation_versions() -> list:
    return re.findall(
        r"^\s*version:\s*\"?([^\s\"]+)", (ROOT / "CITATION.cff").read_text(encoding="utf-8"), re.M
    )


def main() -> None:
    expected = package_version()
    found = {"src/human_risk_graph/__init__.py": expected}
    for i, v in enumerate(citation_versions()):
        found[f"CITATION.cff (version #{i + 1})"] = v
    found[".zenodo.json"] = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))[
        "version"
    ]
    if len(sys.argv) > 1:
        found["release tag"] = sys.argv[1].removeprefix("v")

    mismatched = {k: v for k, v in found.items() if v != expected}
    for k, v in found.items():
        print(f"{'OK  ' if v == expected else 'FAIL'} {k}: {v}")
    if mismatched:
        sys.exit(f"Version mismatch: expected {expected} everywhere")


if __name__ == "__main__":
    main()
