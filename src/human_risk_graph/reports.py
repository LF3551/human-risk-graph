"""
Report generation for Human Risk Graph analysis.

Generates reports in multiple formats: JSON, Markdown, HTML.
"""

import json
from datetime import datetime
from html import escape
from typing import Dict, Any, List, Optional

from .findings import FRAMEWORKS, Finding
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

    if findings:
        md.append("## 🧾 Findings and Related Controls")
        md.append("")
        md.append(f"_{CONTROLS_DISCLAIMER}_")
        md.append("")
        md.append("| Rule | Level | Finding | ISO/IEC 27001:2022 | SOC 2 | DORA |")
        md.append("|------|-------|---------|--------------------|-------|------|")
        for f in findings:
            message = f.message.replace("|", "\\|")
            md.append(
                f"| {f.rule_id} | {f.level} | {message} | {_controls_text(f, 'iso27001')} "
                f"| {_controls_text(f, 'soc2')} | {_controls_text(f, 'dora')} |"
            )
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
) -> str:
    """
    Generate HTML report with styling.

    Args:
        results: Analysis results from HRG
        metadata: Metadata about the analysis
        findings: Optional findings from ``collect_findings``
        fixes: Optional fix plan from ``HumanRiskGraph.fix_plan``

    Returns:
        HTML string
    """
    score = results["composite_score"]
    why_items = "\n".join(
        f"                    <li>{escape(line)}</li>"
        for line in _explanations(results, metadata) + [_formula(results)]
    )
    metric_cards = "\n".join(
        f"""            <div class="metric-card">
                <div class="metric-name">{escape(label)}</div>
                <div class="metric-value">{results[key]:.3f}</div>
                <div class="metric-weight">Weight: {weight:.0%}</div>
            </div>"""
        for key, label, weight in zip(METRIC_KEYS, _metric_labels(results), _weights(results))
    )
    fixes_html = ""
    if fixes:
        rows = "\n".join(
            f"                <tr><td>{i}</td><td>{escape(fix['title'])}</td>"
            f"<td>{escape(fix['reason'])}</td><td>{fix['score_before']} → "
            f"{fix['score_after']} (+{fix['score_after'] - fix['score_before']})</td></tr>"
            for i, fix in enumerate(fixes, 1)
        )
        fixes_html = f"""
        <div class="section">
            <h2>🛠️ Top Fixes</h2>
            <table class="findings">
                <tr><th>#</th><th>Fix</th><th>Why</th><th>Score</th></tr>
{rows}
            </table>
        </div>
"""

    # Determine risk level styling
    if score >= 0.7:
        risk_label = "CRITICAL"
        risk_color = "#dc3545"
    elif score >= 0.5:
        risk_label = "HIGH"
        risk_color = "#ffc107"
    elif score >= 0.3:
        risk_label = "MODERATE"
        risk_color = "#17a2b8"
    else:
        risk_label = "LOW"
        risk_color = "#28a745"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Human Risk Graph Analysis Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e4e4e7;
            line-height: 1.6;
            padding: 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(26, 26, 46, 0.8);
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
        }}

        header {{
            border-bottom: 2px solid #4a4e69;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}

        h1 {{
            color: #00d4ff;
            font-size: 2.5em;
            margin-bottom: 10px;
        }}

        .metadata {{
            color: #9ba4b5;
            font-size: 0.9em;
        }}

        .metadata span {{
            margin-right: 20px;
        }}

        .summary {{
            background: rgba(74, 78, 105, 0.3);
            border-left: 4px solid {risk_color};
            padding: 20px;
            margin: 30px 0;
            border-radius: 8px;
        }}

        .risk-score {{
            font-size: 3em;
            font-weight: bold;
            color: {risk_color};
            margin: 20px 0;
        }}

        .risk-label {{
            display: inline-block;
            background: {risk_color};
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
            margin-bottom: 15px;
        }}

        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}

        .metric-card {{
            background: rgba(74, 78, 105, 0.2);
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #4a4e69;
            transition: transform 0.2s;
        }}

        .metric-card:hover {{
            transform: translateY(-5px);
            border-color: #00d4ff;
        }}

        .metric-name {{
            color: #9ba4b5;
            font-size: 0.9em;
            margin-bottom: 10px;
        }}

        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #00d4ff;
        }}

        .metric-weight {{
            color: #6c757d;
            font-size: 0.85em;
            margin-top: 5px;
        }}

        .section {{
            margin: 40px 0;
        }}

        h2 {{
            color: #00d4ff;
            font-size: 1.8em;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #4a4e69;
        }}

        .critical-list {{
            list-style: none;
            padding: 0;
        }}

        .critical-list li {{
            background: rgba(247, 127, 0, 0.1);
            border-left: 3px solid #f77f00;
            padding: 12px 15px;
            margin: 10px 0;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
        }}

        .path-list {{
            background: rgba(74, 78, 105, 0.2);
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
        }}

        .path-item {{
            padding: 8px 0;
            border-bottom: 1px solid #4a4e69;
            font-family: 'Courier New', monospace;
        }}

        .path-item:last-child {{
            border-bottom: none;
        }}

        .recommendations {{
            background: rgba(0, 212, 255, 0.1);
            border-left: 4px solid #00d4ff;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}

        .recommendations h3 {{
            color: #00d4ff;
            margin-bottom: 15px;
        }}

        .recommendations ul {{
            margin-left: 20px;
            color: #e4e4e7;
        }}

        .recommendations li {{
            margin: 8px 0;
        }}

        footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #4a4e69;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
        }}

        .badge {{
            display: inline-block;
            background: #4a4e69;
            color: white;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            margin-left: 10px;
        }}

        table.findings {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9em;
        }}

        table.findings th, table.findings td {{
            border: 1px solid #4a4e69;
            padding: 8px;
            text-align: left;
            vertical-align: top;
        }}

        table.findings th {{
            color: #00d4ff;
        }}

        @media print {{
            body {{
                background: white;
                color: black;
            }}

            .container {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔒 Human Risk Graph Analysis Report</h1>
            <div class="metadata">
                <span>📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
                <span>👥 {metadata['organization_size']} people</span>
                <span>🔗 {metadata['dependencies_count']} dependencies</span>
            </div>
        </header>

        <div class="summary">
            <div class="risk-label">{risk_label} RISK · GRADE {results['grade']}</div>
            <div class="risk-score">{results['score']}<span style="font-size: 0.4em; color: #9ba4b5;">/100</span></div>
            <p style="color: #e4e4e7; font-size: 1.1em;">
                Human Risk Graph score · composite risk {score:.3f} · model {escape(str(results.get('model', MODEL_V2)))}
            </p>
        </div>

        <div class="section">
            <h2>🧠 Why This Score</h2>
            <div class="recommendations">
                <ul>
{why_items}
                </ul>
            </div>
        </div>
{fixes_html}
        <div class="metrics">
{metric_cards}
        </div>
"""

    # Critical People Section
    if results.get("articulation_points"):
        html += f"""
        <div class="section">
            <h2>⚠️ Critical People <span class="badge">{len(results['articulation_points'])} identified</span></h2>
            <p style="color: #9ba4b5; margin-bottom: 15px;">
                These individuals are <strong>single points of failure</strong> (articulation points).
                Their removal would disconnect the organizational graph.
            </p>
            <ul class="critical-list">
"""
        for person in results["articulation_points"]:
            display_person = escape(_format_person_display(person, metadata))
            person_info = metadata.get("person_lookup", {}).get(person, {})
            criticality = person_info.get("criticality")
            if criticality is not None:
                html += f"                <li>{display_person} — criticality: {criticality:.2f}</li>\n"
            else:
                html += f"                <li>{display_person}</li>\n"

        html += """            </ul>
        </div>
"""

    if findings:
        html += f"""
        <div class="section">
            <h2>🧾 Findings and Related Controls <span class="badge">{len(findings)}</span></h2>
            <p style="color: #9ba4b5; margin-bottom: 15px;">{CONTROLS_DISCLAIMER}</p>
            <table class="findings">
                <tr><th>Rule</th><th>Level</th><th>Finding</th>{"".join(f"<th>{escape(name)}</th>" for name in FRAMEWORKS.values())}</tr>
"""
        for f in findings:
            controls = "".join(
                f"<td>{escape(_controls_text(f, fw))}</td>" for fw in FRAMEWORKS
            )
            html += (
                f"                <tr><td>{f.rule_id}</td><td>{f.level}</td>"
                f"<td>{escape(f.message)}</td>{controls}</tr>\n"
            )
        html += """            </table>
        </div>
"""

    # Recommendations
    html += """
        <div class="section">
            <h2>💡 Recommendations</h2>
"""

    html += """
            <div class="recommendations">
                <h3>Priority Actions</h3>
                <ul>
"""

    if results.get("articulation_points"):
        html += """
                    <li><strong>Reduce key-person dependency (Bus Factor):</strong>
                        <ul>
                            <li>Cross-train backup owners for critical responsibilities</li>
                            <li>Document approval and emergency procedures</li>
                            <li>Define succession coverage for critical roles</li>
                        </ul>
                    </li>
"""

    if results["decision_concentration"] >= 0.3:
        html += """
                    <li><strong>Distribute decision authority:</strong>
                        <ul>
                            <li>Introduce secondary approvers for sensitive workflows</li>
                            <li>Rotate ownership of high-impact decisions</li>
                        </ul>
                    </li>
"""

    if results["bypass_risk"] >= 0.3:
        html += """
                    <li><strong>Tighten bypass governance:</strong>
                        <ul>
                            <li>Add compensating controls for emergency bypasses</li>
                            <li>Alert and review all bypass events weekly</li>
                        </ul>
                    </li>
"""

    if (
        not results.get("articulation_points")
        and results["decision_concentration"] < 0.3
        and results["bypass_risk"] < 0.3
    ):
        html += """
                    <li><strong>Maintain current posture:</strong>
                        <ul>
                            <li>Continue periodic reassessment as organization evolves</li>
                            <li>Re-run analysis after major org or process changes</li>
                        </ul>
                    </li>
"""

    html += """
                </ul>
            </div>
"""

    html += """
        </div>

        <footer>
            <p>Report generated by <a href="https://github.com/LF3551/human-risk-graph"
               style="color: #00d4ff; text-decoration: none;">Human Risk Graph</a></p>
            <p style="margin-top: 10px;">A quantitative model for organizational security risk from human dependencies</p>
        </footer>
    </div>
</body>
</html>
"""

    return html
