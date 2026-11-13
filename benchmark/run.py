"""
Benchmark: does `hrg scan github` find the people a project declares as approvers?

For each repository in repos.yaml, the declared approvers come from a governance file the
scanner does not read (MAINTAINERS, OWNERS). The scanner's approvers are the people who
gave approving reviews on recent merged pull requests. Reported per repository:

- precision: share of observed approvers who are declared approvers
- recall: share of declared approvers seen approving in the window
- approvals by declared: share of all approving reviews given by declared approvers
- release authors declared: share of people who published releases (the hrg-3 release
  function) who are declared approvers

Usage:
    python benchmark/run.py [--max-prs 100] [--only OWNER/REPO] [--output FILE]

Needs a GitHub token (GITHUB_TOKEN, GH_TOKEN or `gh auth login`). Prints a Markdown
report and writes the raw results as JSON.
"""

import argparse
import base64
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import yaml

from human_risk_graph import __version__
from human_risk_graph.github_scan import GitHubClient, GitHubError, GitHubScanner, default_token

HERE = Path(__file__).resolve().parent

# @handle or github.com/handle; not an e-mail address, a team (@org/team) or a deeper URL.
HANDLE = re.compile(
    r"(?:(?<![\w.@/])@|github\.com/)([A-Za-z0-9][A-Za-z0-9-]{0,38})(?![\w/-]|\.[A-Za-z])"
)
STOP = re.compile(r"^\s*(?:#+\s*)?(?:emeritus|retired|former|alumni)\b", re.I | re.M)


def handles(text: str) -> Set[str]:
    """GitHub handles mentioned before the first emeritus/retired section."""
    stop = STOP.search(text)
    return {h.lower() for h in HANDLE.findall(text[: stop.start()] if stop else text)}


def owners(text: str, aliases_text: Optional[str], keys: Iterable[str]) -> Set[str]:
    """Handles in the given lists of a Kubernetes OWNERS file, with aliases resolved."""
    data = yaml.safe_load(text) or {}
    aliases = (yaml.safe_load(aliases_text) or {}).get("aliases") or {} if aliases_text else {}
    found: Set[str] = set()
    for key in keys:
        for name in data.get(key) or []:
            members = (aliases[name] or []) if name in aliases else [name]
            found |= {m.lower() for m in members}
    return found


def evaluate(declared: Set[str], approvals: Dict[str, int]) -> Dict[str, Any]:
    observed = {login.lower(): n for login, n in approvals.items()}
    matched = set(observed) & declared
    total = sum(observed.values())
    ranked = sorted(observed, key=lambda h: (-observed[h], h))
    return {
        "declared": len(declared),
        "approvers": len(observed),
        "matched": len(matched),
        "precision": len(matched) / len(observed) if observed else None,
        "recall": len(matched) / len(declared) if declared else None,
        "approvals_by_declared": sum(observed[h] for h in matched) / total if total else None,
        "top_approver_declared": ranked[0] in declared if ranked else None,
        "undeclared_approvers": [[h, observed[h]] for h in ranked if h not in declared],
        "inactive_declared": sorted(declared - set(observed)),
    }


def evaluate_releases(declared: Set[str], functions: List[Dict[str, Any]]) -> Dict[str, Any]:
    release = next((f for f in functions if f["id"] == "release"), None)
    authors = {p.lower() for p in release["performers"]} if release else set()
    return {
        "release_authors": len(authors),
        "release_authors_declared": len(authors & declared) / len(authors) if authors else None,
    }


def _file(client: GitHubClient, repo: str, path: str) -> Optional[str]:
    data = client.get(f"repos/{repo}/contents/{path}")
    if not data or not data.get("content"):
        return None
    return base64.b64decode(data["content"]).decode("utf-8", "replace")


