"""
Report generation for Human Risk Graph analysis.

Generates reports in multiple formats: JSON, Markdown, HTML.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from .findings import Finding
from .model_v2 import MODEL_V1, MODEL_V2

CONTROLS_DISCLAIMER = (
    "Related controls are informative pointers for audits, not an assessment of compliance."
)
METRIC_KEYS = ("bus_factor", "decision_concentration", "bypass_risk")
METRIC_LABELS = {
    MODEL_V2: ("Key-person risk", "Approval concentration", "Override exposure"),
    MODEL_V1: ("Bus factor risk", "Decision concentration", "Bypass risk"),
}
RISK_INTERPRETATION = {
    "Low": "Human dependency risks are low.",
    "Moderate": "Human dependency risks are manageable; the top fixes below are worth doing.",
    "High": "Significant human dependency risks that should be addressed.",
    "Critical": "Severe human dependency risks that need immediate attention.",
}


def _metric_labels(results: Dict[str, Any]):
    return METRIC_LABELS.get(results.get("model", MODEL_V2), METRIC_LABELS[MODEL_V2])


def _weights(results: Dict[str, Any]):
    w = results.get("weights", {})
    return (w.get("alpha", 0.4), w.get("beta", 0.3), w.get("gamma", 0.3))


def _formula(results: Dict[str, Any]) -> str:
    a, b, c = _weights(results)
    risk = results["composite_score"]
    if results.get("model") == MODEL_V1:
        return (
            f"Composite risk = {a}·BF + {b}·DC + {c}·BR = {risk:.3f} (model hrg-1); "
            f"score = 100·(1 − risk) = {results['score']}"
        )
    return (
        f"Composite risk = (1 − (1 − {a}·K)(1 − {b}·D)(1 − {c}·B)) / "
        f"(1 − (1 − {a})(1 − {b})(1 − {c})) = {risk:.3f}; "
        f"score = 100·(1 − risk) = {results['score']}"
    )


def _explanations(results: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
    """One plain-language line per metric."""

    def name(person_id: str) -> str:
        return metadata.get("person_lookup", {}).get(person_id, {}).get("name") or person_id

    labels = _metric_labels(results)
    k, d, b = (results[key] for key in METRIC_KEYS)
    if results.get("model") == MODEL_V1:
        return [
            f"{labels[0]} {k:.3f}: criticality of single points of failure per person.",
            f"{labels[1]} {d:.3f}: Gini coefficient of approval weight.",
            f"{labels[2]} {b:.3f}: share of critical paths with a bypass shortcut.",
        ]

    lines = []
    key_people = results.get("key_people", [])
    if key_people:
        top = key_people[0]
        bus = results.get("bus_factor_people")
        lines.append(
            f"{labels[0]} K = {k:.3f}: losing {name(top['id'])} cuts off {top['cut_off']} "
            f"{'person' if top['cut_off'] == 1 else 'people'} and {top['impact']:.0%} of the "
            f"connections between the others" + (f" (bus factor {bus})." if bus else ".")
        )
    else:
        lines.append(f"{labels[0]} K = {k:.3f}: no single point of failure.")

    shares = results.get("approval_shares", {})
    if shares:
        top_id, top_share = next(iter(shares.items()))
        lines.append(
            f"{labels[1]} D = {d:.3f}: {results['effective_approvers']:.1f} effective approvers "
            f"of {len(shares)}; {name(top_id)} holds {top_share:.0%} of the approval weight."
        )
    else:
        lines.append(f"{labels[1]} D = {d:.3f}: no approvals in the data.")

    lines.append(
        f"{labels[2]} B = {b:.3f}: {len(results.get('overridable_approvals', []))} of "
        f"{results.get('critical_approvals', 0)} critical approvals can be overridden "
        "through a bypass."
    )
    return lines


def _controls_text(finding: Finding, framework: str) -> str:
    return "; ".join(ref for ref, _ in finding.rule.controls.get(framework, ()))


def _format_person_display(person_id: str, metadata: Dict[str, Any]) -> str:
    """Format person ID into human-readable display using metadata lookup."""
    person_lookup = metadata.get("person_lookup", {})
    person_info = person_lookup.get(person_id, {})

    name = person_info.get("name") or person_id
    role = person_info.get("role")

    if role:
        return f"{name} ({role})"
    return name


def _get_metric_level(score: float) -> str:
    """Convert metric score into qualitative level."""
    if score >= 0.7:
        return "High"
    if score >= 0.3:
        return "Moderate"
    return "Low"


def generate_json_report(
    results: Dict[str, Any],
    metadata: Dict[str, Any],
    findings: Optional[List[Finding]] = None,
    fixes: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Generate JSON report.

    Args:
        results: Analysis results from HRG
        metadata: Metadata about the analysis
        findings: Optional findings from ``collect_findings``
        fixes: Optional fix plan from ``HumanRiskGraph.fix_plan``

    Returns:
        JSON string
    """
    report = {"metadata": metadata, "results": results, "generated_at": datetime.now().isoformat()}
    if findings is not None:
        report["findings"] = [f.to_dict() for f in findings]
    if fixes is not None:
        report["fix_plan"] = fixes

    return json.dumps(report, indent=2, ensure_ascii=False)


