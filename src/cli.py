"""
Command-line interface for Human Risk Graph analysis.

Usage:
    hrg analyze data/example_organization.json
    hrg analyze data/example_organization.json --format html
    hrg analyze data/example_organization.json --output report.html
"""

import click
import json
import sys
from pathlib import Path
from datetime import datetime

from src.hrg import HumanRiskGraph
from src.reports import generate_json_report, generate_markdown_report, generate_html_report
from src.visualization import generate_graph_visualization


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Human Risk Graph - Organizational Security Risk Analysis Tool."""
    pass


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "--format",
    type=click.Choice(["json", "markdown", "html", "all"], case_sensitive=False),
    default="all",
    help="Output format (default: all)",
)
@click.option("--output", type=click.Path(), help="Output file path (default: auto-generated)")
@click.option(
    "--visualize/--no-visualize", default=True, help="Generate graph visualization (default: True)"
)
def analyze(input_file, format, output, visualize):
    """
    Analyze an organization's human risk graph.

    INPUT_FILE: JSON file containing organization data with people and dependencies.

    Example:
        hrg analyze data/example_organization.json
        hrg analyze data/example_organization.json --format html --output report.html
    """
    click.echo(f"🔍 Analyzing: {input_file}")

    # Load data
    try:
        with open(input_file, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        click.echo(f"❌ Error: Invalid JSON file - {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error loading file: {e}", err=True)
        sys.exit(1)

    # Validate data structure
    if "people" not in data or "dependencies" not in data:
        click.echo("❌ Error: JSON must contain 'people' and 'dependencies' keys", err=True)
        sys.exit(1)

    # Create HRG and run analysis
    click.echo("⚙️  Running Human Risk Graph analysis...")
    try:
        hrg = HumanRiskGraph(data["people"], data["dependencies"])
        results = hrg.calculate()
    except Exception as e:
        click.echo(f"❌ Analysis failed: {e}", err=True)
        sys.exit(1)

    # Prepare metadata
    input_path = Path(input_file)
    base_name = input_path.stem
    output_dir = input_path.parent if not output else Path(output).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "input_file": str(input_path.absolute()),
        "analysis_date": datetime.now().isoformat(),
        "organization_size": len(data["people"]),
        "dependencies_count": len(data["dependencies"]),
    }

    # Generate reports
    formats_to_generate = ["json", "markdown", "html"] if format == "all" else [format]
    generated_files = []

    for fmt in formats_to_generate:
        if output and len(formats_to_generate) == 1:
            # User specified output file
            output_file = Path(output)
        else:
            # Auto-generate filename
            ext = {"json": ".json", "markdown": ".md", "html": ".html"}[fmt]
            output_file = output_dir / f"{base_name}_report{ext}"

        try:
            if fmt == "json":
                content = generate_json_report(results, metadata)
                output_file.write_text(content)
            elif fmt == "markdown":
                content = generate_markdown_report(results, metadata)
                output_file.write_text(content)
            elif fmt == "html":
                content = generate_html_report(results, metadata)
                output_file.write_text(content)

            generated_files.append(str(output_file))
            click.echo(f"✅ Generated: {output_file}")
        except Exception as e:
            click.echo(f"⚠️  Warning: Failed to generate {fmt} report - {e}", err=True)

    # Generate visualization
    if visualize:
        try:
            viz_file = output_dir / f"{base_name}_graph.html"
            generate_graph_visualization(hrg, results, str(viz_file))
            generated_files.append(str(viz_file))
            click.echo(f"✅ Generated: {viz_file}")
        except Exception as e:
            click.echo(f"⚠️  Warning: Failed to generate visualization - {e}", err=True)

    # Summary
    click.echo("\n" + "=" * 60)
    click.echo("📊 ANALYSIS SUMMARY")
    click.echo("=" * 60)
    click.echo(f"Composite HRG Score: {results['composite_score']:.3f}")
    click.echo(f"  • Bus Factor Score: {results['bus_factor']:.3f}")
    click.echo(f"  • Decision Concentration: {results['decision_concentration']:.3f}")
    click.echo(f"  • Bypass Risk Score: {results['bypass_risk']:.3f}")

    critical = results.get("articulation_points", [])
    if critical:
        click.echo(f"\n⚠️  Critical People (Articulation Points): {len(critical)}")
        for person in critical[:5]:
            click.echo(f"   - {person}")
        if len(critical) > 5:
            click.echo(f"   ... and {len(critical) - 5} more")

    click.echo(f"\n✅ Analysis complete! Generated {len(generated_files)} file(s).")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", type=click.Path(), help="Output HTML file")
def visualize(input_file, output):
    """
    Generate interactive graph visualization only.

    INPUT_FILE: JSON file containing organization data.
    """
    click.echo(f"🎨 Generating visualization for: {input_file}")

    # Load data
    try:
        with open(input_file, "r") as f:
            data = json.load(f)

        hrg = HumanRiskGraph(data["people"], data["dependencies"])
        results = hrg.calculate()

        # Determine output file
        if output:
            output_file = output
        else:
            input_path = Path(input_file)
            output_file = input_path.parent / f"{input_path.stem}_graph.html"

        generate_graph_visualization(hrg, results, output_file)
        click.echo(f"✅ Visualization saved: {output_file}")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


def main():
    """Entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
