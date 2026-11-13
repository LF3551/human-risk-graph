"""
Command-line interface for Human Risk Graph analysis.

Usage:
    hrg analyze data/example_organization.json
    hrg analyze org.yaml --format sarif --format junit --min-score 70
    hrg diff old.json new.json --format markdown
    hrg schema > organization.schema.json

Exit codes: 0 success, 1 invalid input or error, 2 usage error, 3 score below
--min-score, risk above --fail-above, or risk increased with --fail-on-increase.
"""

import click
import hashlib
import sys
from collections import Counter
from pathlib import Path
from datetime import datetime

from rich.console import Console
from click.core import ParameterSource

from . import __version__
from . import diff as diff_module
from .ci_reports import generate_junit_report, generate_sarif_report
from .config import Config, ConfigError, apply_acceptances, load_config
from .console import render_summary
from .findings import collect_findings, threshold_breach
from .github_scan import (
    GitHubClient,
    GitHubError,
    GitHubScanner,
    default_token,
    draft_yaml,
    merge_with_existing,
)
from .hrg import HumanRiskGraph
from .loader import load_organization, organization_schema
from .model_v2 import MODEL_V2, MODELS
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
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


CONFIG_OPTION = click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Config file (default: hrg.toml, .hrg.toml or [tool.hrg] in pyproject.toml).",
)


