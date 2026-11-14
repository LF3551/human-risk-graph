"""
Interactive graph visualization for Human Risk Graph.

Uses pyvis to create beautiful, interactive network visualizations.
"""

from pathlib import Path
from typing import Dict, Set, Tuple

import networkx as nx
from pyvis.network import Network

# Edge type -> (colour, width, tooltip heading)
EDGE_STYLES: Dict[str, Tuple[str, float, str]] = {
    "critical_path": ("#ff0000", 3, "Critical Path"),
    "bypass": ("#fcbf49", 2.4, "Bypass Route"),
    "approval": ("#00d4ff", 2, "Approval Dependency"),
    "escalation": ("#b388ff", 1.8, "Escalation Path"),
}
DEFAULT_EDGE_STYLE = ("#4a4e69", 1.5, "Dependency")


def generate_graph_visualization(hrg, results, output_file):
    """
    Generate interactive HTML visualization of the organizational graph.

    Args:
        hrg: HumanRiskGraph instance
        results: Analysis results dict
        output_file: Path to save HTML file
    """
    # Create pyvis network
    net = Network(
        height="750px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="white",
        directed=True,
        # "local" (default) copies a lib/ folder into the current working directory
        cdn_resources="in_line",
    )

    # Configure physics for better layout
    net.set_options("""
    {
        "physics": {
            "enabled": true,
            "forceAtlas2Based": {
                "gravitationalConstant": -50,
                "centralGravity": 0.01,
                "springLength": 200,
                "springConstant": 0.08
            },
            "maxVelocity": 50,
            "solver": "forceAtlas2Based",
            "timestep": 0.35,
            "stabilization": {"iterations": 150}
        },
        "nodes": {
            "font": {
                "size": 16,
                "color": "white"
            },
            "borderWidth": 2,
            "borderWidthSelected": 4
        },
        "edges": {
            "arrows": {
                "to": {
                    "enabled": true,
                    "scaleFactor": 0.5
                }
            },
            "color": {
                "color": "#4a4e69",
                "highlight": "#00d4ff"
            },
            "smooth": {
                "type": "curvedCW",
                "roundness": 0.2
            }
        }
    }
    """)

    critical_people = set(results.get("articulation_points", []))
    _add_nodes(net, hrg, critical_people)
    _add_edges(net, hrg)

    legend_html = _legend_html(hrg.graph, results, len(critical_people))

    # Generate HTML
    output_path = Path(output_file)
    net.save_graph(str(output_path))

    # Read and modify HTML to add legend
    html_content = output_path.read_text(encoding="utf-8")

    # Insert legend before closing body tag
    html_content = html_content.replace("</body>", f"{legend_html}</body>")

    # Add custom title
    title = "Human Risk Graph - Interactive Visualization"
    html_content = html_content.replace("<title>pyvis.html</title>", f"<title>{title}</title>")

    # Write modified HTML
    output_path.write_text(html_content, encoding="utf-8")

    return str(output_path)


def _node_color(is_critical: bool, node_score: float) -> str:
    if is_critical:
        return "#f77f00"  # Orange - critical (articulation point)
    if node_score > 0.7:
        return "#fcbf49"  # Yellow - high risk
    if node_score > 0.4:
        return "#0abfbc"  # Teal - medium risk
    return "#00d4ff"  # Cyan - low risk


def _node_title(person: Dict, analysis: Dict, node_score: float, is_critical: bool) -> str:
    """
    Tooltip of a person.

    vis-network shows string titles as plain text (innerText), so this is text with
    line breaks, not HTML: markup would appear literally, and user data stays inert.
    """
    lines = [
        str(person.get("name", person["id"])),
        f"ID: {person['id']}",
        f"Risk Score: {node_score:.3f}",
        f"Criticality: {analysis.get('criticality', 0):.3f}",
        f"Betweenness: {analysis.get('betweenness_centrality', 0):.3f}",
    ]
    if "role" in person:
        lines.append(f"Role: {person['role']}")
    if is_critical:
        lines += ["", "⚠️ CRITICAL NODE", "(Articulation Point)"]
    lines += [
        "",
        f"Dependencies: {analysis['out_degree']}",
        f"Depended by: {analysis['in_degree']}",
    ]
    return "\n".join(lines)


