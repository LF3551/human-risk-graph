"""
Who can ship it alone? Two-person control and dormant authority over publishing in the
1,000 most downloaded PyPI packages.

Protocol: docs/study-two-person.md, registered on OSF before any data was collected.

Usage:
    python benchmark/two_person.py --t0 YYYY-MM-DD [--limit 1000] [--offset 0]

Needs a GitHub token (GITHUB_TOKEN, GH_TOKEN or `gh auth login`) of an account without
push access to the sampled repositories. API responses are cached in benchmark/.cache/ so
an interrupted run resumes. Per-repository rows go to benchmark/.private/ (not committed,
see the protocol's publication rules); only aggregates are written to
benchmark/two-person/results.json.
"""

import argparse
import csv
import json
import math
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate import (  # noqa: E402  (shared collection helpers of the first study)
    Cache,
    StrictClient,
    _http_json,
    github_repo,
    parse_time,
    pypi_summary,
)

from human_risk_graph import __version__  # noqa: E402
from human_risk_graph.github_scan import (  # noqa: E402
    PRODUCTION_LIKE,
    GitHubError,
    _is_bot,
    default_token,
)

HERE = Path(__file__).resolve().parent
FRAME_URL = (
    "https://raw.githubusercontent.com/hugovk/top-pypi-packages/"
    "29c0d4c38c28c0e6b99e73fa09cb91a2323ca51b/top-pypi-packages.min.json"
)
FRAME_SIZE = 1000
ACTIVE_DAYS = 365  # a PyPI upload in this window makes a package eligible
PUBLISH_DAYS = 365  # window for human publishers (RQ2)
DORMANT_DAYS = 90  # primary inactivity threshold (RQ3)
DORMANT_DAYS_SENSITIVITY = 180
PULLS = 50  # most recent merged pull requests read per repository (RQ4)
CLOSED_PULLS = 300  # closed pull requests read to find them (bots and unmerged ones are many)
MIN_APPROVED_PULLS = 10
EFFECTIVE_APPROVERS_SINGLE = 2.0  # below this, review rests on one person (HRG002 error)
TOP_RANK = 100  # exploratory split by popularity
CHECK_SIZE = 40  # included projects checked by hand against their workflows (measurement check)
CHECK_SEED = 20261114

GATES = ("G2", "G1", "G0", "NE")
# Path of the latest release, from PyPI provenance (PEP 740), weakest first.
PATHS = ("U", "P", "O", "V0", "V1", "V2")
PATH_NAMES = {
    "V2": "every file published through a two-person gate",
    "V1": "every file through a gated environment that allows self-approval or admin bypass",
    "V0": "every file attested, at least one through an ungated environment or none",
    "O": "attested by another publisher than this GitHub repository",
    "P": "only some files attested",
    "U": "no file attested: path not observable",
}
INTEGRITY = "https://pypi.org/integrity/{project}/{version}/{filename}/provenance"
GATE_NAMES = {
    "G2": "two-person gate",
    "G1": "self-approvable gate",
    "G0": "publishing environment without reviewers",
    "NE": "no publishing environment visible",
}


# Pure functions (unit-tested in tests/test_two_person.py)


def is_publishing(name: str) -> bool:
    """A publishing environment, by the name rule of `hrg scan github` 0.16.0."""
    return bool(PRODUCTION_LIKE.search(name or ""))


def environment_gate(env: Dict[str, Any]) -> Dict[str, Any]:
    """Required reviewers of one environment and whether they make a two-person gate."""
    rule = next(
        (r for r in env.get("protection_rules") or [] if r.get("type") == "required_reviewers"),
        None,
    )
    users: List[str] = []
    teams = 0
    for entry in (rule or {}).get("reviewers") or []:
        reviewer = entry.get("reviewer") or {}
        if entry.get("type") == "Team":
            teams += 1
        elif reviewer.get("login") and not _is_bot(reviewer["login"]):
            users.append(reviewer["login"])
    self_review = not (rule or {}).get("prevent_self_review", False)
    admin_bypass = env.get("can_admins_bypass", True)
    gated = rule is not None and bool(users or teams)
    return {
        "name": env.get("name") or "",
        "publishing": is_publishing(env.get("name") or ""),
        "gated": gated,
        "two_person": gated and not self_review and not admin_bypass,
        "self_review": self_review,
        "admin_bypass": admin_bypass,
        "user_reviewers": sorted(set(users)),
        "team_reviewers": teams,
    }