def generate_markdown_report(
    results: Dict[str, Any],
    metadata: Dict[str, Any],
    findings: Optional[List[Finding]] = None,
    fixes: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Generate Markdown report.

    Args:
        results: Analysis results from HRG
        metadata: Metadata about the analysis
        findings: Optional findings from ``collect_findings``
        fixes: Optional fix plan from ``HumanRiskGraph.fix_plan``

    Returns:
        Markdown string
    """
    md = []

    # Header
    md.append("# Human Risk Graph Analysis Report")
    md.append("")
    md.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"**Input File:** `{metadata['input_file']}`")
    md.append(f"**Organization Size:** {metadata['organization_size']} people")
    md.append(f"**Dependencies:** {metadata['dependencies_count']}")
    if metadata.get("unconfirmed_dependencies"):
        md.append("")
        md.append(
            f"> **Note:** {metadata['unconfirmed_dependencies']} dependencies are unconfirmed "
            "(from `hrg scan`). Review them before relying on the score."
        )
    md.append("")

    # Executive Summary
    labels = _metric_labels(results)
    weights = _weights(results)
    md.append("## 📊 Executive Summary")
    md.append("")
    md.append(
        f"**Score: {results['score']}/100 · grade {results['grade']} · "
        f"{results['risk_level']} risk** (composite risk {results['composite_score']:.3f}, "
        f"model `{results.get('model', MODEL_V2)}`)"
    )
    md.append("")
    md.append(RISK_INTERPRETATION.get(results["risk_level"], ""))
    md.append("")

    md.append("## 🧠 Why This Score")
    md.append("")
    for line in _explanations(results, metadata):
        md.append(f"- {line}")
    md.append(f"- {_formula(results)}")
    md.append("")

    if fixes:
        md.append("## 🛠️ Top Fixes")
        md.append("")
        md.append("| # | Fix | Why | Score |")
        md.append("|---|-----|-----|-------|")
        for i, fix in enumerate(fixes, 1):
            gain = fix["score_after"] - fix["score_before"]
            md.append(
                f"| {i} | {fix['title']} | {fix['reason']} | "
                f"{fix['score_before']} → {fix['score_after']} (+{gain}) |"
            )
        md.append("")

    # Metrics Breakdown
    md.append("## 📈 Risk Metrics")
    md.append("")
    md.append("| Metric | Value | Weight | Level |")
    md.append("|--------|-------|--------|-------|")
    for key, label, weight in zip(METRIC_KEYS, labels, weights):
        md.append(
            f"| **{label}** | {results[key]:.3f} | {weight:.0%} | {_get_metric_level(results[key])} |"
        )
    md.append(f"| **Composite risk** | {results['composite_score']:.3f} | | {results['risk_level']} |")
    md.append("")

    dep_type_counts = metadata.get("dependency_type_counts", {})
    dep_profile = ", ".join(
        f"{dep_type}: {count}" for dep_type, count in sorted(dep_type_counts.items())
    ) or "No typed dependencies provided"
    critical_node_count = len(results.get("critical_nodes", []))
    org_size = metadata.get("organization_size", 0)
    md.append(
        f"Critical people (criticality ≥ {results.get('critical_threshold', 0.7)}): "
        f"**{critical_node_count}/{org_size}** · Dependencies: {dep_profile}"
    )
    md.append("")

    # Critical People
    if results.get("articulation_points"):
        md.append("## ⚠️ Critical People (Articulation Points)")
        md.append("")
        md.append(
            "These individuals are **single points of failure**. Their removal would disconnect the organizational graph:"
        )
        md.append("")

        for person in results["articulation_points"]:
            display_person = _format_person_display(person, metadata)
            person_info = metadata.get("person_lookup", {}).get(person, {})
            criticality = person_info.get("criticality")
            if criticality is not None:
                md.append(f"- `{display_person}` — criticality: {criticality:.2f}")
            else:
                md.append(f"- `{display_person}`")

        md.append("")
        md.append(f"**Total Critical People:** {len(results['articulation_points'])}")
        md.append("")

    open_findings = [f for f in findings or [] if not f.accepted]
    accepted = [f for f in findings or [] if f.accepted]
    if open_findings:
        md.append("## 🧾 Findings and Related Controls")
        md.append("")
        md.append(f"_{CONTROLS_DISCLAIMER}_")
        md.append("")
        md.append("| Rule | Level | Finding | ISO/IEC 27001:2022 | SOC 2 | DORA |")
        md.append("|------|-------|---------|--------------------|-------|------|")
        for f in open_findings:
            message = f.message.replace("|", "\\|")
            md.append(
                f"| {f.rule_id} | {f.level} | {message} | {_controls_text(f, 'iso27001')} "
                f"| {_controls_text(f, 'soc2')} | {_controls_text(f, 'dora')} |"
            )
        md.append("")

    if accepted:
        md.append("## ✅ Accepted Risks")
        md.append("")
        md.append("| Rule | Finding | Reason | Ticket | Expires |")
        md.append("|------|---------|--------|--------|---------|")
        for f in accepted:
            a = f.acceptance
            cells = [f.message, a.reason, a.ticket or "", a.expires.isoformat() if a.expires else ""]
            cells = [c.replace("|", "\\|") for c in cells]
            md.append(f"| {f.rule_id} | " + " | ".join(cells) + " |")
        md.append("")

    # Recommendations
    md.append("## 💡 Recommendations")
    md.append("")

    md.append("### Priority Actions")
    md.append("")

    if results.get("articulation_points"):
        md.append("1. **Reduce key-person dependency (Bus Factor):**")
        md.append("   - Cross-train backup owners for critical responsibilities")
        md.append("   - Document approval and emergency procedures")
        md.append("   - Define succession coverage for critical roles")
        md.append("")

    if results["decision_concentration"] >= 0.3:
        md.append("2. **Distribute decision authority:**")
        md.append("   - Introduce secondary approvers for sensitive workflows")
        md.append("   - Rotate ownership of high-impact decisions")
        md.append("")

    if results["bypass_risk"] >= 0.3:
        md.append("3. **Tighten bypass governance:**")
        md.append("   - Add compensating controls for emergency bypasses")
        md.append("   - Alert and review all bypass events weekly")
        md.append("")

    if (
        not results.get("articulation_points")
        and results["decision_concentration"] < 0.3
        and results["bypass_risk"] < 0.3
    ):
        md.append("1. **Maintain current posture:**")
        md.append("   - Continue periodic reassessment as organization evolves")
        md.append("   - Re-run analysis after major org or process changes")
        md.append("")

    # Footer
    md.append("---")
    md.append("")
    md.append(
        "*Report generated by [Human Risk Graph](https://github.com/LF3551/human-risk-graph)*"
    )
    md.append("")

    return "\n".join(md)


def generate_html_report(
    results: Dict[str, Any],
    metadata: Dict[str, Any],
    findings: Optional[List[Finding]] = None,
    fixes: Optional[List[Dict[str, Any]]] = None,
    hrg=None,
) -> str:
    """
    Generate a self-contained HTML report.

    Args:
        results: Analysis results from HRG
        metadata: Metadata about the analysis
        findings: Optional findings from ``collect_findings``
        fixes: Optional fix plan from ``HumanRiskGraph.fix_plan``
        hrg: Optional ``HumanRiskGraph``; enables the dependency map and per-person links

    Returns:
        HTML string
    """
    from .html_report import render

    return render(results, metadata, findings, fixes, hrg)
