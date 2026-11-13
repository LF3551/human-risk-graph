"""
GitHub Actions helpers: a job summary and step outputs from a JSON report.

    python -m human_risk_graph.gha summary REPORT.json >> "$GITHUB_STEP_SUMMARY"
    python -m human_risk_graph.gha outputs REPORT.json >> "$GITHUB_OUTPUT"
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from .reports import _metric_labels, unconfirmed_text

MAX_FINDINGS = 10
METRIC_KEYS = ("bus_factor", "decision_concentration", "bypass_risk")


def _cell(text: Any) -> str:
    """Make user-provided text safe inside a Markdown table cell."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def _counts(findings: List[Dict[str, Any]]) -> Dict[str, int]:
    open_findings = [f for f in findings if not f.get("accepted")]
    errors = sum(1 for f in open_findings if f.get("level") == "error")
    return {
        "errors": errors,
        "warnings": len(open_findings) - errors,
        "accepted": len(findings) - len(open_findings),
    }


def outputs(report: Dict[str, Any]) -> str:
    results = report["results"]
    counts = _counts(report.get("findings", []))
    values = {
        "score": results.get("score", ""),
        "grade": results.get("grade", ""),
        "risk-level": results.get("risk_level", ""),
        "errors": counts["errors"],
        "warnings": counts["warnings"],
    }
    return "".join(f"{key}={value}\n" for key, value in values.items())


def summary(report: Dict[str, Any]) -> str:
    results, metadata = report["results"], report.get("metadata", {})
    findings = report.get("findings", [])
    counts = _counts(findings)
    people = metadata.get("organization_size", "?")
    lines = [
        f"## Human Risk Graph: {results.get('score')}/100 \u00b7 grade {results.get('grade')} "
        f"\u00b7 {results.get('risk_level')} risk",
        "",
        f"`{_cell(metadata.get('input_name', ''))}` \u00b7 "
        f"{people} {'person' if people == 1 else 'people'} \u00b7 "
        f"{metadata.get('dependencies_count', '?')} dependencies \u00b7 "
        f"model {results.get('model', '')}",
        "",
    ]
    if unconfirmed_text(metadata):
        only = metadata.get("confirmed_only")
        lines += [
            f"> [!WARNING]\n> {unconfirmed_text(metadata)}"
            + (f"; on confirmed data only the score is {only['score']}/100." if only else ".")
            + " Review them before relying on the score.",
            "",
        ]
    gaps = metadata.get("coverage_gaps") or []
    if gaps:
        lines += [
            f"> [!NOTE]\n> {len(gaps)} data gap{'s' if len(gaps) != 1 else ''}: what the "
            "scan could not see is not evidence that it does not exist.",
            "",
        ]
    lines += ["| Metric | Value |", "|---|---:|"]
    labels = _metric_labels(results)
    lines += [
        f"| {label} | {results[key]:.2f} |"
        for label, key in zip(labels, METRIC_KEYS)
        if key in results
    ]
    lines.append("")

    lines.append(
        f"**Findings:** {counts['errors']} errors \u00b7 {counts['warnings']} warnings"
        + (f" \u00b7 {counts['accepted']} accepted" if counts["accepted"] else "")
    )
    open_findings = [f for f in findings if not f.get("accepted")]
    if open_findings:
        lines += ["", "| Level | Rule | Finding |", "|---|---|---|"]
        for f in open_findings[:MAX_FINDINGS]:
            lines.append(f"| {f['level']} | {f['rule_id']} | {_cell(f['message'])} |")
        if len(open_findings) > MAX_FINDINGS:
            lines.append(f"\n{len(open_findings) - MAX_FINDINGS} more in the full report.")
    fixes = report.get("fix_plan") or []
    if fixes:
        lines += ["", "**Top fixes**", ""]
        lines += [
            f"{i}. {_cell(fix['title'])}: {fix['score_before']} \u2192 {fix['score_after']}"
            for i, fix in enumerate(fixes, 1)
        ]
    lines += ["", "The full HTML, Markdown, JSON and SARIF reports are in the workflow artifact."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] not in ("summary", "outputs"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    report = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    sys.stdout.write(summary(report) if args[0] == "summary" else outputs(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
