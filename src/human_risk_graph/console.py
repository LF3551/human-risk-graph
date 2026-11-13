"""Terminal summary for ``hrg analyze``."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import __version__
from .findings import Finding, acceptance_text
from .model_v2 import MODEL_V1

GRADE_STYLE = {"A": "bold green", "B": "green", "C": "yellow", "D": "dark_orange", "F": "bold red"}
LEVEL_STYLE = {"error": "red", "warning": "yellow", "note": "blue"}
BAR_WIDTH = 10


def _bar(score: int, style: str) -> Text:
    filled = round(score / 100 * BAR_WIDTH)
    return Text("█" * filled, style=style) + Text("░" * (BAR_WIDTH - filled), style="dim")


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _metric_rows(results: Dict[str, Any], name) -> List[tuple]:
    if results.get("model") == MODEL_V1:
        return [
            ("Bus factor", f"{results['bus_factor']:.3f}"),
            ("Decision", f"{results['decision_concentration']:.3f} (Gini)"),
            ("Bypass", f"{results['bypass_risk']:.3f}"),
        ]

    rows = []
    key_people = results.get("key_people", [])
    bus = results.get("bus_factor_people")
    bus_text = f"bus factor {bus} · " if bus else ""
    if key_people:
        top = key_people[0]
        rows.append(
            (
                "Key people",
                f"{bus_text}losing {name(top['id'])} cuts off "
                f"{top['cut_off']} {'person' if top['cut_off'] == 1 else 'people'} "
                f"({top['impact']:.0%} of connections)",
            )
        )
    else:
        rows.append(("Key people", f"{bus_text}no single point of failure"))

    shares = results.get("approval_shares", {})
    if shares:
        top_id, top_share = next(iter(shares.items()))
        rows.append(
            (
                "Approvals",
                f"{results['effective_approvers']:.1f} effective approvers of {len(shares)} · "
                f"{name(top_id)} holds {top_share:.0%}",
            )
        )
    else:
        rows.append(("Approvals", "no approvals in the data"))

    rows.append(
        (
            "Overrides",
            f"{len(results.get('overridable_approvals', []))} of "
            f"{results.get('critical_approvals', 0)} critical approvals can be overridden",
        )
    )
    return rows


def render_summary(
    console: Console,
    input_file: str,
    data: Dict[str, Any],
    results: Dict[str, Any],
    findings: List[Finding],
    fixes: List[Dict[str, Any]],
    generated: List[str],
    breach: Optional[str] = None,
    config_file: Optional[str] = None,
) -> None:
    names = {p["id"]: p.get("name") or p["id"] for p in data["people"]}

    def name(person_id: str) -> str:
        return names.get(person_id, person_id)

    people, deps = len(data["people"]), len(data["dependencies"])
    console.print()
    console.print(
        Text.assemble(
            ("Human Risk Graph ", "bold"),
            (__version__, "dim"),
            " · ",
            (Path(input_file).name, "cyan"),
            f" · {people} {'person' if people == 1 else 'people'}",
            f" · {deps} {'dependency' if deps == 1 else 'dependencies'}",
            (f" · config {config_file}" if config_file else "", "dim"),
        )
    )
    console.print()

    grade_style = GRADE_STYLE.get(results["grade"], "bold")
    headline = Table.grid(padding=(0, 2))
    headline.add_column()
    headline.add_column()
    headline.add_column()
    headline.add_column(justify="right")
    headline.add_row(
        Text("  Score", style="bold"),
        Text(f"{results['score']}/100", style=grade_style),
        _bar(results["score"], grade_style)
        + Text(f"  {results['grade']} · {results['risk_level']} risk", style=grade_style),
        Text(f"model {results.get('model')}", style="dim"),
    )
    console.print(headline)
    console.print()

    metrics = Table.grid(padding=(0, 2))
    metrics.add_column(style="bold", min_width=12)
    metrics.add_column()
    for label, value in _metric_rows(results, name):
        metrics.add_row(f"  {label}", value)
    console.print(metrics)

    if fixes:
        console.print()
        console.print(Text("  Top fixes", style="bold"))
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="right", style="dim")
        table.add_column()
        table.add_column(justify="right", no_wrap=True)
        table.add_column(justify="right", style="green", no_wrap=True)
        for i, fix in enumerate(fixes, 1):
            table.add_row(
                f"  {i}",
                fix["title"],
                f"{fix['score_before']} → {fix['score_after']}",
                f"+{fix['score_after'] - fix['score_before']}",
            )
        console.print(table)

    accepted = [f for f in findings if f.accepted]
    findings = [f for f in findings if not f.accepted]
    errors = sum(1 for f in findings if f.level == "error")
    console.print()
    console.print(
        Text.assemble(
            ("  Findings  ", "bold"),
            (_plural(errors, "error"), "red" if errors else "dim"),
            " · ",
            (_plural(len(findings) - errors, "warning"), "yellow" if findings else "dim"),
            (f" · {len(accepted)} accepted" if accepted else "", "dim"),
        )
    )
    rows = Table.grid(padding=(0, 1))
    rows.add_column(no_wrap=True)
    rows.add_column(no_wrap=True, style="bold")
    rows.add_column()
    for finding in findings:
        rows.add_row(
            Text("   ▲" if finding.level == "error" else "   △", LEVEL_STYLE[finding.level]),
            finding.rule_id,
            finding.message,
        )
    for finding in accepted:
        rows.add_row(
            Text("   ✓", "green"),
            Text(finding.rule_id, style="dim"),
            Text(f"Accepted: {finding.message} ({acceptance_text(finding)})", style="dim"),
        )
    console.print(rows)

    if generated:
        console.print()
        console.print(Text("  Reports", style="bold"))
        for path in generated:
            console.print(Text(f"   {path}", style="cyan"))
    if breach:
        console.print()
        console.print(Text(f"  ✗ {breach}", style="bold red"))
    console.print()
