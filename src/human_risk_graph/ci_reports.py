"""SARIF and JUnit XML output for CI pipelines."""

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from . import __version__
from .findings import FRAMEWORKS, RULES, Finding, Rule, acceptance_text

INFORMATION_URI = "https://github.com/LF3551/human-risk-graph"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def _key_value(key: str, value: str) -> "re.Pattern[str]":
    """Match ``key: value`` in JSON or YAML, with optional quotes."""
    return re.compile(rf"\b{key}[\"']?\s*:\s*[\"']?{re.escape(value)}[\"']?(?![\w.@-])")


def _find_line(lines: List[str], finding: Finding) -> int:
    """Best-effort 1-based line of the person or dependency the finding is about."""
    if finding.dependency:
        source = _key_value("from", finding.dependency[0])
        target = _key_value("to", finding.dependency[1])
        for i, line in enumerate(lines):
            if not source.search(line):
                continue
            if target.search(line):
                return i + 1
            # YAML block style: "to" follows on the next lines of the same item.
            for nxt in lines[i + 1 : i + 5]:
                if re.match(r"\s*-\s", nxt) or "from" in nxt:
                    break
                if target.search(nxt):
                    return i + 1
    if finding.person:
        person = _key_value("id", finding.person)
        for i, line in enumerate(lines):
            if person.search(line):
                return i + 1
    return 1


def _controls_lines(rule: Rule, bold: bool = False) -> List[str]:
    lines = []
    for fw, refs in rule.controls.items():
        name = f"**{FRAMEWORKS[fw]}:**" if bold else f"{FRAMEWORKS[fw]}:"
        lines.append(f"- {name} " + "; ".join(f"{ref} {title}" for ref, title in refs))
    return lines


def _sarif_rule(rule: Rule) -> Dict[str, Any]:
    tags = ["human-risk"] + [
        f"{fw}/{ref.replace(' ', '')}" for fw, refs in rule.controls.items() for ref, _ in refs
    ]
    help_text = "\n".join(
        [rule.description, "", f"Remediation: {rule.remediation}", "", "Related controls:"]
        + _controls_lines(rule)
    )
    help_markdown = "\n".join(
        [
            rule.description,
            "",
            f"**Remediation:** {rule.remediation}",
            "",
            "**Related controls** (informative, not a compliance assessment):",
            "",
        ]
        + _controls_lines(rule, bold=True)
    )
    return {
        "id": rule.id,
        "name": rule.name,
        "shortDescription": {"text": rule.title},
        "fullDescription": {"text": rule.description},
        "help": {"text": help_text, "markdown": help_markdown},
        "helpUri": f"{INFORMATION_URI}/blob/main/docs/compliance.md",
        "properties": {"tags": tags},
    }


def generate_sarif_report(findings: List[Finding], artifact_uri: str, source_text: str) -> str:
    """
    Build a SARIF 2.1.0 log, for example for GitHub code scanning.

    Args:
        findings: Findings from ``collect_findings``.
        artifact_uri: Path of the analysed file, relative to the repository root.
        source_text: Content of the analysed file, used to point results at the right line.
    """
    rules = list(RULES.values())
    rule_index = {rule.id: i for i, rule in enumerate(rules)}
    lines = source_text.splitlines()

    results = []
    for f in findings:
        result = {
            "ruleId": f.rule_id,
            "ruleIndex": rule_index[f.rule_id],
            "level": f.level,
            "message": {"text": f.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": artifact_uri},
                        "region": {"startLine": _find_line(lines, f)},
                    }
                }
            ],
            "partialFingerprints": {"hrgFinding/v1": f.key},
        }
        if f.accepted:
            result["suppressions"] = [
                {"kind": "external", "status": "accepted", "justification": acceptance_text(f)}
            ]
        results.append(result)

    log = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Human Risk Graph",
                        "version": __version__,
                        "informationUri": INFORMATION_URI,
                        "rules": [_sarif_rule(rule) for rule in rules],
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(log, indent=2, ensure_ascii=False)


def generate_junit_report(
    findings: List[Finding],
    results: Dict[str, Any],
    fail_above: Optional[float] = None,
    min_score: Optional[int] = None,
) -> str:
    """
    Build a JUnit XML report with one test case per rule.

    A rule's test case fails when the analysis produced findings for it that are not covered
    by a risk acceptance. The threshold rule (HRG004) is skipped when neither ``fail_above``
    nor ``min_score`` was given.
    """
    suite = ET.Element("testsuite", name="human-risk-graph")
    props = ET.SubElement(suite, "properties")
    for key in ("model", "score", "grade", "risk_level"):
        ET.SubElement(props, "property", name=key, value=str(results.get(key)))
    for key in ("composite_score", "bus_factor", "decision_concentration", "bypass_risk"):
        ET.SubElement(props, "property", name=key, value=f"{results[key]:.3f}")

    failures = skipped = 0
    for rule in RULES.values():
        case = ET.SubElement(
            suite, "testcase", classname="human-risk-graph", name=f"{rule.id} {rule.name}"
        )
        rule_findings = [f for f in findings if f.rule_id == rule.id and not f.accepted]
        accepted = [f for f in findings if f.rule_id == rule.id and f.accepted]
        if accepted:
            ET.SubElement(case, "system-out").text = "\n".join(
                f"Accepted: {f.message} ({acceptance_text(f)})" for f in accepted
            )
        if rule.id == "HRG004" and fail_above is None and min_score is None:
            ET.SubElement(case, "skipped", message="No --fail-above or --min-score threshold set")
            skipped += 1
        elif rule_findings:
            failures += 1
            level = "error" if any(f.level == "error" for f in rule_findings) else "warning"
            failure = ET.SubElement(
                case,
                "failure",
                message=f"{len(rule_findings)} finding(s): {rule.title}",
                type=level,
            )
            failure.text = "\n".join(
                [f"[{f.level}] {f.message}" for f in rule_findings]
                + ["", f"Remediation: {rule.remediation}"]
            )

    counts = {"tests": str(len(RULES)), "failures": str(failures), "errors": "0"}
    suite.attrib.update({**counts, "skipped": str(skipped)})
    root = ET.Element("testsuites", name="human-risk-graph", **counts)
    root.append(suite)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"
