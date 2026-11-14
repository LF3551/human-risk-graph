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
import csv
import hashlib
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from click.core import ParameterSource

from . import __version__
from . import diff as diff_module
from .ci_reports import generate_junit_report, generate_sarif_report
from .config import Acceptance, Config, ConfigError, apply_acceptances, load_config
from .console import render_summary
from .activity import DEFAULT_INACTIVE_DAYS, is_inactive
from .findings import Finding, collect_findings, threshold_breach
from .github_scan import (
    API,
    GitHubClient,
    GitHubError,
    GitHubScanner,
    default_token,
    draft_yaml,
    merge_with_existing,
    scan_organization,
)
from .hrg import HumanRiskGraph
from .loader import load_organization, organization_schema
from .model_v2 import MODEL_V2, MODEL_V3, MODELS
from .privacy import KEY_ENV, PseudonymKeyError, Pseudonymizer, load_key
from .reports import (
    generate_html_report,
    generate_json_report,
    generate_markdown_report,
    privacy_text,
)
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
        return data, HumanRiskGraph(data["people"], data["dependencies"], data.get("functions"))
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


def privacy_options(command):
    command = click.option(
        "--pseudonym-key-file",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help=f"File with the pseudonym key (default: the {KEY_ENV} environment variable).",
    )(command)
    return click.option(
        "--pseudonymize/--no-pseudonymize",
        default=False,
        help="Replace people by keyed pseudonyms and drop names, roles and evidence "
        "(also `pseudonymize = true` in hrg.toml).",
    )(command)