def _config(path) -> Config:
    try:
        return load_config(path)
    except (OSError, ConfigError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _setting(ctx, name, cli_value, config_value):
    """The command-line value unless it was left at its default and the config sets one."""
    if config_value is not None and ctx.get_parameter_source(name) == ParameterSource.DEFAULT:
        return config_value
    return cli_value


def _confirmed_only(data, calc):
    """Score without the dependencies marked ``confirmed: false``, or None if there are none."""
    kept = [d for d in data["dependencies"] if d.get("confirmed") is not False]
    if len(kept) == len(data["dependencies"]):
        return None
    results = HumanRiskGraph(data["people"], kept).calculate(with_bus_factor=False, **calc)
    return {"score": results["score"], "grade": results["grade"], "dependencies": len(kept)}


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
    help=f"Exit with code {EXIT_RISK} if the composite risk (0-1) is above this value.",
)
@click.option(
    "--min-score",
    type=click.IntRange(0, 100),
    help=f"Exit with code {EXIT_RISK} if the score (0-100) is below this value.",
)
@click.option(
    "--model",
    type=click.Choice(MODELS),
    default=MODEL_V2,
    show_default=True,
    help="Scoring model; hrg-1 reproduces the original paper.",
)
@click.option(
    "--fixes",
    "fix_steps",
    type=click.IntRange(0, 10),
    default=3,
    show_default=True,
    help="Number of remediations to simulate and rank (0 to skip).",
)
@click.option("--quiet", "-q", is_flag=True, help="Only print errors.")
@CONFIG_OPTION
@click.pass_context
def analyze(
    ctx, input_file, formats, output, visualize, fail_above, min_score, model, fix_steps, quiet,
    config_path,
):  # fmt: skip
    """
    Analyze an organization's human risk graph.

    INPUT_FILE: JSON or YAML file with people and dependencies.

    Settings and risk acceptances are read from hrg.toml (or [tool.hrg] in
    pyproject.toml) in the current directory; options on the command line win.

    Example:
        hrg analyze data/example_organization.json
        hrg analyze data/example_organization.json --format html --output report.html
        hrg analyze org.yaml --format sarif --format junit --no-visualize --min-score 70
    """
    config = _config(config_path)
    model = _setting(ctx, "model", model, config.model)
    fix_steps = _setting(ctx, "fix_steps", fix_steps, config.fixes)
    min_score = _setting(ctx, "min_score", min_score, config.min_score)
    fail_above = _setting(ctx, "fail_above", fail_above, config.fail_above)
    calc = {"model": model, **config.calculate_kwargs()}

    data, hrg = _load(input_file)
    results = hrg.calculate(**calc)
    findings = collect_findings(hrg, results, fail_above, min_score)
    findings, unused = apply_acceptances(findings, config.accept)
    fixes = hrg.fix_plan(steps=fix_steps, **calc) if fix_steps else []
    breach = threshold_breach(results, fail_above, min_score)
    if breach and any(f.rule_id == "HRG004" and f.accepted for f in findings):
        breach = None

    # Prepare metadata
    input_path = Path(input_file)
    base_name = input_path.stem
    output_dir = input_path.parent if not output else Path(output).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    person_lookup = {
        person["id"]: {
            "name": person.get("name", person["id"]),
            "role": person.get("role", ""),
            "criticality": person.get("criticality", 0.5),
        }
        for person in data["people"]
    }

    dependency_type_counts = {}
    for dep in data["dependencies"]:
        dep_type = dep.get("type", "unknown")
        dependency_type_counts[dep_type] = dependency_type_counts.get(dep_type, 0) + 1

    metadata = {
        # As given on the command line: an absolute path would leak local directory names.
        "input_file": input_path.as_posix(),
        "input_name": input_path.name,
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "tool_version": __version__,
        "analysis_date": datetime.now().isoformat(timespec="seconds"),
        "organization_size": len(data["people"]),
        "dependencies_count": len(data["dependencies"]),
        "person_lookup": person_lookup,
        "dependency_type_counts": dependency_type_counts,
        "config_file": config.path.name if config.path else None,
        "unconfirmed_dependencies": sum(
            1 for d in data["dependencies"] if d.get("confirmed") is False
        ),
        "coverage_gaps": [
            str(gap) for gap in ((data.get("coverage") or {}).get("gaps") or []) if gap
        ],
        "confirmed_only": _confirmed_only(data, calc),
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
                content = generate_json_report(results, metadata, findings, fixes)
            elif fmt == "markdown":
                content = generate_markdown_report(results, metadata, findings, fixes)
            elif fmt == "html":
                content = generate_html_report(results, metadata, findings, fixes, hrg)
            elif fmt == "sarif":
                content = generate_sarif_report(
                    findings,
                    _artifact_uri(input_path),
                    input_path.read_text(encoding="utf-8"),
                )
            else:
                content = generate_junit_report(findings, results, fail_above, min_score)
            output_file.write_text(content, encoding="utf-8")
            generated_files.append(str(output_file))
        except Exception as e:
            failed = True
            click.echo(f"Error: failed to generate {fmt} report: {e}", err=True)

    # Generate visualization
    if visualize:
        try:
            viz_file = output_dir / f"{base_name}_graph.html"
            generate_graph_visualization(hrg, results, str(viz_file))
            generated_files.append(str(viz_file))
        except Exception as e:
            click.echo(f"Warning: failed to generate visualization: {e}", err=True)

    if not quiet:
        render_summary(
            Console(highlight=False),
            input_file,
            data,
            results,
            findings,
            fixes,
            generated_files,
            breach,
            config_file=metadata["config_file"],
            confirmed_only=metadata["confirmed_only"],
        )
    for acceptance in unused:
        target = f" {acceptance.target}" if acceptance.target else ""
        click.echo(
            f"Warning: risk acceptance {acceptance.rule}{target} matches no finding "
            "and can be removed from the config.",
            err=True,
        )
    for finding in findings:
        if finding.acceptance_expired:
            click.echo(
                f"Warning: risk acceptance for {finding.key} expired on "
                f"{finding.acceptance.expires.isoformat()}.",
                err=True,
            )

    if failed:
        sys.exit(1)
    if breach:
        if quiet:
            click.echo(f"Error: {breach}", err=True)
        sys.exit(EXIT_RISK)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", type=click.Path(), help="Output HTML file")
def visualize(input_file, output):
    """
    Generate interactive graph visualization only.

    INPUT_FILE: JSON or YAML file with people and dependencies.
    """
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
        click.echo(f"Visualization saved: {output_file}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
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
    help=f"Exit with code {EXIT_RISK} if the composite risk went up.",
)
@click.option("--model", type=click.Choice(MODELS), default=MODEL_V2, show_default=True)
@CONFIG_OPTION
@click.pass_context
def diff(ctx, old_file, new_file, fmt, output, fail_on_increase, model, config_path):
    """
    Compare two snapshots of an organization.

    Shows score and metric changes, added, removed and changed people and
    dependencies, and single points of failure that appeared or disappeared.

    Example:
        hrg diff org-2026-q1.yaml org-2026-q2.yaml --format markdown
    """
    config = _config(config_path)
    model = _setting(ctx, "model", model, config.model)
    old_data, _ = _load(old_file)
    new_data, _ = _load(new_file)
    changes = diff_module.compare(old_data, new_data, model=model, **config.calculate_kwargs())

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
        click.echo("Error: composite risk increased", err=True)
        sys.exit(EXIT_RISK)


@cli.command()
def schema():
    """Print the JSON Schema for organization files."""
    click.echo(organization_schema(), nl=False)


@cli.group()
def scan():
    """Build a draft organization file from real data."""


@scan.command("github")
@click.argument("repo")
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Draft file to write (default: REPO-org.yaml). An existing draft is updated.",
)
@click.option("--branch", help="Protected branch to analyze (default: the default branch).")
@click.option(
    "--max-prs",
    type=click.IntRange(1, 1000),
    default=100,
    show_default=True,
    help="Most recent merged pull requests to read.",
)
@click.option("--include-bots", is_flag=True, help="Keep bot accounts such as dependabot[bot].")
@click.option(
    "--token",
    envvar="HRG_GITHUB_TOKEN",
    help="GitHub token (default: GITHUB_TOKEN, GH_TOKEN or `gh auth token`).",
)
def scan_github(repo, output, branch, max_prs, include_bots, token):
    """
    Draft an organization from a GitHub repository.

    REPO is OWNER/NAME. Reads pull request reviews, CODEOWNERS, branch rules and merges
    without review, and writes a YAML draft where every dependency has its source,
    evidence and confirmed: false. Review the draft, then run hrg analyze on it.

    Example:
        hrg scan github my-org/payments-api
        hrg analyze payments-api-org.yaml
    """
    console = Console(stderr=True, highlight=False)
    output = output or Path(f"{repo.split('/')[-1]}-org.yaml")
    existing = None
    if output.exists():
        try:
            existing = load_organization(output)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    client = GitHubClient(token or default_token())
    if not client.token:
        console.print("[yellow]No GitHub token: limited to 60 requests per hour.[/]")
    try:
        with console.status(f"Scanning {repo}") as status:
            scanner = GitHubScanner(
                client,
                repo,
                branch=branch,
                max_prs=max_prs,
                include_bots=include_bots,
                progress=lambda message: status.update(f"{repo}: {message}"),
            )
            result = scanner.scan()
    except (GitHubError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    notes = merge_with_existing(result, existing)
    output.write_text(draft_yaml(result, notes), encoding="utf-8")

    kinds = Counter(d["type"] for d in result.dependencies)
    unconfirmed = sum(1 for d in result.dependencies if d.get("confirmed") is False)
    console.print(
        f"\n[bold]{repo}[/] · {result.pull_requests} merged PRs on {result.branch} · "
        f"{result.api_calls} API calls"
    )
    people = len(result.people)
    console.print(
        f"  {people} {'person' if people == 1 else 'people'} · "
        + "".join(f"{n} {kind} · " for kind, n in sorted(kinds.items()))
        + f"{unconfirmed} to confirm"
    )
    for note in [*result.notes, *notes]:
        console.print(f"  [dim]{note}[/]")
    for gap in result.gaps:
        console.print(f"  [yellow]Gap:[/] {gap}")
    console.print(f"\n  Draft written to [cyan]{output}[/]")
    console.print(f"  Next: review it, set confirmed: true, then [bold]hrg analyze {output}[/]\n")


def _tolerate_encoding(streams=None):
    """Replace characters a console cannot encode (e.g. cp1252 on Windows) instead of crashing."""
    for stream in streams if streams is not None else (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main():
    """Entry point for CLI."""
    _tolerate_encoding()
    cli()


if __name__ == "__main__":
    main()
