"""
Helpers for the steps after collection in the two-person study (docs/study-two-person.md).

They read the collection's cache and private rows with the registered functions of
benchmark/two_person.py, so details agree with the results; they never change the data.

Usage:
    python benchmark/two_person_review.py measurement   # checklist for the 40 projects
    python benchmark/two_person_review.py score         # agreement, from the filled checklist
    python benchmark/two_person_review.py disclosure    # channels and draft notifications

Outputs go to benchmark/.private/ (never committed), except the aggregate agreement of the
measurement check, which goes to benchmark/two-person/measurement-check.json.
"""

import argparse
import base64
import csv
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import two_person as tp  # noqa: E402
from validate import Cache, StrictClient  # noqa: E402

from human_risk_graph.github_scan import default_token  # noqa: E402

HERE = Path(__file__).resolve().parent
T0 = date(2026, 11, 14)  # registered reference date of the run
PUBLISH_STEP = re.compile(
    r"pypa/gh-action-pypi-publish|twine\s+upload|uv\s+publish|poetry\s+publish|flit\s+publish"
    r"|hatch\s+publish|maturin\s+(?:publish|upload)",
    re.IGNORECASE,
)
ENVIRONMENT_LINE = re.compile(r"^\s*environment\s*:", re.IGNORECASE)
SECURITY_FILES = ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"https?://[^\s)>\]]+")
CHECK_ITEMS = ("path", "gate", "reviewers")
MARKS = {"x": True, "-": False}


def _t0() -> datetime:
    return datetime.combine(T0, datetime.min.time(), tzinfo=timezone.utc)


def read_rows(private_dir: Path) -> Dict[str, Dict[str, str]]:
    with open(private_dir / "two-person-rows.csv", encoding="utf-8") as fh:
        return {r["repo"]: r for r in csv.DictReader(fh) if r["status"] == "included"}


# Measurement check


def publish_lines(text: str) -> List[Tuple[int, str]]:
    """Lines of a workflow that publish to PyPI or select an environment; [] if it publishes not."""
    all_lines = text.splitlines()
    lines = []
    for number, line in enumerate(all_lines, 1):
        if PUBLISH_STEP.search(line) or ENVIRONMENT_LINE.search(line):
            lines.append((number, line.strip()))
            # "environment:" with the name on the next line ("name: pypi")
            if (
                ENVIRONMENT_LINE.search(line)
                and line.rstrip().endswith(":")
                and number < len(all_lines)
            ):
                lines.append((number + 1, all_lines[number].strip()))
    return lines if any(PUBLISH_STEP.search(line) for _, line in lines) else []


def _workflows(client, cache: Cache, repo: str) -> List[Tuple[str, List[Tuple[int, str]]]]:
    """Workflow files that mention a publishing step, with the relevant lines."""
    listing = cache.get(
        f"rv:workflows:{repo}", lambda: client.get(f"repos/{repo}/contents/.github/workflows")
    )
    found = []
    for entry in listing or []:
        name = entry.get("name") or ""
        if not name.endswith((".yml", ".yaml")):
            continue
        data = cache.get(
            f"rv:workflow:{repo}:{name}",
            lambda name=name: client.get(f"repos/{repo}/contents/.github/workflows/{name}"),
        )
        text = base64.b64decode((data or {}).get("content") or "").decode("utf-8", "replace")
        lines = publish_lines(text)
        if lines:
            found.append((name, lines))
    return found


def _environments(cache: Cache, repo: str) -> List[Dict[str, Any]]:
    envs = cache.get(f"tp:envs:{repo}", lambda: None) or {}
    return [tp.environment_gate(e) for e in envs.get("environments") or []]


def _provenance(cache: Cache, package: str) -> List[Tuple[str, Optional[Dict[str, Any]]]]:
    """Publisher of each file of the latest release, as the collection read it."""
    releases = cache.get(f"tp:pypi-releases:{package}", lambda: {}) or {}
    version, files = tp.latest_release(releases, _t0())
    out = []
    for filename in files:
        bundle = cache.get(f"tp:provenance:{package}:{version}:{filename}", lambda: None)
        bundles = (bundle or {}).get("attestation_bundles") or []
        out.append((filename, bundles[0].get("publisher") if bundles else None))
    return out