def _pseudonymizer(enabled: bool, key_file: Optional[Path], need_key: bool = False):
    """A Pseudonymizer when pseudonymization is on, else None; exits on a bad key."""
    if not enabled:
        return None
    try:
        key = load_key(key_file)
    except (OSError, PseudonymKeyError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    if key is None:
        if need_key:
            click.echo(f"Error: set {KEY_ENV} or --pseudonym-key-file.", err=True)
            sys.exit(1)
        click.echo(
            f"Warning: no pseudonym key ({KEY_ENV} or --pseudonym-key-file); pseudonyms "
            "change on every run, so reports cannot be compared or re-identified.",
            err=True,
        )
    return Pseudonymizer(key)


def _pseudonymized(pz, data):
    """(data, HumanRiskGraph) with pseudonymous people."""
    data = pz.organization(data)
    return data, HumanRiskGraph(data["people"], data["dependencies"], data.get("functions"))


def _setting(ctx, name, cli_value, config_value):
    """The command-line value unless it was left at its default and the config sets one."""
    if config_value is not None and ctx.get_parameter_source(name) == ParameterSource.DEFAULT:
        return config_value
    return cli_value


def _confirmed_only(data, calc):
    """Score without dependencies and functions marked ``confirmed: false``, or None."""
    kept = [d for d in data["dependencies"] if d.get("confirmed") is not False]
    functions = data.get("functions") or []
    kept_functions = [f for f in functions if f.get("confirmed") is not False]
    if len(kept) == len(data["dependencies"]) and len(kept_functions) == len(functions):
        return None
    try:
        results = HumanRiskGraph(data["people"], kept, kept_functions).calculate(
            with_bus_factor=False, **calc
        )
    except ValueError:  # e.g. hrg-3 with no confirmed function left
        return None
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
@click.option(
    "--inactive-days",
    type=click.IntRange(1, 3650),
    default=DEFAULT_INACTIVE_DAYS,
    show_default=True,
    help="hrg-3: people whose last_active is older than this many days are inactive (HRG007).",
)
@click.option("--quiet", "-q", is_flag=True, help="Only print errors.")
@privacy_options
@CONFIG_OPTION
@click.pass_context
def analyze(
    ctx, input_file, formats, output, visualize, fail_above, min_score, model, fix_steps,
    inactive_days, quiet, pseudonymize, pseudonym_key_file, config_path,
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
    pseudonymize = _setting(ctx, "pseudonymize", pseudonymize, config.pseudonymize)
    inactive_days = _setting(ctx, "inactive_days", inactive_days, config.inactive_days)
    calc = {"model": model, **config.calculate_kwargs()}
    thresholds = {"fail_above": fail_above, "min_score": min_score}

    run = _run_analysis(
        input_file, config, calc, pseudonymize, pseudonym_key_file, fix_steps, inactive_days,
        **thresholds,
    )  # fmt: skip
    pz = run.pz
    input_path = Path(input_file)
    base_name = pz.scrub(input_path.stem) if pz else input_path.stem
    output_dir = input_path.parent if not output else Path(output).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = _metadata(input_path, run.data, config, calc, pz)

    formats_to_generate = _expand_formats(formats)
    if output and len(formats_to_generate) == 1:
        targets = {formats_to_generate[0]: Path(output)}  # user specified output file
    else:
        targets = {
            f: output_dir / f"{base_name}_report{EXTENSIONS[f]}" for f in formats_to_generate
        }
    generated_files, failed = _write_reports(targets, run, metadata, input_path, **thresholds)
    if visualize:
        generated_files += _write_visualization(run, output_dir / f"{base_name}_graph.html")

    if not quiet:
        render_summary(
            Console(highlight=False),
            input_file,
            run.data,
            run.results,
            run.findings,
            run.fixes,
            generated_files,
            run.breach,
            config_file=metadata["config_file"],
            confirmed_only=metadata["confirmed_only"],
        )
        if pz:
            click.echo(f"Privacy: {privacy_text(metadata)}")
        hint = inactivity_hint(run.data, run.results.get("model"), inactive_days)
        if hint:
            click.echo(hint)
    _warn_acceptances(run.unused, run.findings)

    if failed:
        sys.exit(1)
    if run.breach:
        if quiet:
            click.echo(f"Error: {run.breach}", err=True)
        sys.exit(EXIT_RISK)


@dataclass
class _Analysis:
    """Everything ``analyze`` computes before writing reports."""

    data: Dict[str, Any]
    hrg: HumanRiskGraph
    pz: Optional[Pseudonymizer]
    results: Dict[str, Any]
    findings: List[Finding]
    unused: List[Acceptance]
    fixes: List[Dict[str, Any]]
    breach: Optional[str]


def _run_analysis(
    input_file, config: Config, calc, pseudonymize, key_file, fix_steps, inactive_days,
    fail_above, min_score,
) -> _Analysis:  # fmt: skip
    """Load, optionally pseudonymize, score, collect findings and plan fixes; exits on errors."""
    data, hrg = _load(input_file)
    pz = _pseudonymizer(pseudonymize, key_file)
    accept = config.accept
    if pz:
        data, hrg = _pseudonymized(pz, data)
        accept = pz.acceptances(accept)
    try:
        results = hrg.calculate(**calc)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    findings = collect_findings(hrg, results, fail_above, min_score, inactive_days)
    findings, unused = apply_acceptances(findings, accept)
    fixes = hrg.fix_plan(steps=fix_steps, **calc) if fix_steps else []
    breach = threshold_breach(results, fail_above, min_score)
    if breach and any(f.rule_id == "HRG004" and f.accepted for f in findings):
        breach = None
    return _Analysis(data, hrg, pz, results, findings, unused, fixes, breach)


def _metadata(input_path: Path, data, config: Config, calc, pz) -> Dict[str, Any]:
    """Report metadata: the input, its size, data quality and how it was processed."""
    person_lookup = {
        person["id"]: {
            "name": person.get("name", person["id"]),
            "role": person.get("role", ""),
            "criticality": person.get("criticality", 0.5),
        }
        for person in data["people"]
    }
    functions = data.get("functions") or []
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
        "dependency_type_counts": dict(
            Counter(dep.get("type", "unknown") for dep in data["dependencies"])
        ),
        "config_file": config.path.name if config.path else None,
        "unconfirmed_dependencies": sum(
            1 for d in data["dependencies"] if d.get("confirmed") is False
        ),
        "functions_count": len(functions),
        "unconfirmed_functions": sum(1 for f in functions if f.get("confirmed") is False),
        "coverage_gaps": [
            str(gap) for gap in ((data.get("coverage") or {}).get("gaps") or []) if gap
        ],
        "confirmed_only": _confirmed_only(data, calc),
        "pseudonymized": ({"method": "HMAC-SHA256", "stable": pz.stable} if pz else None),
    }
    if pz:
        # A file name such as anna-org.yaml would identify someone too.
        metadata["input_file"] = pz.scrub(metadata["input_file"])
        metadata["input_name"] = pz.scrub(metadata["input_name"])
    return metadata


def _expand_formats(formats) -> List[str]:
    """Requested formats in order, without duplicates; 'all' is json, markdown and html."""
    expanded: List[str] = []
    for fmt in formats:
        names = ("json", "markdown", "html") if fmt.lower() == "all" else (fmt.lower(),)
        expanded += [f for f in names if f not in expanded]
    return expanded


def _render_report(
    fmt: str, run: _Analysis, metadata, input_path: Path, fail_above, min_score
) -> str:
    if fmt == "json":
        return generate_json_report(run.results, metadata, run.findings, run.fixes)
    if fmt == "markdown":
        return generate_markdown_report(run.results, metadata, run.findings, run.fixes)
    if fmt == "html":
        return generate_html_report(run.results, metadata, run.findings, run.fixes, run.hrg)
    if fmt == "sarif":
        pz = run.pz
        return generate_sarif_report(
            run.findings,
            pz.scrub(_artifact_uri(input_path)) if pz else _artifact_uri(input_path),
            input_path.read_text(encoding="utf-8"),
            {p: i for i, p in pz.mapping.items()} if pz else None,
        )
    return generate_junit_report(run.findings, run.results, fail_above, min_score)


def _write_reports(
    targets: Dict[str, Path], run: _Analysis, metadata, input_path: Path, fail_above, min_score
) -> Tuple[List[str], bool]:
    """Write each format to its file; returns the files written and whether any failed."""
    written = []
    failed = False
    for fmt, output_file in targets.items():
        try:
            content = _render_report(fmt, run, metadata, input_path, fail_above, min_score)
            output_file.write_text(content, encoding="utf-8")
            written.append(str(output_file))
        except Exception as e:
            failed = True
            click.echo(f"Error: failed to generate {fmt} report: {e}", err=True)
    return written, failed


def _write_visualization(run: _Analysis, viz_file: Path) -> List[str]:
    """The interactive graph; a failure is only a warning."""
    try:
        generate_graph_visualization(run.hrg, run.results, str(viz_file))
    except Exception as e:
        click.echo(f"Warning: failed to generate visualization: {e}", err=True)
        return []
    return [str(viz_file)]


def inactivity_hint(data: Dict[str, Any], model: Optional[str], days: int) -> Optional[str]:
    """
    Outside hrg-3, a pointer to the people the data mark as inactive: HRG007 only runs on
    functions, and without this they would go unnoticed under the default model.
    """
    if model == MODEL_V3:
        return None
    inactive = sum(1 for p in data["people"] if is_inactive(p.get("last_active"), days))
    if not inactive:
        return None
    people = f"{inactive} {'person has' if inactive == 1 else 'people have'}"
    if data.get("functions"):
        return (
            f"Note: {people} no activity seen for over {days} days (last_active); "
            "run with --model hrg-3 to see which functions rely on them (HRG007)."
        )
    return f"Note: {people} no activity seen for over {days} days (last_active)."


def _warn_acceptances(unused: List[Acceptance], findings: List[Finding]) -> None:
    """Warn about risk acceptances that match nothing or have expired."""
    for acceptance in unused:
        target = f" {acceptance.target}" if acceptance.target else ""
        click.echo(
            f"Warning: risk acceptance {acceptance.rule}{target} matches no finding "
            "and can be removed from the config.",
            err=True,
        )
    for finding in findings:
        expired = finding.acceptance
        if finding.acceptance_expired and expired and expired.expires:
            click.echo(
                f"Warning: risk acceptance for {finding.key} expired on "
                f"{expired.expires.isoformat()}.",
                err=True,
            )


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", type=click.Path(), help="Output HTML file")
@privacy_options
def visualize(input_file, output, pseudonymize, pseudonym_key_file):
    """
    Generate interactive graph visualization only.

    INPUT_FILE: JSON or YAML file with people and dependencies.
    """
    data, hrg = _load(input_file)
    pz = _pseudonymizer(pseudonymize, pseudonym_key_file)
    if pz:
        data, hrg = _pseudonymized(pz, data)

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
@privacy_options
@CONFIG_OPTION
@click.pass_context
def diff(
    ctx, old_file, new_file, fmt, output, fail_on_increase, model, pseudonymize,
    pseudonym_key_file, config_path,
):  # fmt: skip
    """
    Compare two snapshots of an organization.

    Shows score and metric changes, added, removed and changed people and
    dependencies, and single points of failure that appeared or disappeared.

    Example:
        hrg diff org-2026-q1.yaml org-2026-q2.yaml --format markdown
    """
    config = _config(config_path)
    model = _setting(ctx, "model", model, config.model)
    pseudonymize = _setting(ctx, "pseudonymize", pseudonymize, config.pseudonymize)
    old_data, _ = _load(old_file)
    new_data, _ = _load(new_file)
    pz = _pseudonymizer(pseudonymize, pseudonym_key_file)
    if pz:
        old_data, new_data = pz.organization(old_data), pz.organization(new_data)
    try:
        changes = diff_module.compare(old_data, new_data, model=model, **config.calculate_kwargs())
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

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


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--pseudonym-key-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=f"File with the pseudonym key (default: the {KEY_ENV} environment variable).",
)
def pseudonyms(input_file, pseudonym_key_file):
    """
    Print the pseudonym of every person in an organization file (CSV).

    For re-identification by whoever holds the key, for example the data protection
    officer answering "who is P-3f9a2c1d?". Needs the key the reports were made with.

    Example:
        HRG_PSEUDONYM_KEY=... hrg pseudonyms org.yaml > pseudonyms.csv
    """
    data, _ = _load(input_file)
    pz = _pseudonymizer(True, pseudonym_key_file, need_key=True)
    pz.organization(data)
    names = {p["id"]: p.get("name") or p["id"] for p in data["people"]}
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["pseudonym", "id", "name"])
    for pseudonym, pid in pz.table():
        writer.writerow([pseudonym, pid, names.get(pid, pid)])


