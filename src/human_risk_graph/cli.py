"""
Command-line interface for Human Risk Graph analysis.

Usage:
    hrg analyze data/example_organization.json
    hrg analyze org.yaml --format sarif --format junit --fail-above 0.5
    hrg diff old.json new.json --format markdown
    hrg schema > organization.schema.json

Exit codes: 0 success, 1 invalid input or error, 2 usage error,
3 risk above --fail-above or increased with --fail-on-increase.
"""

import click
import sys
from pathlib import Path
from datetime import datetime

from . import __version__
from . import diff as diff_module
from .ci_reports import generate_junit_report, generate_sarif_report
from .findings import collect_findings
from .hrg import HumanRiskGraph
from .loader import load_organization, organization_schema
from .reports import generate_json_report, generate_markdown_report, generate_html_report
from .visualization import generate_graph_visualization

EXIT_RISK = 3
REPORT_FORMATS = ("json", "markdown", "html", "sarif", "junit")
EXTENSIONS = {
    "json": ".json",
    "markdown": ".md",
    "html": ".html",
    "sarif": ".sarif",
    "junit": ".junit.xml",
}


def _load(input_file):
    try:
        data = load_organization(input_file)
        return data, HumanRiskGraph(data["people"], data["dependencies"])
    except (OSError, ValueError) as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