def measurement_section(repo: str, row: Dict[str, str], workflows, gates, provenance) -> str:
    """One project of the checklist: what was recorded, the evidence, three items to mark."""
    lines = [
        f"## {repo} (package {row['package']}, rank {row['rank']})",
        "",
        f"Recorded: path **{row['path']}** (latest release {row['latest_version']}, "
        f"{row['release_files']} files), configured gate **{row['gate']}**, "
        f"{row['assessable_reviewers']} user reviewer(s), {row['dormant_90']} dormant at 90 "
        f"days, dormant solo authority {row['dormant_solo_90']}.",
        "",
        "Environments:",
    ]
    lines += [
        f"- `{g['name']}`: publishing {g['publishing']}, gated {g['gated']}, "
        f"{len(g['user_reviewers'])} user + {g['team_reviewers']} team reviewer(s), "
        f"self-review {'allowed' if g['self_review'] else 'prevented'}, "
        f"admin bypass {'allowed' if g['admin_bypass'] else 'off'}"
        for g in gates
    ] or ["- none"]
    lines += ["", "Publishing workflows:"]
    for name, found in workflows:
        lines.append(f"- `.github/workflows/{name}`")
        lines += [f"  - line {number}: `{text}`" for number, text in found]
    if not workflows:
        lines.append("- none found")
    lines += ["", "Provenance of the latest release:"]
    lines += [
        f"- `{filename}`: "
        + (
            f"{p.get('kind')} {tp.publisher_repository(p)} "
            f"{p.get('workflow') or p.get('workflow_filename')} "
            f"environment `{p.get('environment')}`"
            if p
            else "no provenance"
        )
        for filename, p in provenance
    ] or ["- no release"]
    lines += [
        "",
        "Mark each item `[x]` if it agrees with the evidence, `[-]` if not, and explain:",
        "",
        f"- [ ] path: release path {row['path']}",
        f"- [ ] gate: configured gate {row['gate']}",
        f"- [ ] reviewers: {row['assessable_reviewers']} user reviewer(s), "
        f"{row['dormant_90']} dormant",
        "",
        "Notes:",
        "",
    ]
    return "\n".join(lines)


def measurement(client, cache: Cache, private_dir: Path) -> Path:
    rows = read_rows(private_dir)
    repos = (private_dir / "measurement-check.txt").read_text(encoding="utf-8").split()
    sections = [
        "# Measurement check (private)",
        "",
        f"{len(repos)} projects drawn by `measurement_sample` (seed {tp.CHECK_SEED}). Compare "
        "the recorded classes with the evidence below and with the repository and PyPI "
        "pages; then run `python benchmark/two_person_review.py score`.",
        "",
    ]
    for repo in repos:
        row = rows[repo]
        sections.append(
            measurement_section(
                repo, row, _workflows(client, cache, repo), _environments(cache, repo),
                _provenance(cache, row["package"]),
            )  # fmt: skip
        )
    out = private_dir / "measurement-check.md"
    out.write_text("\n".join(sections), encoding="utf-8")
    return out


def score(text: str) -> Dict[str, Any]:
    """Agreement per item and per project from a filled checklist; every item must be marked."""
    projects: Dict[str, Dict[str, bool]] = {}
    current = None
    unmarked = []
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].split(" ")[0]
            projects[current] = {}
            continue
        match = re.match(r"- \[(.)\] (path|gate|reviewers):", line)
        if current and match:
            mark, item = match.groups()
            if mark not in MARKS:
                unmarked.append(f"{current} {item}")
            else:
                projects[current][item] = MARKS[mark]
    if unmarked:
        raise ValueError("not marked yet: " + ", ".join(unmarked))
    result: Dict[str, Any] = {"projects": len(projects)}
    for item in CHECK_ITEMS:
        values = [p[item] for p in projects.values() if item in p]
        result[item] = tp.wilson(sum(values), len(values))
    result["all_three"] = tp.wilson(
        sum(all(p.get(i) for i in CHECK_ITEMS) for p in projects.values()), len(projects)
    )
    return result


# Disclosure


def dormant_solo_details(client, cache: Cache, repo: str) -> List[Dict[str, Any]]:
    """
    The reviewers behind dormant solo authority: user reviewers of a gated publishing
    environment that allows self-approval, with no activity seen in the 90 days before T0.
    Rebuilt with the registered functions from the cached responses.
    """
    t0 = _t0()
    meta = cache.get(f"tp:repo:{repo}", lambda: client.get(f"repos/{repo}"))
    gates = _environments(cache, repo)
    activity: Dict[str, datetime] = {}
    tp._publishing(client, cache, repo, gates, activity)
    _, pull_activity = tp._pull_activity(client, cache, repo, meta["default_branch"])
    for login, moment in pull_activity.items():
        activity[login] = max(moment, activity.get(login, moment))
    reviewers = sorted(
        {u for g in gates if g["publishing"] and g["gated"] for u in g["user_reviewers"]}
    )
    tp._reviewer_commits(client, cache, repo, meta["default_branch"], reviewers, t0, activity)
    return [
        {
            "environment": g["name"],
            "reviewer": login,
            "last_seen": activity[login].date().isoformat() if login in activity else None,
        }
        for g in gates
        if g["publishing"] and g["gated"] and g["self_review"]
        for login in g["user_reviewers"]
        if tp.is_dormant(activity.get(login), t0, tp.DORMANT_DAYS)
    ]


def security_contacts(text: str) -> List[str]:
    """E-mail addresses and links in a security policy, in order, without duplicates."""
    found = EMAIL.findall(text) + [u.rstrip(".,;") for u in URL.findall(text)]
    return list(dict.fromkeys(found))


