"""
Report generation for Human Risk Graph analysis.

Generates reports in multiple formats: JSON, Markdown, HTML.
"""

import json
from datetime import datetime
from typing import Dict, Any


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


def _get_primary_risk_driver(results: Dict[str, Any]) -> str:
    """Return the metric that contributes most to perceived risk."""
    metric_scores = {
        "Bus Factor Risk": results.get("bus_factor", 0.0),
        "Decision Concentration": results.get("decision_concentration", 0.0),
        "Bypass Risk": results.get("bypass_risk", 0.0),
    }
    return max(metric_scores, key=metric_scores.get)


def _score_breakdown(results: Dict[str, Any]) -> Dict[str, float]:
    """Return weighted contributions of each metric to the composite score."""
    return {
        "bus_factor_contribution": results.get("bus_factor", 0.0) * 0.4,
        "decision_contribution": results.get("decision_concentration", 0.0) * 0.3,
        "bypass_contribution": results.get("bypass_risk", 0.0) * 0.3,
    }


def generate_json_report(results: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    """
    Generate JSON report.

    Args:
        results: Analysis results from HRG
        metadata: Metadata about the analysis

    Returns:
        JSON string
    """
    report = {"metadata": metadata, "results": results, "generated_at": datetime.now().isoformat()}

    return json.dumps(report, indent=2, ensure_ascii=False)


def generate_markdown_report(results: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    """
    Generate Markdown report.

    Args:
        results: Analysis results from HRG
        metadata: Metadata about the analysis

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
    md.append("## 📊 Executive Summary")
    md.append("")
    md.append(
        f"The organization's **Composite HRG Score** is **{results['composite_score']:.3f}**."
    )
    md.append("")

    # Risk interpretation (aligned with metrics.interpret_risk_level)
    score = results["composite_score"]
    risk_level_raw = results.get("risk_level")
    if not risk_level_raw:
        if score < 0.3:
            risk_level_raw = "Low"
        elif score < 0.5:
            risk_level_raw = "Moderate"
        elif score < 0.7:
            risk_level_raw = "High"
        else:
            risk_level_raw = "Critical"

    risk_label_map = {
        "Low": "✅ **LOW**",
        "Moderate": "🟢 **MODERATE**",
        "High": "🟡 **HIGH**",
        "Critical": "🔴 **CRITICAL**",
    }
    interpretation_map = {
        "Low": "The organization has low human dependency risks.",
        "Moderate": "The organization has manageable human dependency risks.",
        "High": "The organization has significant human dependency risks that should be addressed.",
        "Critical": "The organization has severe human dependency risks that require immediate attention.",
    }

    risk_level = risk_label_map.get(risk_level_raw, "✅ **LOW**")
    interpretation = interpretation_map.get(
        risk_level_raw, "The organization has low human dependency risks."
    )

    md.append(f"**Risk Level:** {risk_level}")
    md.append("")
    md.append(interpretation)
    md.append("")

    # Key findings for non-technical readers
    primary_driver = _get_primary_risk_driver(results)
    critical_people_count = len(results.get("articulation_points", []))
    dep_type_counts = metadata.get("dependency_type_counts", {})
    dep_profile = ", ".join(
        f"{dep_type}: {count}" for dep_type, count in sorted(dep_type_counts.items())
    ) or "No typed dependencies provided"

    md.append("## 🔎 Key Findings")
    md.append("")
    md.append(f"- **Primary Risk Driver:** {primary_driver}")
    md.append(f"- **Critical People Identified:** {critical_people_count}")
    md.append(f"- **Dependency Profile:** {dep_profile}")
    md.append("")

    breakdown = _score_breakdown(results)
    critical_node_count = len(results.get("critical_nodes", []))
    org_size = metadata.get("organization_size", 0)
    critical_share = (critical_node_count / org_size) if org_size else 0.0

    md.append("## 🧠 Why This Score")
    md.append("")
    md.append(
        f"- Composite score is a weighted sum: **0.4×Bus + 0.3×Decision + 0.3×Bypass = {results['composite_score']:.3f}**"
    )
    md.append(
        f"- Bus contribution: **{breakdown['bus_factor_contribution']:.3f}**, Decision contribution: **{breakdown['decision_contribution']:.3f}**, Bypass contribution: **{breakdown['bypass_contribution']:.3f}**"
    )
    md.append(
        f"- Critical nodes above threshold: **{critical_node_count}/{org_size} ({critical_share:.0%})**"
    )
    md.append("")

    md.append("## 📘 How To Read Metrics")
    md.append("")
    md.append("- **Bus Factor Risk:** higher means stronger dependency on a few people.")
    md.append("- **Decision Concentration:** higher means approval power is concentrated.")
    md.append("- **Bypass Risk:** higher means controls are easier to bypass on critical paths.")
    md.append("")

    # Metrics Breakdown
    md.append("## 📈 Risk Metrics")
    md.append("")
    md.append("| Metric | Score | Weight | Description |")
    md.append("|--------|-------|--------|-------------|")
    md.append(
        f"| **Bus Factor Risk** | {results['bus_factor']:.3f} | 40% | Risk from key person dependencies |"
    )
    md.append(
        f"| **Decision Concentration** | {results['decision_concentration']:.3f} | 30% | Authority centralization risk |"
    )
    md.append(f"| **Bypass Risk** | {results['bypass_risk']:.3f} | 30% | Control override risk |")
    md.append(
        f"| **Composite Score** | {results['composite_score']:.3f} | 100% | Overall organizational risk |"
    )
    md.append("")

    md.append("**Metric interpretation:**")
    md.append(f"- Bus Factor Risk: **{_get_metric_level(results['bus_factor'])}**")
    md.append(
        f"- Decision Concentration: **{_get_metric_level(results['decision_concentration'])}**"
    )
    md.append(f"- Bypass Risk: **{_get_metric_level(results['bypass_risk'])}**")
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


def generate_html_report(results: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    """
    Generate HTML report with styling.

    Args:
        results: Analysis results from HRG
        metadata: Metadata about the analysis

    Returns:
        HTML string
    """
    score = results["composite_score"]

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
            <div class="risk-label">{risk_label} RISK</div>
            <div class="risk-score">{score:.3f}</div>
            <p style="color: #e4e4e7; font-size: 1.1em;">
                Composite Human Risk Graph Score
            </p>
        </div>

        <div class="section">
            <h2>🔎 Key Findings</h2>
            <div class="recommendations">
                <ul>
                    <li><strong>Primary Risk Driver:</strong> {_get_primary_risk_driver(results)}</li>
                    <li><strong>Critical People Identified:</strong> {len(results.get('articulation_points', []))}</li>
                    <li><strong>Dependency Profile:</strong> {", ".join(f"{k}: {v}" for k, v in sorted(metadata.get('dependency_type_counts', {}).items())) or "No typed dependencies provided"}</li>
                </ul>
            </div>
        </div>

        <div class="section">
            <h2>🧠 Why This Score</h2>
            <div class="recommendations">
                <ul>
                    <li><strong>Formula:</strong> 0.4 × Bus + 0.3 × Decision + 0.3 × Bypass = {results['composite_score']:.3f}</li>
                    <li><strong>Bus contribution:</strong> {_score_breakdown(results)['bus_factor_contribution']:.3f}</li>
                    <li><strong>Decision contribution:</strong> {_score_breakdown(results)['decision_contribution']:.3f}</li>
                    <li><strong>Bypass contribution:</strong> {_score_breakdown(results)['bypass_contribution']:.3f}</li>
                    <li><strong>Critical nodes:</strong> {len(results.get('critical_nodes', []))}/{metadata.get('organization_size', 0)}</li>
                </ul>
            </div>
        </div>

        <div class="section">
            <h2>📘 How To Read Metrics</h2>
            <div class="recommendations">
                <ul>
                    <li><strong>Bus Factor Risk:</strong> higher means stronger dependency on a few people.</li>
                    <li><strong>Decision Concentration:</strong> higher means approval power is concentrated.</li>
                    <li><strong>Bypass Risk:</strong> higher means controls are easier to bypass on critical paths.</li>
                </ul>
            </div>
        </div>

        <div class="metrics">
            <div class="metric-card">
                <div class="metric-name">🚌 Bus Factor Risk</div>
                <div class="metric-value">{results['bus_factor']:.3f}</div>
                <div class="metric-weight">Weight: 40%</div>
            </div>

            <div class="metric-card">
                <div class="metric-name">🎯 Decision Concentration</div>
                <div class="metric-value">{results['decision_concentration']:.3f}</div>
                <div class="metric-weight">Weight: 30%</div>
            </div>

            <div class="metric-card">
                <div class="metric-name">⚡ Bypass Risk</div>
                <div class="metric-value">{results['bypass_risk']:.3f}</div>
                <div class="metric-weight">Weight: 30%</div>
            </div>
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
            display_person = _format_person_display(person, metadata)
            person_info = metadata.get("person_lookup", {}).get(person, {})
            criticality = person_info.get("criticality")
            if criticality is not None:
                html += f"                <li>{display_person} — criticality: {criticality:.2f}</li>\n"
            else:
                html += f"                <li>{display_person}</li>\n"

        html += """            </ul>
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
