"""
Report generation for Human Risk Graph analysis.

Generates reports in multiple formats: JSON, Markdown, HTML.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from .findings import Finding
from .model_v2 import MODEL_V1, MODEL_V2, MODEL_V3
from .model_v3 import describe as describe_v3

CONTROLS_DISCLAIMER = (
    "Related controls are informative pointers for audits, not an assessment of compliance."
)
METRIC_KEYS = ("bus_factor", "decision_concentration", "bypass_risk")
METRIC_LABELS = {
    MODEL_V2: ("Key-person risk", "Approval concentration", "Override exposure"),
    MODEL_V3: ("Function loss", "Authority concentration", "Solo control"),
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


def privacy_text(metadata: Dict[str, Any]) -> str:
    """Notice for pseudonymized reports, or an empty string."""
    privacy = metadata.get("pseudonymized")
    if not privacy:
        return ""
    return (
        "People are pseudonymized (keyed HMAC-SHA256); names, roles and evidence are removed."
        + ("" if privacy.get("stable") else " Without a key the pseudonyms change on every run.")
    )


def unconfirmed_text(metadata: Dict[str, Any]) -> str:
    """'2 of 9 dependencies and 1 of 3 functions are unconfirmed', or '' if none are."""
    parts = []
    deps, functions = (
        metadata.get(k) or 0 for k in ("unconfirmed_dependencies", "unconfirmed_functions")
    )
    if deps:
        parts.append(f"{deps} of {metadata.get('dependencies_count', '?')} dependencies")
    if functions:
        parts.append(f"{functions} of {metadata.get('functions_count', '?')} functions")
    return " and ".join(parts) + " are unconfirmed" if parts else ""


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
    letters = ("L", "D", "S") if results.get("model") == MODEL_V3 else ("K", "D", "B")
    x, y, z = letters
    return (
        f"Composite risk = (1 − (1 − {a}·{x})(1 − {b}·{y})(1 − {c}·{z})) / "
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
    if results.get("model") == MODEL_V3:
        return [
            f"{label} {letter} = {results[key]:.3f}: {headline}; {detail}"
            for label, letter, key, (headline, detail) in zip(
                labels, "LDS", METRIC_KEYS, describe_v3(results, name)
            )
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

    break_glass = len(results.get("break_glass_approvals", []))
    lines.append(
        f"{labels[2]} B = {b:.3f}: {len(results.get('overridable_approvals', []))} of "
        f"{results.get('critical_approvals', 0)} critical approvals can be overridden "
        "through a bypass"
        + (
            f" ({break_glass} only via break-glass, counted at half weight)."
            if break_glass
            else "."
        )
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
    report: Dict[str, Any] = {
        "metadata": metadata,
        "results": results,
        "generated_at": datetime.now().isoformat(),
    }
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
    findings = findings or []
    sections = [
        _md_header(metadata),
        _md_summary(results, metadata),
        _md_fixes(fixes or []),
        _md_metrics(results, metadata),
        _md_functions(results, metadata),
        _md_critical_people(results, metadata),
        _md_findings([f for f in findings if not f.accepted]),
        _md_accepted([f for f in findings if f.accepted]),
        _md_recommendations(results),
        [
            "---",
            "",
            "*Report generated by [Human Risk Graph](https://github.com/LF3551/human-risk-graph)*",
            "",
        ],
    ]
    return "\n".join(line for section in sections for line in section)


def _md_header(metadata: Dict[str, Any]) -> List[str]:
    md = [
        "# Human Risk Graph Analysis Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Input File:** `{metadata['input_file']}`",
        f"**Organization Size:** {metadata['organization_size']} people",
        f"**Dependencies:** {metadata['dependencies_count']}",
    ]
    if privacy_text(metadata):
        md += ["", f"> **Privacy:** {privacy_text(metadata)}"]
    if unconfirmed_text(metadata):
        confirmed = metadata.get("confirmed_only")
        md += [
            "",
            f"> **Note:** {unconfirmed_text(metadata)} "
            "(from `hrg scan`). Review them before relying on the score."
            + (
                f" On confirmed data only: {confirmed['score']}/100 ({confirmed['grade']})."
                if confirmed
                else ""
            ),
        ]
    gaps = metadata.get("coverage_gaps")
    if gaps:
        md += [
            "",
            f"> **Data gaps ({len(gaps)}):** what the scan could not see "
            "is not evidence that it does not exist.",
        ]
        md += [f"> - {gap}" for gap in gaps]
    md.append("")
    return md


def _md_summary(results: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
    md = [
        "## 📊 Executive Summary",
        "",
        f"**Score: {results['score']}/100 · grade {results['grade']} · "
        f"{results['risk_level']} risk** (composite risk {results['composite_score']:.3f}, "
        f"model `{results.get('model', MODEL_V2)}`)",
        "",
        RISK_INTERPRETATION.get(results["risk_level"], ""),
        "",
        "## 🧠 Why This Score",
        "",
    ]
    md += [f"- {line}" for line in _explanations(results, metadata)]
    md += [f"- {_formula(results)}", ""]
    return md


def _md_fixes(fixes: List[Dict[str, Any]]) -> List[str]:
    if not fixes:
        return []
    md = ["## 🛠️ Top Fixes", "", "| # | Fix | Why | Score |", "|---|-----|-----|-------|"]
    for i, fix in enumerate(fixes, 1):
        gain = fix["score_after"] - fix["score_before"]
        md.append(
            f"| {i} | {fix['title']} | {fix['reason']} | "
            f"{fix['score_before']} → {fix['score_after']} (+{gain}) |"
        )
    md.append("")
    return md


def _md_metrics(results: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
    md = [
        "## 📈 Risk Metrics",
        "",
        "| Metric | Value | Weight | Level |",
        "|--------|-------|--------|-------|",
    ]
    for key, label, weight in zip(METRIC_KEYS, _metric_labels(results), _weights(results)):
        md.append(
            f"| **{label}** | {results[key]:.3f} | {weight:.0%} | {_get_metric_level(results[key])} |"
        )
    md += [
        f"| **Composite risk** | {results['composite_score']:.3f} | | {results['risk_level']} |",
        "",
    ]
    dep_type_counts = metadata.get("dependency_type_counts", {})
    dep_profile = (
        ", ".join(f"{dep_type}: {count}" for dep_type, count in sorted(dep_type_counts.items()))
        or "No typed dependencies provided"
    )
    critical_node_count = len(results.get("critical_nodes", []))
    org_size = metadata.get("organization_size", 0)
    md += [
        f"Critical people (criticality ≥ {results.get('critical_threshold', 0.7)}): "
        f"**{critical_node_count}/{org_size}** · Dependencies: {dep_profile}",
        "",
    ]
    return md


def _md_functions(results: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
    if not results.get("functions"):
        return []
    md = [
        "## 🔑 Critical Functions",
        "",
        "| Function | Criticality | Requires | Performers | Margin | One person alone |",
        "|---|---:|---:|---|---:|---|",
    ]
    for f in results["functions"]:
        performers = ", ".join(_format_person_display(p, metadata) for p in f["performers"])
        alone = ", ".join(_format_person_display(p, metadata) for p in f["alone"]) or "—"
        if f["alone"] and f.get("separation") == "not-required":
            alone += " (by policy)"
        md.append(
            f"| {f['name']} | {f['criticality']:.2f} | {f['requires']} | "
            f"{performers or '—'} | {f['margin']} | {alone} |"
        )
    md += [
        "",
        "Margin: how many performers can be unavailable before the function stops. "
        "One person alone: who can complete it without a second person; "
        "(by policy): allowed, not counted as solo control.",
        "",
    ]
    return md


def _md_critical_people(results: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
    if not results.get("articulation_points"):
        return []
    md = [
        "## ⚠️ Critical People (Articulation Points)",
        "",
        "These individuals are **single points of failure**. Their removal would disconnect the organizational graph:",
        "",
    ]
    for person in results["articulation_points"]:
        display_person = _format_person_display(person, metadata)
        criticality = metadata.get("person_lookup", {}).get(person, {}).get("criticality")
        if criticality is not None:
            md.append(f"- `{display_person}` — criticality: {criticality:.2f}")
        else:
            md.append(f"- `{display_person}`")
    md += ["", f"**Total Critical People:** {len(results['articulation_points'])}", ""]
    return md


def _md_findings(open_findings: List[Finding]) -> List[str]:
    if not open_findings:
        return []
    md = [
        "## 🧾 Findings and Related Controls",
        "",
        f"_{CONTROLS_DISCLAIMER}_",
        "",
        "| Rule | Level | Finding | ISO/IEC 27001:2022 | SOC 2 | DORA |",
        "|------|-------|---------|--------------------|-------|------|",
    ]
    for f in open_findings:
        message = f.message.replace("|", "\\|")
        md.append(
            f"| {f.rule_id} | {f.level} | {message} | {_controls_text(f, 'iso27001')} "
            f"| {_controls_text(f, 'soc2')} | {_controls_text(f, 'dora')} |"
        )
    md.append("")
    return md


def _md_accepted(accepted: List[Finding]) -> List[str]:
    if not accepted:
        return []
    md = [
        "## ✅ Accepted Risks",
        "",
        "| Rule | Finding | Reason | Ticket | Expires |",
        "|------|---------|--------|--------|---------|",
    ]
    for f in accepted:
        a = f.acceptance
        if a is None:  # f.accepted implies an acceptance
            continue
        cells = [f.message, a.reason, a.ticket or "", a.expires.isoformat() if a.expires else ""]
        md.append(f"| {f.rule_id} | " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    md.append("")
    return md


def _md_recommendations(results: Dict[str, Any]) -> List[str]:
    md = ["## 💡 Recommendations", "", "### Priority Actions", ""]
    key_people = bool(results.get("articulation_points"))
    concentrated = results["decision_concentration"] >= 0.3
    bypassable = results["bypass_risk"] >= 0.3
    if key_people:
        md += [
            "1. **Reduce key-person dependency (Bus Factor):**",
            "   - Cross-train backup owners for critical responsibilities",
            "   - Document approval and emergency procedures",
            "   - Define succession coverage for critical roles",
            "",
        ]
    if concentrated:
        md += [
            "2. **Distribute decision authority:**",
            "   - Introduce secondary approvers for sensitive workflows",
            "   - Rotate ownership of high-impact decisions",
            "",
        ]
    if bypassable:
        md += [
            "3. **Tighten bypass governance:**",
            "   - Add compensating controls for emergency bypasses",
            "   - Alert and review all bypass events weekly",
            "",
        ]
    if not (key_people or concentrated or bypassable):
        md += [
            "1. **Maintain current posture:**",
            "   - Continue periodic reassessment as organization evolves",
            "   - Re-run analysis after major org or process changes",
            "",
        ]
    return md


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