def channel(client, cache: Cache, repo: str) -> Dict[str, Any]:
    """
    How to tell a project privately: GitHub private vulnerability reporting when enabled,
    otherwise the contacts in its security policy (the repository's, then the owner's
    `.github` repository); otherwise none, and the project is not contacted.
    """
    pvr = cache.get(
        f"rv:pvr:{repo}", lambda: client.get(f"repos/{repo}/private-vulnerability-reporting")
    )
    if (pvr or {}).get("enabled"):
        return {"kind": "private vulnerability reporting",
                "target": f"https://github.com/{repo}/security/advisories/new"}  # fmt: skip
    owner = repo.split("/")[0]
    for source in (repo, f"{owner}/.github"):
        for path in SECURITY_FILES:
            data = cache.get(
                f"rv:security:{source}:{path}",
                lambda source=source, path=path: client.get(f"repos/{source}/contents/{path}"),
            )
            if data and data.get("content"):
                text = base64.b64decode(data["content"]).decode("utf-8", "replace")
                contacts = security_contacts(text)
                if contacts:
                    return {"kind": "security policy", "target": ", ".join(contacts),
                            "policy": f"https://github.com/{source}/blob/HEAD/{path}"}  # fmt: skip
    return {"kind": "none", "target": ""}


MESSAGE = """Subject: A dormant reviewer can approve releases of {repo} alone

Hello,

I am studying how the most downloaded PyPI packages protect publishing (preregistered on
OSF: https://doi.org/10.17605/OSF.IO/J8ZFG). The study reports aggregates only and names no
project or person; I am writing privately so that you can look at this first.

In {repo}, the GitHub environment {environments} requires a reviewer before a release job
runs, and its reviewers can approve a run they started themselves. Among those reviewers,
{reviewers} had no activity visible in this repository in the 90 days before {t0}
(commits, pull requests, reviews, releases or deployments). That is not a judgement on
anyone: people can be active elsewhere. But an account that is no longer used and can
both start and approve a release is an attractive target for takeover.

You may want to confirm that each reviewer still needs the role, and to enable
"Prevent self-review" for the environment so that a second person approves every release.

The report will be published no earlier than {publish_after}. Nothing about {repo} will be
in it beyond aggregate counts. Thank you for maintaining {package}.

{author}
"""


def draft(repo: str, package: str, details: List[Dict[str, Any]], publish_after: str,
          author: str) -> str:  # fmt: skip
    environments = ", ".join(sorted({f"`{d['environment']}`" for d in details}))
    reviewers = ", ".join(sorted({f"@{d['reviewer']}" for d in details}))
    return MESSAGE.format(
        repo=repo, package=package, environments=environments, reviewers=reviewers,
        t0=T0.isoformat(), publish_after=publish_after, author=author,
    )  # fmt: skip


def disclosure(client, cache: Cache, private_dir: Path, publish_after: str, author: str) -> Path:
    rows = read_rows(private_dir)
    flagged = [r for r in rows.values() if r["dormant_solo_90"] == "True"]
    sections = [
        "# Private notifications (private)",
        "",
        f"{len(flagged)} projects with dormant solo authority. Nothing is sent from here; the "
        "author approves and sends each message, then records the date in "
        "`disclosure-log.csv`. Projects without a private channel are not contacted.",
        "",
    ]
    log = [("repo", "package", "channel", "target", "sent_on")]
    for row in sorted(flagged, key=lambda r: int(r["rank"])):
        repo = row["repo"]
        details = dormant_solo_details(client, cache, repo)
        how = channel(client, cache, repo)
        log.append((repo, row["package"], how["kind"], how["target"], ""))
        sections += [f"## {repo}", "", f"Channel: {how['kind']} {how['target']}".rstrip(), ""]
        if how["kind"] == "none":
            sections += ["Not contacted: no private channel (protocol).", ""]
            continue
        sections += ["```", draft(repo, row["package"], details, publish_after, author), "```", ""]
    (private_dir / "disclosure.md").write_text("\n".join(sections), encoding="utf-8")
    with open(private_dir / "disclosure-log.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(log)
    return private_dir / "disclosure.md"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("step", choices=["measurement", "score", "disclosure"])
    parser.add_argument("--private-dir", type=Path, default=HERE / ".private")
    parser.add_argument("--cache-dir", type=Path, default=HERE / ".cache")
    parser.add_argument("--output-dir", type=Path, default=HERE / "two-person")
    parser.add_argument("--publish-after", help="earliest publication date, for the messages")
    parser.add_argument("--author", default="Aleksei Aleinikov")
    args = parser.parse_args(argv)

    if args.step == "score":
        text = (args.private_dir / "measurement-check.md").read_text(encoding="utf-8")
        result = score(text)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        out = args.output_dir / "measurement-check.json"
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    token = default_token()
    if not token:
        print("A GitHub token is required.", file=sys.stderr)
        return 2
    client = StrictClient(token)
    cache = Cache(args.cache_dir)
    step: Callable[[], Path]
    if args.step == "measurement":
        step = lambda: measurement(client, cache, args.private_dir)  # noqa: E731
    else:
        if not args.publish_after:
            parser.error("disclosure needs --publish-after YYYY-MM-DD")
        step = lambda: disclosure(  # noqa: E731
            client, cache, args.private_dir, args.publish_after, args.author
        )
    print(f"Written: {step()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