@cli.group()
def scan():
    """Build a draft organization file from real data."""


@scan.command("github")
@click.argument("repo", required=False)
@click.option(
    "--org",
    help="Scan the repositories of this organization (or user) instead of one REPO.",
)
@click.option(
    "--max-repos",
    type=click.IntRange(1, 1000),
    default=30,
    show_default=True,
    help="With --org: most recently pushed repositories to scan.",
)
@click.option("--include-archived", is_flag=True, help="With --org: also archived repositories.")
@click.option("--include-forks", is_flag=True, help="With --org: also forks.")
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Draft file to write (default: REPO-org.yaml or ORG-org.yaml). An existing draft is updated.",
)
@click.option("--branch", help="Protected branch to analyze (default: the default branch).")
@click.option(
    "--max-prs",
    type=click.IntRange(1, 1000),
    default=None,
    help="Most recent merged pull requests to read per repository [default: 100; 30 with --org].",
)
@click.option("--include-bots", is_flag=True, help="Keep bot accounts such as dependabot[bot].")
@click.option(
    "--activity/--no-activity",
    default=True,
    show_default=True,
    help="Record when people with authority over a function were last active (last_active), "
    "for the inactive-performer finding (HRG007).",
)
@click.option(
    "--token",
    envvar="HRG_GITHUB_TOKEN",
    help="GitHub token (default: GITHUB_TOKEN, GH_TOKEN or `gh auth token`).",
)
@click.option(
    "--api-url",
    envvar=["HRG_GITHUB_API_URL", "GITHUB_API_URL"],
    default=API,
    show_default=True,
    help="GitHub API, e.g. https://github.example.com/api/v3 for GitHub Enterprise Server "
    "(GITHUB_API_URL, set in GitHub Actions, is used when present).",
)
def scan_github(
    repo, org, max_repos, include_archived, include_forks, output, branch, max_prs, include_bots,
    activity, token, api_url,
):  # fmt: skip
    """
    Draft an organization from a GitHub repository or a whole organization.

    REPO is OWNER/NAME. Reads pull request reviews, CODEOWNERS, branch rules, merges
    without review, releases and deployment environments, and writes a YAML draft where
    every dependency and function has its source, evidence and confirmed: false. Review
    the draft, then run hrg analyze on it.

    With --org, the most recently pushed repositories of the organization are scanned and
    merged into one draft: people appear once, and the merge, release, admin and deploy
    functions are kept per repository, so a person who is the only releaser of many
    services shows up.

    Example:
        hrg scan github my-org/payments-api
        hrg scan github --org my-org --max-repos 50
        hrg analyze payments-api-org.yaml
    """
    if bool(repo) == bool(org):
        raise click.UsageError("Give either REPO (OWNER/NAME) or --org ORG.")
    if org and branch:
        raise click.UsageError(
            "--branch applies to one repository; with --org the default branch of each is used."
        )
    max_prs = max_prs or (30 if org else 100)
    label = org or repo
    console = Console(stderr=True, highlight=False)
    output = output or Path(f"{(org or repo.split('/')[-1])}-org.yaml")
    existing = _existing_draft(output)
    client = _github_client(token, api_url)
    if not client.token:
        console.print("[yellow]No GitHub token: limited to 60 requests per hour.[/]")
    try:
        with console.status(f"Scanning {label}") as status:
            if org:
                result = scan_organization(
                    client,
                    org,
                    max_repos=max_repos,
                    max_prs=max_prs,
                    include_bots=include_bots,
                    record_activity=activity,
                    include_archived=include_archived,
                    include_forks=include_forks,
                    progress=status.update,
                )
            else:
                scanner = GitHubScanner(
                    client,
                    repo,
                    branch=branch,
                    max_prs=max_prs,
                    include_bots=include_bots,
                    record_activity=activity,
                    progress=lambda message: status.update(f"{repo}: {message}"),
                )
                result = scanner.scan()
    except (GitHubError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    notes = merge_with_existing(result, existing)
    output.write_text(draft_yaml(result, notes), encoding="utf-8")
    _print_scan_summary(console, label, result, notes, output, is_org=bool(org))


def _existing_draft(output: Path) -> Optional[Dict[str, Any]]:
    """The draft a re-scan updates, or None; exits if it cannot be read."""
    if not output.exists():
        return None
    try:
        return load_organization(output)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _github_client(token: Optional[str], api_url: str) -> GitHubClient:
    try:
        return GitHubClient(token or default_token(api_url), api=api_url)
    except ValueError as e:
        raise click.BadParameter(str(e), param_hint="--api-url") from None


def _print_scan_summary(console: Console, label, result, notes, output: Path, is_org) -> None:
    kinds = Counter(d["type"] for d in result.dependencies)
    unconfirmed = sum(1 for d in result.dependencies if d.get("confirmed") is False)
    where = f"{len(result.repositories)} repositories" if is_org else result.branch
    console.print(
        f"\n[bold]{label}[/] · {result.pull_requests} merged PRs on {where} · "
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