def declared_approvers(client: GitHubClient, entry: Dict[str, Any]) -> Set[str]:
    repo, path = entry["repo"], entry["governance"]
    if ":" in path:
        repo, path = path.split(":", 1)
    text = _file(client, repo, path)
    if text is None:
        raise GitHubError(f"{repo}:{path} not found")
    if entry["format"] == "owners":
        aliases_path = str(Path(path).parent / "OWNERS_ALIASES").lstrip("./")
        return owners(text, _file(client, repo, aliases_path), entry["keys"])
    return handles(text)


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def markdown(run: Dict[str, Any]) -> str:
    rows = [r for r in run["repos"] if "error" not in r]
    lines = [
        f"Run on {run['date']} with human-risk-graph {run['tool_version']}, "
        f"up to {run['max_prs']} merged pull requests per repository.",
        "",
        "| Repository | PRs | Declared | Approvers | Precision | Recall "
        "| Approvals by declared | Top approver declared | Release authors declared "
        "| Reviews required |",
        "|---|---:|---:|---:|---:|---:|---:|:---:|---:|:---:|",
    ]
    for r in rows:
        m = r["metrics"]
        rel = r.get("releases") or {}
        authors = rel.get("release_authors")
        release_cell = (
            f"{_pct(rel.get('release_authors_declared'))} of {authors}" if authors else "n/a"
        )
        lines.append(
            f"| {r['repo']} | {r['pull_requests']} | {m['declared']} | {m['approvers']} "
            f"| {_pct(m['precision'])} | {_pct(m['recall'])} "
            f"| {_pct(m['approvals_by_declared'])} "
            f"| {'yes' if m['top_approver_declared'] else 'no'} | {release_cell} "
            f"| {r['review_required']} |"
        )
    totals = run["totals"]
    lines += [
        f"| **All** | {totals['pull_requests']} | {totals['declared']} | {totals['approvers']} "
        f"| **{_pct(totals['precision'])}** | **{_pct(totals['recall'])}** "
        f"| **{_pct(totals['approvals_by_declared'])}** | "
        f"| **{_pct(totals.get('release_authors_declared'))}** of "
        f"{totals.get('release_authors', 0)} | |",
        "",
    ]
    for r in run["repos"]:
        if "error" in r:
            lines.append(f"- **{r['repo']}**: error: {r['error']}")
            continue
        m = r["metrics"]
        undeclared = m["undeclared_approvers"]
        lines.append(
            f"- **{r['repo']}**: {len(undeclared)} approvers not declared "
            f"({sum(n for _, n in undeclared)} approvals); "
            f"{len(m['inactive_declared'])} declared approvers with no approval in the window"
        )
    return "\n".join(lines) + "\n"


def totals(repos: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [r for r in repos if "error" not in r]
    s = {k: sum(r["metrics"][k] for r in ok) for k in ("declared", "approvers", "matched")}
    approvals = sum(sum(r["approvals_given"].values()) for r in ok)
    by_declared = sum(
        r["metrics"]["approvals_by_declared"] * sum(r["approvals_given"].values())
        for r in ok
        if r["metrics"]["approvals_by_declared"] is not None
    )
    releases = [r.get("releases") or {} for r in ok]
    release_authors = sum(rel.get("release_authors") or 0 for rel in releases)
    release_declared = sum(
        (rel.get("release_authors_declared") or 0) * (rel.get("release_authors") or 0)
        for rel in releases
    )
    return {
        **s,
        "pull_requests": sum(r["pull_requests"] for r in ok),
        "precision": s["matched"] / s["approvers"] if s["approvers"] else None,
        "recall": s["matched"] / s["declared"] if s["declared"] else None,
        "approvals_by_declared": by_declared / approvals if approvals else None,
        "release_authors": release_authors,
        "release_authors_declared": (
            release_declared / release_authors if release_authors else None
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--max-prs", type=int, default=100)
    parser.add_argument("--only", help="Run a single repository from repos.yaml")
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args(argv)

    entries = yaml.safe_load((HERE / "repos.yaml").read_text(encoding="utf-8"))
    if args.only:
        entries = [e for e in entries if e["repo"] == args.only]
    client = GitHubClient(default_token())
    repos = []
    for entry in entries:
        print(f"{entry['repo']} ...", file=sys.stderr)
        try:
            declared = declared_approvers(client, entry)
            result = GitHubScanner(client, entry["repo"], max_prs=args.max_prs).scan()
        except (GitHubError, ValueError) as e:
            repos.append({"repo": entry["repo"], "error": str(e)})
            continue
        repos.append(
            {
                "repo": entry["repo"],
                "governance": entry["governance"],
                "pull_requests": result.pull_requests,
                "review_required": {True: "yes", False: "no", None: "unknown"}[
                    result.review_required
                ],
                "gaps": len(result.gaps),
                "approvals_given": result.approvals_given,
                "metrics": evaluate(declared, result.approvals_given),
                "releases": evaluate_releases(declared, result.functions),
            }
        )
    run = {
        "date": date.today().isoformat(),
        "tool_version": __version__,
        "max_prs": args.max_prs,
        "api_calls": client.calls,
        "repos": repos,
        "totals": totals(repos),
    }
    args.output.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    print(markdown(run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
