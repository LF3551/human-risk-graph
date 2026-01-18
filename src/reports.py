"""
Report generation for Human Risk Graph analysis.

Generates reports in multiple formats: JSON, Markdown, HTML.
"""

import json
from datetime import datetime
from typing import Dict, Any


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

    # Risk interpretation
    score = results["composite_score"]
    if score > 0.7:
        risk_level = "🔴 **CRITICAL**"
        interpretation = (
            "The organization has severe human dependency risks that require immediate attention."
        )
    elif score > 0.4:
        risk_level = "🟡 **HIGH**"
        interpretation = (
            "The organization has significant human dependency risks that should be addressed."
        )
    elif score > 0.2:
        risk_level = "🟢 **MODERATE**"
        interpretation = "The organization has manageable human dependency risks."
    else:
        risk_level = "✅ **LOW**"
        interpretation = "The organization has low human dependency risks."

    md.append(f"**Risk Level:** {risk_level}")
    md.append("")
    md.append(interpretation)
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
        f"| **Decision Concentration** | {results['decision_concentration']:.3f} | 35% | Authority centralization risk |"
    )
    md.append(f"| **Bypass Risk** | {results['bypass_risk']:.3f} | 25% | Control override risk |")
    md.append(
        f"| **Composite Score** | {results['composite_score']:.3f} | 100% | Overall organizational risk |"
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
            md.append(f"- `{person}`")

        md.append("")
        md.append(f"**Total Critical People:** {len(results['articulation_points'])}")
        md.append("")

    # Recommendations
    md.append("## 💡 Recommendations")
    md.append("")

    if score > 0.5:
        md.append("### 🚨 Immediate Actions")
        md.append("")
        if results.get("articulation_points"):
            md.append("1. **Reduce Bus Factor Risk:**")
            md.append("   - Cross-train team members to reduce dependency on critical individuals")
            md.append("   - Document critical processes and decision-making procedures")
            md.append("   - Implement succession planning for critical roles")
            md.append("")

        if results["decision_concentration"] > 0.5:
            md.append("2. **Distribute Decision Authority:**")
            md.append("   - Delegate decision-making power to more team members")
            md.append("   - Implement matrix management structures")
            md.append("   - Create decision-making committees")
            md.append("")

        if results["bypass_risk"] > 0.5:
            md.append("3. **Strengthen Access Controls:**")
            md.append("   - Review and audit emergency bypass procedures")
            md.append("   - Implement multi-party approval for critical operations")
            md.append("   - Add monitoring for control overrides")
            md.append("")
    else:
        md.append("- Continue monitoring organizational changes")
        md.append("- Maintain current risk management practices")
        md.append("- Regular reassessment as organization evolves")
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
    if score > 0.7:
        risk_label = "CRITICAL"
        risk_color = "#dc3545"
    elif score > 0.4:
        risk_label = "HIGH"
        risk_color = "#ffc107"
    elif score > 0.2:
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

        <div class="metrics">
            <div class="metric-card">
                <div class="metric-name">🚌 Bus Factor Risk</div>
                <div class="metric-value">{results['bus_factor']:.3f}</div>
                <div class="metric-weight">Weight: 40%</div>
            </div>

            <div class="metric-card">
                <div class="metric-name">🎯 Decision Concentration</div>
                <div class="metric-value">{results['decision_concentration']:.3f}</div>
                <div class="metric-weight">Weight: 35%</div>
            </div>

            <div class="metric-card">
                <div class="metric-name">⚡ Bypass Risk</div>
                <div class="metric-value">{results['bypass_risk']:.3f}</div>
                <div class="metric-weight">Weight: 25%</div>
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
            html += f"                <li>{person}</li>\n"

        html += """            </ul>
        </div>
"""

    # Recommendations
    html += """
        <div class="section">
            <h2>💡 Recommendations</h2>
"""

    if score > 0.5:
        html += """
            <div class="recommendations">
                <h3>🚨 Immediate Actions Required</h3>
                <ul>
"""
        if results.get("articulation_points"):
            html += """
                    <li><strong>Reduce Bus Factor Risk:</strong>
                        <ul>
                            <li>Cross-train team members to reduce dependency on critical individuals</li>
                            <li>Document critical processes and decision-making procedures</li>
                            <li>Implement succession planning for critical roles</li>
                        </ul>
                    </li>
"""

        if results["decision_concentration"] > 0.5:
            html += """
                    <li><strong>Distribute Decision Authority:</strong>
                        <ul>
                            <li>Delegate decision-making power to more team members</li>
                            <li>Implement matrix management structures</li>
                            <li>Create decision-making committees</li>
                        </ul>
                    </li>
"""

        if results["bypass_risk"] > 0.5:
            html += """
                    <li><strong>Strengthen Access Controls:</strong>
                        <ul>
                            <li>Review and audit emergency bypass procedures</li>
                            <li>Implement multi-party approval for critical operations</li>
                            <li>Add monitoring for control overrides</li>
                        </ul>
                    </li>
"""

        html += """
                </ul>
            </div>
"""
    else:
        html += """
            <div class="recommendations">
                <ul>
                    <li>Continue monitoring organizational changes</li>
                    <li>Maintain current risk management practices</li>
                    <li>Regular reassessment as organization evolves</li>
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