def _artifact_uri(path: Path) -> str:
    """Path for SARIF results: relative to the working directory (the repo root in CI)."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_uri()


@click.group()
@click.version_option(version=__version__)
def cli():
    """Human Risk Graph - Organizational Security Risk Analysis Tool."""
    pass


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--format",
    "formats",
    type=click.Choice([*REPORT_FORMATS, "all"], case_sensitive=False),
    multiple=True,
    default=("all",),
    show_default=True,
    help="Report format; repeat for several. 'all' means json, markdown and html.",
)
@click.option("--output", type=click.Path(), help="Output file path (default: auto-generated)")
@click.option(
    "--visualize/--no-visualize", default=True, help="Generate graph visualization (default: True)"
)
@click.option(
    "--fail-above",
    type=click.FloatRange(0, 1),
    help=f"Exit with code {EXIT_RISK} if the composite score is above this value.",
)
def analyze(input_file, formats, output, visualize, fail_above):
    """
    Analyze an organization's human risk graph.

    INPUT_FILE: JSON or YAML file with people and dependencies.

    Example:
        hrg analyze data/example_organization.json
        hrg analyze data/example_organization.json --format html --output report.html
        hrg analyze org.yaml --format sarif --format junit --no-visualize --fail-above 0.5
    """
    click.echo(f"🔍 Analyzing: {input_file}")
    data, hrg = _load(input_file)

    click.echo("⚙️  Running Human Risk Graph analysis...")
    results = hrg.calculate()
    findings = collect_findings(hrg, results, fail_above)

    # Prepare metadata
    input_path = Path(input_file)
    base_name = input_path.stem
    output_dir = input_path.parent if not output else Path(output).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    person_lookup = {
        person["id"]: {
            "name": person.get("name", person["id"]),
            "role": person.get("role", ""),
            "criticality": person.get("criticality", 0.0),
        }
        for person in data["people"]
    }

    dependency_type_counts = {}
    for dep in data["dependencies"]:
        dep_type = dep.get("type", "unknown")
        dependency_type_counts[dep_type] = dependency_type_counts.get(dep_type, 0) + 1

    metadata = {
        "input_file": str(input_path.absolute()),
        "analysis_date": datetime.now().isoformat(),
        "organization_size": len(data["people"]),
        "dependencies_count": len(data["dependencies"]),
        "person_lookup": person_lookup,
        "dependency_type_counts": dependency_type_counts,
    }

    # Generate reports
    formats_to_generate = []
    for fmt in formats:
        expanded = ("json", "markdown", "html") if fmt.lower() == "all" else (fmt.lower(),)
        formats_to_generate += [f for f in expanded if f not in formats_to_generate]
    generated_files = []
    failed = False

    for fmt in formats_to_generate:
        if output and len(formats_to_generate) == 1:
            # User specified output file
            output_file = Path(output)
        else:
            output_file = output_dir / f"{base_name}_report{EXTENSIONS[fmt]}"

        try:
            if fmt == "json":
                content = generate_json_report(results, metadata, findings)
            elif fmt == "markdown":
                content = generate_markdown_report(results, metadata, findings)
            elif fmt == "html":
                content = generate_html_report(results, metadata, findings)
            elif fmt == "sarif":
                content = generate_sarif_report(
                    findings,
                    _artifact_uri(input_path),
                    input_path.read_text(encoding="utf-8"),
                )
            else:
                content = generate_junit_report(findings, results, fail_above)
            output_file.write_text(content, encoding="utf-8")

            generated_files.append(str(output_file))
            click.echo(f"✅ Generated: {output_file}")
        except Exception as e:
            failed = True
            click.echo(f"❌ Failed to generate {fmt} report - {e}", err=True)

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
            person_info = person_lookup.get(person, {})
            display_name = person_info.get("name", person)
            role = person_info.get("role", "")
            if role:
                click.echo(f"   - {display_name} ({role})")
            else:
                click.echo(f"   - {display_name}")
        if len(critical) > 5:
            click.echo(f"   ... and {len(critical) - 5} more")

    errors = sum(1 for f in findings if f.level == "error")
    click.echo(f"\n🧾 Findings: {errors} error(s), {len(findings) - errors} warning(s)")
    for finding in findings:
        click.echo(f"   [{finding.rule_id}] {finding.message}")

    click.echo(f"\n✅ Analysis complete! Generated {len(generated_files)} file(s).")

    if failed:
        sys.exit(1)
    if fail_above is not None and results["composite_score"] > fail_above:
        click.echo(
            f"❌ Composite score {results['composite_score']:.3f} is above "
            f"--fail-above {fail_above:.3f}",
            err=True,
        )
        sys.exit(EXIT_RISK)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", type=click.Path(), help="Output HTML file")
def visualize(input_file, output):
    """
    Generate interactive graph visualization only.

    INPUT_FILE: JSON or YAML file with people and dependencies.
    """
    click.echo(f"🎨 Generating visualization for: {input_file}")
    _, hrg = _load(input_file)

    try:
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


@cli.command()
@click.argument("old_file", type=click.Path(exists=True, dir_okay=False))
@click.argument("new_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "markdown", "json"], case_sensitive=False),
    default="text",
    show_default=True,
)
@click.option("--output", type=click.Path(), help="Write to this file instead of stdout.")
@click.option(
    "--fail-on-increase",
    is_flag=True,
    help=f"Exit with code {EXIT_RISK} if the composite score went up.",
)
def diff(old_file, new_file, fmt, output, fail_on_increase):
    """
    Compare two snapshots of an organization.

    Shows metric changes, added and removed people and dependencies, and
    single points of failure that appeared or disappeared.

    Example:
        hrg diff org-2026-q1.yaml org-2026-q2.yaml --format markdown
    """
    old_data, _ = _load(old_file)
    new_data, _ = _load(new_file)
    changes = diff_module.compare(old_data, new_data)

    formatter = {
        "text": diff_module.format_text,
        "markdown": diff_module.format_markdown,
        "json": diff_module.format_json,
    }[fmt.lower()]
    content = formatter(changes)
    if output:
        Path(output).write_text(content, encoding="utf-8")
    else:
        click.echo(content, nl=False)

    if fail_on_increase and diff_module.risk_increased(changes):
        click.echo("❌ Composite score increased", err=True)
        sys.exit(EXIT_RISK)


@cli.command()
def schema():
    """Print the JSON Schema for organization files."""
    click.echo(organization_schema(), nl=False)


def main():
    """Entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