def publish_gate(gates: Iterable[Dict[str, Any]], any_name: bool = False) -> str:
    """
    G2: a publishing environment with a two-person gate; G1: gated, but self-approval or
    admin bypass is allowed; G0: publishing environments without reviewers; NE: none.
    With ``any_name`` (sensitivity analysis), an environment with required reviewers counts
    as publishing whatever its name.
    """
    publishing = [g for g in gates if g["publishing"] or (any_name and g["gated"])]
    if not publishing:
        return "NE"
    if any(g["two_person"] for g in publishing):
        return "G2"
    if any(g["gated"] for g in publishing):
        return "G1"
    return "G0"


def latest_release(
    releases: Dict[str, List[Dict[str, Any]]], t0: datetime
) -> Tuple[Optional[str], List[str]]:
    """The version whose last non-yanked upload before t0 is the most recent, and all its files."""
    best: Tuple[Optional[datetime], Optional[str]] = (None, None)
    for version, files in releases.items():
        times = [parse_time(f.get("upload_time_iso_8601")) for f in files if not f.get("yanked")]
        before = [t for t in times if t and t < t0]
        if before and (best[0] is None or max(before) > best[0]):
            best = (max(before), version)
    latest = best[1]
    if latest is None:
        return None, []
    names = sorted(
        f["filename"]
        for f in releases[latest]
        if not f.get("yanked") and (parse_time(f.get("upload_time_iso_8601")) or t0) < t0
    )
    return latest, names


def publisher_repository(publisher: Dict[str, Any]) -> str:
    """
    OWNER/REPO of a GitHub Trusted Publisher. PyPI's integrity API returns ``repository``;
    PEP 740's example uses ``repository_owner`` and ``repository_name``. Both are read.
    """
    if publisher.get("repository"):
        return str(publisher["repository"])
    owner, name = publisher.get("repository_owner"), publisher.get("repository_name")
    return f"{owner}/{name}" if owner and name else ""


def release_path(
    publishers: List[Optional[Dict[str, Any]]], repo: str, gates: List[Dict[str, Any]]
) -> str:
    """
    Class of the path the latest release took, from the publisher of each file's
    provenance (None: no provenance). The weakest file decides.
    """
    attested = [p for p in publishers if p]
    if not attested:
        return "U"
    if len(attested) < len(publishers):
        return "P"
    by_name = {g["name"].lower(): g for g in gates}
    classes = []
    for p in attested:
        if p.get("kind") != "GitHub" or publisher_repository(p).lower() != repo.lower():
            return "O"
        gate = by_name.get((p.get("environment") or "").lower())
        classes.append(
            "V2" if gate and gate["two_person"] else "V1" if gate and gate["gated"] else "V0"
        )
    return min(classes, key=PATHS.index)


def human_publishers(
    releases: Iterable[Dict[str, Any]],
    deployments: Iterable[Dict[str, Any]],
    t0: datetime,
    days: int = PUBLISH_DAYS,
) -> Set[str]:
    """People (not bots) who published a GitHub release or deployed to a publishing environment."""
    start = t0 - timedelta(days=days)
    people = set()
    for item in [*releases, *deployments]:
        when, login = item.get("when"), item.get("login")
        if login and when and start <= when < t0 and not _is_bot(login):
            people.add(login)
    return people


def standing_approvals(reviews: List[Dict[str, Any]], author: str) -> List[str]:
    """
    People other than the author (not bots) whose approval stood: their latest review that
    changes the state is an approval. A later request for changes, or a dismissed approval,
    withdraws it; comments do not (GitHub's rule).
    """
    state: Dict[str, bool] = {}
    for r in sorted(reviews, key=lambda r: r.get("submitted_at") or ""):
        login = (r.get("user") or {}).get("login")
        if not login or _is_bot(login) or login == author:
            continue
        if r.get("state") == "APPROVED":
            state[login] = True
        elif r.get("state") in ("CHANGES_REQUESTED", "DISMISSED"):
            state[login] = False
    return sorted(login for login, approved in state.items() if approved)