def _add_nodes(net: Network, hrg, critical_people: Set[str]) -> None:
    """Add people, coloured by risk and sized by degree centrality."""
    degree_centrality = nx.degree_centrality(hrg.graph)
    max_degree = max(degree_centrality.values()) if degree_centrality else 1
    if max_degree <= 0:
        max_degree = 1
    analyses = hrg.analyze_nodes()

    for person in hrg.people:
        person_id = person["id"]
        analysis = analyses[person_id]
        node_score = analysis.get("node_risk_score", analysis.get("criticality", 0))
        is_critical = person_id in critical_people
        net.add_node(
            person_id,
            label=person.get("name", person_id),
            title=_node_title(person, analysis, node_score, is_critical),
            color=_node_color(is_critical, node_score),
            borderWidth=3 if is_critical else 2,
            size=20 + (degree_centrality.get(person_id, 0) / max_degree) * 30,
            shape="dot",
            font={"size": 14, "face": "arial", "color": "white"},
            borderWidthSelected=5,
            chosen={"node": True},
            mass=2,
        )


def _add_edges(net: Network, hrg) -> None:
    """Add dependencies, styled by type; bypasses are dashed."""
    names = {person["id"]: person.get("name", person["id"]) for person in hrg.people}
    for u, v, data in hrg.graph.edges(data=True):
        edge_type = data.get("edge_type", data.get("type", "dependency"))
        color, width, title = EDGE_STYLES.get(edge_type, DEFAULT_EDGE_STYLE)
        title += (
            f"\nFrom: {names.get(u, u)}\nTo: {names.get(v, v)}"
            f"\nType: {edge_type}\nWeight: {data.get('weight', 0.0):.2f}"
        )
        if "context" in data:
            title += f": {data['context']}"
        net.add_edge(
            u,
            v,
            title=title,
            color=color,
            width=width,
            dashes=edge_type == "bypass",
            arrows={"to": {"enabled": True, "scaleFactor": 0.5}},
        )


def _legend_html(graph: nx.DiGraph, results: Dict, critical_count: int) -> str:
    return """
    <div style="position: absolute; top: 10px; right: 10px; background: rgba(26, 26, 46, 0.9);
                padding: 15px; border-radius: 8px; border: 2px solid #4a4e69; color: white;
                font-family: Arial, sans-serif; font-size: 14px; z-index: 1000;">
        <h3 style="margin: 0 0 10px 0; color: #00d4ff;">Human Risk Graph</h3>
        <div style="margin-bottom: 8px;">
            <span style="color: #f77f00;">●</span> Critical Node (Articulation Point)
        </div>
        <div style="margin-bottom: 8px;">
            <span style="color: #fcbf49;">●</span> High Risk
        </div>
        <div style="margin-bottom: 8px;">
            <span style="color: #0abfbc;">●</span> Medium Risk
        </div>
        <div style="margin-bottom: 8px;">
            <span style="color: #00d4ff;">●</span> Low Risk
        </div>
        <hr style="border-color: #4a4e69; margin: 10px 0;">
        <div style="margin-bottom: 6px;"><b>Edge Types</b></div>
        <div style="margin-bottom: 6px;"><span style="color:#00d4ff;">—</span> Approval</div>
        <div style="margin-bottom: 6px;"><span style="color:#b388ff;">—</span> Escalation</div>
        <div style="margin-bottom: 6px;"><span style="color:#fcbf49;">- -</span> Bypass</div>
        <hr style="border-color: #4a4e69; margin: 10px 0;">
        <div style="font-size: 12px; color: #cbd5e1; margin-bottom: 8px;">
            <b>Network:</b> {nodes} people, {edges} dependencies<br>
            <b>Critical nodes:</b> {critical_count}
        </div>
        <div style="font-size: 12px; color: #9ba4b5; margin-bottom: 10px;">
            Tip: drag nodes, zoom with wheel, hover any node/edge for details.
        </div>
        <div style="font-size: 12px; color: #9ba4b5;">
            <b>Metrics:</b><br>
            Composite Score: {composite:.3f}<br>
            Bus Factor: {bus_factor:.3f}<br>
            Decision Conc.: {decision:.3f}<br>
            Bypass Risk: {bypass:.3f}
        </div>
    </div>
    """.format(
        nodes=len(graph.nodes()),
        edges=len(graph.edges()),
        critical_count=critical_count,
        composite=results["composite_score"],
        bus_factor=results["bus_factor"],
        decision=results["decision_concentration"],
        bypass=results["bypass_risk"],
    )
