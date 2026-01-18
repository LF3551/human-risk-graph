"""
Interactive graph visualization for Human Risk Graph.

Uses pyvis to create beautiful, interactive network visualizations.
"""

from pyvis.network import Network
import networkx as nx
from pathlib import Path


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
        height="750px", width="100%", bgcolor="#1a1a2e", font_color="white", directed=True
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

    # Get critical people from results
    critical_people = set(results.get("articulation_points", []))

    # Calculate node sizes based on degree centrality
    G = hrg.graph
    degree_centrality = nx.degree_centrality(G)
    max_degree = max(degree_centrality.values()) if degree_centrality else 1

    # Add nodes with risk-based coloring
    for person in hrg.people:
        person_id = person["id"]
        name = person.get("name", person_id)

        # Analyze this specific node
        node_analysis = hrg.analyze_node(person_id)
        node_score = node_analysis.get("node_risk_score", 0)

        # Determine node color based on risk level
        if person_id in critical_people:
            color = "#f77f00"  # Orange - critical (articulation point)
        elif node_score > 0.7:
            color = "#fcbf49"  # Yellow - high risk
        elif node_score > 0.4:
            color = "#0abfbc"  # Teal - medium risk
        else:
            color = "#00d4ff"  # Cyan - low risk

        # Node size based on centrality
        centrality = degree_centrality.get(person_id, 0)
        size = 20 + (centrality / max_degree) * 30

        # Build title (tooltip) with detailed info
        title = f"<b>{name}</b><br>"
        title += f"ID: {person_id}<br>"
        title += f"Risk Score: {node_score:.3f}<br>"

        if "role" in person:
            title += f"Role: {person['role']}<br>"

        if person_id in critical_people:
            title += "<br><b style='color:#f77f00'>⚠️ CRITICAL NODE</b><br>"
            title += "(Articulation Point)<br>"

        # Add dependency info
        in_degree = G.in_degree(person_id)
        out_degree = G.out_degree(person_id)
        title += f"<br>Dependencies: {out_degree}<br>"
        title += f"Depended by: {in_degree}"

        net.add_node(
            person_id,
            label=name,
            title=title,
            color=color,
            borderWidth=3 if person_id in critical_people else 2,
            size=size,
            shape="dot",
            font={"size": 14, "face": "arial", "color": "white"},
            borderWidthSelected=5,
            chosen={"node": True},
            mass=2,
        )

    # Add edges
    for u, v, data in G.edges(data=True):
        edge_type = data.get("type", "dependency")

        # Edge styling based on type
        if edge_type == "critical_path":
            color = "#ff0000"
            width = 3
            title = "Critical Path"
        elif edge_type == "bypass":
            color = "#fcbf49"
            width = 2
            title = "Bypass Route"
        else:
            color = "#4a4e69"
            width = 1.5
            title = "Dependency"

        # Add context to tooltip if available
        if "context" in data:
            title += f": {data['context']}"

        net.add_edge(
            u,
            v,
            title=title,
            color=color,
            width=width,
            arrows={"to": {"enabled": True, "scaleFactor": 0.5}},
        )

    # Add legend to the visualization
    legend_html = """
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
        <div style="font-size: 12px; color: #9ba4b5;">
            <b>Metrics:</b><br>
            Composite Score: {composite:.3f}<br>
            Bus Factor: {bus_factor:.3f}<br>
            Decision Conc.: {decision:.3f}<br>
            Bypass Risk: {bypass:.3f}
        </div>
    </div>
    """.format(
        composite=results["composite_score"],
        bus_factor=results["bus_factor"],
        decision=results["decision_concentration"],
        bypass=results["bypass_risk"],
    )

    # Generate HTML
    output_path = Path(output_file)
    net.save_graph(str(output_path))

    # Read and modify HTML to add legend
    html_content = output_path.read_text()

    # Insert legend before closing body tag
    html_content = html_content.replace("</body>", f"{legend_html}</body>")

    # Add custom title
    title = "Human Risk Graph - Interactive Visualization"
    html_content = html_content.replace("<title>pyvis.html</title>", f"<title>{title}</title>")

    # Write modified HTML
    output_path.write_text(html_content)

    return str(output_path)


def generate_static_visualization(hrg, results, output_file):
    """
    Generate static PNG visualization using matplotlib (fallback).

    Args:
        hrg: HumanRiskGraph instance
        results: Analysis results dict
        output_file: Path to save PNG file
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, ax = plt.subplots(figsize=(14, 10), facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.axis("off")

    G = hrg.graph

    # Layout
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    # Get critical people
    critical_people = set(results.get("articulation_points", []))

    # Node colors based on criticality
    node_colors = []
    node_sizes = []
    for node in G.nodes():
        if node in critical_people:
            node_colors.append("#f77f00")
            node_sizes.append(1000)
        else:
            node_colors.append("#00d4ff")
            node_sizes.append(600)

    # Draw
    nx.draw_networkx_nodes(
        G,
        pos,
        node_color=node_colors,
        node_size=node_sizes,
        edgecolors="white",
        linewidths=2,
        ax=ax,
    )
    nx.draw_networkx_edges(
        G,
        pos,
        edge_color="#4a4e69",
        arrows=True,
        arrowsize=20,
        width=2,
        alpha=0.6,
        ax=ax,
        connectionstyle="arc3,rad=0.1",
    )

    # Labels
    labels = {person["id"]: person.get("name", person["id"]) for person in hrg.people}
    nx.draw_networkx_labels(
        G, pos, labels, font_size=10, font_color="white", font_weight="bold", ax=ax
    )

    # Legend
    legend_elements = [
        mpatches.Patch(color="#f77f00", label="Critical Node"),
        mpatches.Patch(color="#00d4ff", label="Normal Node"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="upper right",
        facecolor="#1a1a2e",
        edgecolor="white",
        labelcolor="white",
    )

    # Title
    plt.title("Human Risk Graph", color="white", fontsize=18, fontweight="bold", pad=20)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, facecolor="#1a1a2e", edgecolor="none")
    plt.close()

    return str(output_file)