def effective_approvers(counts: Dict[str, int]) -> Optional[float]:
    """1 / Herfindahl-Hirschman index of approvals per approver."""
    total = sum(counts.values())
    if not total:
        return None
    return 1 / sum((n / total) ** 2 for n in counts.values())


def is_dormant(last_active: Optional[datetime], t0: datetime, days: int) -> bool:
    """No activity seen in the ``days`` before ``t0``."""
    return last_active is None or last_active < t0 - timedelta(days=days)


def wilson(k: int, n: int, z: float = 1.959964) -> Dict[str, Optional[float]]:
    """Proportion with a Wilson score 95% interval."""
    if not n:
        return {"k": k, "n": n, "p": None, "low": None, "high": None}
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return {"k": k, "n": n, "p": p, "low": max(0.0, centre - half), "high": min(1.0, centre + half)}


def _share(rows: Sequence[Dict[str, Any]], test: Callable[[Dict[str, Any]], bool]):
    return wilson(sum(1 for r in rows if test(r)), len(rows))


def analyze(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Every analysis of the protocol, from the included rows."""
    rows = [r for r in rows if r["status"] == "included"]
    gated = [r for r in rows if r["gate"] in ("G1", "G2") and r["assessable_reviewers"]]
    publishers = [r for r in rows if r["publishers"] > 0]
    reviewed = [r for r in rows if r["approved_pulls"] >= MIN_APPROVED_PULLS]
    required = [r for r in reviewed if r["review_required_visible"]]

    def by_group(test, subset):
        return {
            "organization": _share([r for r in subset if r["owner_type"] == "Organization"], test),
            "user": _share([r for r in subset if r["owner_type"] != "Organization"], test),
            f"rank_1_{TOP_RANK}": _share([r for r in subset if r["rank"] <= TOP_RANK], test),
            f"rank_{TOP_RANK + 1}_plus": _share([r for r in subset if r["rank"] > TOP_RANK], test),
        }

    def no_two_person(r):
        return r["gate"] != "G2"

    def single(r):
        return r["publishers"] == 1

    return {
        "included": len(rows),
        "rq1_publish_gate": {
            "primary_no_observed_two_person_path": _share(rows, lambda r: r["path"] != "V2"),
            "latest_release_path": _shares(rows, "path", PATHS),
            "configured_gate_by_path": {
                g: _shares([r for r in rows if r["gate"] == g], "path", PATHS) for g in GATES
            },
            "secondary_no_configured_two_person_gate": _share(rows, no_two_person),
            "median_latest_release_age_days": _median(
                [r["release_age_days"] for r in rows if r.get("release_age_days") is not None]
            ),
            "distribution": _gate_shares(rows, "gate"),
            "sensitivity_any_environment_name": _gate_shares(rows, "gate_any_name"),
            "exploratory_by_group": by_group(lambda r: r["path"] != "V2", rows),
        },
        "rq2_single_publisher": {
            "primary": _share(publishers, single),
            "no_visible_publisher": len(rows) - len(publishers),
            "exploratory_by_group": by_group(single, publishers),
        },
        "rq3_dormant_authority": {
            "primary_gated_with_dormant_reviewer": _share(gated, lambda r: r["dormant_90"] > 0),
            "primary_dormant_solo_authority": _share(rows, lambda r: r["dormant_solo_90"]),
            "sensitivity_180_days": {
                "gated_with_dormant_reviewer": _share(gated, lambda r: r["dormant_180"] > 0),
                "dormant_solo_authority": _share(rows, lambda r: r["dormant_solo_180"]),
            },
            "gated_with_team_reviewers_only": sum(
                1 for r in rows if r["gate"] in ("G1", "G2") and not r["assessable_reviewers"]
            ),
        },
        "rq4_review_concentration": {
            "primary_single_reviewer": _share(
                reviewed, lambda r: r["effective_approvers"] < EFFECTIVE_APPROVERS_SINGLE
            ),
            "review_visibly_required": _share(
                required, lambda r: r["effective_approvers"] < EFFECTIVE_APPROVERS_SINGLE
            ),
            "exploratory_unapproved_merges_where_required": _median(
                [r["unapproved_share"] for r in required]
            ),
        },
    }


def _shares(rows: Sequence[Dict[str, Any]], key: str, classes: Sequence[str]) -> Dict[str, Any]:
    counts = Counter(r[key] for r in rows)
    return {c: wilson(counts[c], len(rows)) for c in classes}


def _gate_shares(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, Any]:
    return _shares(rows, key, GATES)


def measurement_sample(rows: List[Dict[str, Any]], size: int = CHECK_SIZE) -> List[str]:
    """Repositories for the manual measurement check: a seeded random draw of included rows."""
    included = sorted(r["repo"] for r in rows if r["status"] == "included")
    return sorted(random.Random(CHECK_SEED).sample(included, min(size, len(included))))


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


# Collection


def _get_json(url: str, accept: str = "application/json") -> Optional[Any]:
    request = urllib.request.Request(
        url, headers={"Accept": accept, "User-Agent": "human-risk-graph-study"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _release_path(cache: Cache, package: str, repo: str, gates, t0: datetime) -> Dict[str, Any]:
    """Provenance of the latest PyPI release before t0 and the path class it gives."""
    data = cache.get(
        f"tp:pypi-releases:{package}",
        lambda: (_get_json(f"https://pypi.org/pypi/{urllib.parse.quote(package)}/json") or {}).get(
            "releases", {}
        ),
    )
    version, files = latest_release(data, t0)
    uploads = [
        parse_time(f.get("upload_time_iso_8601"))
        for f in (data.get(version) or [] if version else [])
        if f.get("filename") in files
    ]
    uploaded = max((u for u in uploads if u), default=None)
    publishers: List[Optional[Dict[str, Any]]] = []
    for filename in files:
        url = INTEGRITY.format(project=package, version=version, filename=filename)
        bundle = cache.get(
            f"tp:provenance:{package}:{version}:{filename}",
            lambda url=url: _get_json(url, "application/vnd.pypi.integrity.v1+json"),
        )
        bundles = (bundle or {}).get("attestation_bundles") or []
        publishers.append(bundles[0].get("publisher") if bundles else None)
    return {
        "latest_version": version,
        "release_files": len(files),
        "release_age_days": (t0 - uploaded).days if uploaded else None,
        "path": release_path(publishers, repo, gates) if files else "U",
    }


def _items(client, cache: Cache, key: str, path: str, params=None, limit: int = 0) -> List[Any]:
    return cache.get(key, lambda: client.get(path, params, limit) or [])


def _pull_activity(client, cache, repo: str, branch: str) -> Tuple[List[Dict[str, Any]], Dict]:
    """The last PULLS merged human pull requests into ``branch``, with approvals by others."""
    pulls = _items(
        client, cache, f"tp:pulls:{repo}", f"repos/{repo}/pulls",
        {"state": "closed", "base": branch, "sort": "updated", "direction": "desc",
         "per_page": 100},
        CLOSED_PULLS,
    )  # fmt: skip
    merged = [
        p
        for p in pulls
        if p.get("merged_at")
        and (p.get("user") or {}).get("login")
        and not _is_bot(p["user"]["login"])
    ]
    merged.sort(key=lambda p: p["merged_at"], reverse=True)
    out: List[Dict[str, Any]] = []
    activity: Dict[str, datetime] = {}
    for p in merged[:PULLS]:
        author = p["user"]["login"]
        _seen(activity, author, p["merged_at"])
        reviews = _items(
            client, cache, f"tp:reviews:{repo}:{p['number']}",
            f"repos/{repo}/pulls/{p['number']}/reviews", {"per_page": 100},
        )  # fmt: skip
        for r in reviews:
            login = (r.get("user") or {}).get("login")
            if login and not _is_bot(login) and login != author:
                _seen(activity, login, r.get("submitted_at"))
        out.append({"approvers": standing_approvals(reviews, author)})
    return out, activity


def _seen(activity: Dict[str, datetime], login: Optional[str], when: Optional[str]) -> None:
    moment = parse_time(when)
    if login and moment and (login not in activity or moment > activity[login]):
        activity[login] = moment


def _publishing(client, cache, repo: str, gates, activity) -> Tuple[List[Dict], List[Dict]]:
    """Releases and deployments to publishing environments, as (login, when) items."""
    deployments: List[Dict[str, Any]] = []
    for g in gates:
        if not g["publishing"]:
            continue
        for d in _items(
            client, cache, f"tp:deployments:{repo}:{g['name']}", f"repos/{repo}/deployments",
            {"environment": g["name"], "per_page": 100},
        ):  # fmt: skip
            login = (d.get("creator") or {}).get("login")
            deployments.append({"login": login, "when": parse_time(d.get("created_at"))})
            _seen(activity, login, d.get("created_at"))
    releases: List[Dict[str, Any]] = []
    for r in _items(client, cache, f"tp:releases:{repo}", f"repos/{repo}/releases",
                    {"per_page": 100}):  # fmt: skip
        if not r.get("draft"):
            login = (r.get("author") or {}).get("login")
            releases.append({"login": login, "when": parse_time(r.get("published_at"))})
            _seen(activity, login, r.get("published_at"))
    return releases, deployments


def _reviewer_commits(client, cache, repo, branch, reviewers, t0, activity) -> None:
    """Each reviewer's latest commit on the default branch in the sensitivity window."""
    since = (t0 - timedelta(days=DORMANT_DAYS_SENSITIVITY)).isoformat()
    for login in reviewers:
        commits = _items(
            client, cache, f"tp:commits:{repo}:{login}", f"repos/{repo}/commits",
            {"sha": branch, "author": login, "since": since, "until": t0.isoformat(),
             "per_page": 1},
        )  # fmt: skip
        if commits:
            commit = commits[0].get("commit") or {}
            when = (commit.get("committer") or commit.get("author") or {}).get("date")
            _seen(activity, login, when)


def _dormancy(gates, reviewers, activity, t0) -> Dict[str, Any]:
    def dormant(login: str, days: int) -> bool:
        return is_dormant(activity.get(login), t0, days)

    def dormant_solo(days: int) -> bool:
        return any(
            g["publishing"] and g["gated"] and g["self_review"] and dormant(u, days)
            for g in gates
            for u in g["user_reviewers"]
        )

    return {
        "assessable_reviewers": len(reviewers),
        "dormant_90": sum(1 for u in reviewers if dormant(u, DORMANT_DAYS)),
        "dormant_180": sum(1 for u in reviewers if dormant(u, DORMANT_DAYS_SENSITIVITY)),
        "dormant_solo_90": dormant_solo(DORMANT_DAYS),
        "dormant_solo_180": dormant_solo(DORMANT_DAYS_SENSITIVITY),
    }


def _review(pulls: List[Dict[str, Any]], rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    approvals = Counter(a for p in pulls for a in p["approvers"])
    approved = sum(1 for p in pulls if p["approvers"])
    effective = effective_approvers(dict(approvals))
    return {
        "review_required_visible": any(
            r.get("type") == "pull_request"
            and (r.get("parameters") or {}).get("required_approving_review_count", 0) >= 1
            for r in rules
        ),
        "merged_pulls": len(pulls),
        "approved_pulls": approved,
        "effective_approvers": round(effective, 3) if effective is not None else None,
        "unapproved_share": round(1 - approved / len(pulls), 3) if pulls else None,
    }


def collect_repo(client, cache, repo: str, t0: datetime, package: str) -> Dict[str, Any]:
    meta = cache.get(f"tp:repo:{repo}", lambda: client.get(f"repos/{repo}"))
    if not meta:
        return {"status": "excluded: repository not reachable"}
    if meta.get("archived"):
        return {"repo": meta["full_name"], "status": "excluded: archived"}
    repo, branch = meta["full_name"], meta["default_branch"]

    envs = cache.get(f"tp:envs:{repo}", lambda: client.get(f"repos/{repo}/environments"))
    gates = [environment_gate(e) for e in (envs or {}).get("environments") or []]
    activity: Dict[str, datetime] = {}
    releases, deployments = _publishing(client, cache, repo, gates, activity)
    rules = _items(client, cache, f"tp:rules:{repo}", f"repos/{repo}/rules/branches/{branch}")
    pulls, pull_activity = _pull_activity(client, cache, repo, branch)
    for login, moment in pull_activity.items():
        activity[login] = max(moment, activity.get(login, moment))
    reviewers = sorted(
        {u for g in gates if g["publishing"] and g["gated"] for u in g["user_reviewers"]}
    )
    _reviewer_commits(client, cache, repo, branch, reviewers, t0, activity)
    return {
        "repo": repo,
        "owner_type": (meta.get("owner") or {}).get("type"),
        "gate": publish_gate(gates),
        "gate_any_name": publish_gate(gates, any_name=True),
        **_release_path(cache, package, repo, gates, t0),
        "publishing_environments": sum(1 for g in gates if g["publishing"]),
        "publishers": len(human_publishers(releases, deployments, t0)),
        **_dormancy(gates, reviewers, activity, t0),
        **_review(pulls, rules),
        "status": "included",
    }


def frame(cache: Cache, offset: int, limit: int) -> List[Dict[str, Any]]:
    rows = cache.get(f"frame:{FRAME_URL}", lambda: _http_json(FRAME_URL))["rows"]
    return rows[offset : offset + limit]


def collect(client, cache: Cache, t0: datetime, offset: int, limit: int, log) -> List[Dict]:
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for rank, entry in enumerate(frame(cache, offset, limit), offset + 1):
        package = entry["project"]
        pypi = cache.get(f"pypi:{package}", lambda: pypi_summary(package))
        base = {"rank": rank, "package": package}
        repo = github_repo(pypi["info"]) if pypi else None
        if not repo:
            rows.append({**base, "status": "excluded: no GitHub repository"})
            continue
        uploads = [parse_time(t) for t in pypi["times"]]
        if not any(u and t0 - timedelta(days=ACTIVE_DAYS) <= u < t0 for u in uploads):
            rows.append({**base, "repo": repo, "status": "excluded: no PyPI upload in a year"})
            continue
        for attempt in range(5):
            try:
                row = collect_repo(client, cache, repo, t0, package)
                break
            except GitHubError as e:
                if "rate limit" not in str(e) or attempt == 4:
                    raise
                log(f"{package}: rate limit reached, waiting 15 minutes")
                time.sleep(900)
        key = row.get("repo", repo).lower()
        if key in seen:
            rows.append({**base, "repo": row.get("repo", repo), "status": "excluded: duplicate"})
            continue
        seen.add(key)
        rows.append({**base, **row})
        if rank % 25 == 0:
            log(f"{rank - offset}/{limit} packages, {client.calls} GitHub calls")
    return rows


COLUMNS = (
    "rank package repo status owner_type gate gate_any_name path latest_version release_files "
    "release_age_days "
    "publishing_environments "
    "publishers assessable_reviewers dormant_90 dormant_180 dormant_solo_90 dormant_solo_180 "
    "review_required_visible merged_pulls approved_pulls effective_approvers unapproved_share"
).split()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--t0", type=date.fromisoformat, required=True,
                        help="reference date, the UTC day collection starts")  # fmt: skip
    parser.add_argument("--offset", type=int, default=0, help="first frame position (pilot)")
    parser.add_argument("--limit", type=int, default=FRAME_SIZE)
    parser.add_argument("--output-dir", type=Path, default=HERE / "two-person")
    parser.add_argument("--private-dir", type=Path, default=HERE / ".private")
    parser.add_argument("--cache-dir", type=Path, default=HERE / ".cache")
    args = parser.parse_args(argv)

    token = default_token()
    if not token:
        print("A GitHub token is required.", file=sys.stderr)
        return 2
    t0 = datetime.combine(args.t0, datetime.min.time(), tzinfo=timezone.utc)
    client = StrictClient(token)
    rows = collect(
        client, Cache(args.cache_dir), t0, args.offset, args.limit,
        lambda m: print(m, file=sys.stderr),
    )  # fmt: skip

    args.private_dir.mkdir(parents=True, exist_ok=True)
    (args.private_dir / "measurement-check.txt").write_text(
        "\n".join(measurement_sample(rows)) + "\n", encoding="utf-8"
    )
    with open(args.private_dir / "two-person-rows.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    results = {
        "protocol": "docs/study-two-person.md",
        "hrg_version": __version__,
        "t0": args.t0.isoformat(),
        "frame": FRAME_URL,
        "frame_positions": [args.offset + 1, args.offset + args.limit],
        "packages": len(rows),
        "exclusions": dict(Counter(r["status"] for r in rows if r["status"] != "included")),
        "github_calls": client.calls,
        "analyses": analyze(rows),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results["analyses"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
