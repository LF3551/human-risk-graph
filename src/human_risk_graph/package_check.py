"""
``hrg check``: how a PyPI package is published, and who could release it alone.

Reads public data only: the package's PyPI metadata and provenance (PEP 740), and its
GitHub repository's deployment environments, releases, deployments, pull request reviews
and commits. Uses the definitions of the two-person study (``publishing``).

People are not named unless ``show_people`` is set: the result says what is wrong and how
to fix it, which is what a maintainer needs, and nothing that points an attacker at an
account. Run it with ``--show-people`` on your own project.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from .activity import DEFAULT_INACTIVE_DAYS
from .publishing import (
    GATE_NAMES,
    PATH_NAMES,
    environment_gate,
    github_repo,
    human_publishers,
    is_dormant,
    latest_release,
    parse_time,
    publish_gate,
    publisher_repository,
    release_path,
)

PYPI = "https://pypi.org"
INTEGRITY = PYPI + "/integrity/{project}/{version}/{filename}/provenance"
PACKAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
REVIEWED_PULLS = 30  # most recent merged pull requests whose reviews count as activity
ACTIVITY_DAYS = 180  # window for reviewers' commits
LEVELS = ("ok", "note", "warning", "error")
GATE_ADVICE = (
    "On the publishing environment, require reviewers, enable Prevent self-review and turn "
    "off the administrator bypass."
)
NO_ENVIRONMENT_ADVICE = (
    "Publish from a GitHub deployment environment that requires reviewers, with Prevent "
    "self-review on and no administrator bypass."
)

Fetch = Callable[[str, str], Optional[Any]]


class CheckError(Exception):
    pass


def fetch_json(url: str, accept: str = "application/json") -> Optional[Any]:
    """GET a PyPI URL as JSON; None when it does not exist."""
    if not url.startswith(PYPI + "/"):
        raise ValueError(f"not a PyPI URL: {url}")
    request = urllib.request.Request(
        url, headers={"Accept": accept, "User-Agent": "human-risk-graph"}
    )
    try:
        # https only: checked above (bandit B310).
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise CheckError(f"PyPI error {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise CheckError(f"Cannot reach PyPI: {getattr(e, 'reason', e)}") from e


# PyPI


@dataclass
class _Release:
    """The latest PyPI release and the publisher of each of its files (None: no provenance)."""

    name: str
    version: Optional[str]
    files: List[str]
    publishers: List[Optional[Dict[str, Any]]]
    info: Dict[str, Any]


def _pypi(package: str, fetch: Fetch, now: datetime) -> _Release:
    if not PACKAGE_NAME.fullmatch(package):
        raise CheckError(f"not a PyPI package name: {package!r}")
    project = fetch(f"{PYPI}/pypi/{urllib.parse.quote(package)}/json", "application/json")
    if not project:
        raise CheckError(f"{package} is not on PyPI")
    info = project.get("info") or {}
    name = info.get("name") or package
    version, files = latest_release(project.get("releases") or {}, now)
    publishers = [_publisher(fetch, name, version, f) for f in files] if version else []
    return _Release(name, version, files, publishers, info)


def _publisher(fetch: Fetch, project: str, version: str, filename: str) -> Optional[Dict]:
    url = INTEGRITY.format(
        project=urllib.parse.quote(project),
        version=urllib.parse.quote(version),
        filename=urllib.parse.quote(filename),
    )
    data = fetch(url, "application/vnd.pypi.integrity.v1+json")
    bundles = (data or {}).get("attestation_bundles") or []
    return bundles[0].get("publisher") if bundles else None


def _repository_of(release: _Release) -> Optional[str]:
    """The GitHub repository from PyPI metadata, else the one every attested file names."""
    attested = {
        publisher_repository(p) for p in release.publishers if p and p.get("kind") == "GitHub"
    }
    return github_repo(release.info) or (attested.pop() if len(attested) == 1 else None)


# GitHub


@dataclass
class _Repository:
    """What ``hrg check`` reads from GitHub about a repository."""

    repo: Optional[str] = None
    visible: bool = False
    environments_visible: bool = False
    gates: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    reviewers: List[str] = field(default_factory=list)
    activity: Dict[str, datetime] = field(default_factory=dict)

    def see(self, login: Optional[str], when: Optional[str]) -> None:
        moment = parse_time(when)
        if login and moment and (login not in self.activity or moment > self.activity[login]):
            self.activity[login] = moment


def _github(client, repo: str, now: datetime, read_reviews: bool) -> _Repository:
    """Environments, publishing events and reviewer activity of a repository."""
    meta = client.get(f"repos/{repo}")
    if not meta:
        return _Repository(repo=repo)
    gh = _Repository(repo=meta["full_name"], visible=True)
    branch = meta.get("default_branch") or "main"
    envs = client.get(f"repos/{gh.repo}/environments")
    gh.environments_visible = envs is not None
    gh.gates = [environment_gate(e) for e in (envs or {}).get("environments") or []]
    _publishing_events(client, gh)
    gh.reviewers = sorted(
        {u for g in gh.gates if g["publishing"] and g["gated"] for u in g["user_reviewers"]}
    )
    if gh.reviewers and read_reviews:
        _review_activity(client, gh, branch)
    since = (now - timedelta(days=ACTIVITY_DAYS)).isoformat()
    for login in gh.reviewers:
        commits = client.get(
            f"repos/{gh.repo}/commits",
            {"sha": branch, "author": login, "since": since, "per_page": 1},
        )
        if commits:
            commit = commits[0].get("commit") or {}
            gh.see(login, (commit.get("committer") or commit.get("author") or {}).get("date"))
    return gh


def _publishing_events(client, gh: _Repository) -> None:
    """GitHub releases and deployments to publishing environments, as (login, when) events."""
    for gate in gh.gates:
        if not gate["publishing"]:
            continue
        for d in client.get(
            f"repos/{gh.repo}/deployments", {"environment": gate["name"], "per_page": 100}
        ) or []:  # fmt: skip
            login = (d.get("creator") or {}).get("login")
            gh.events.append({"login": login, "when": parse_time(d.get("created_at"))})
            gh.see(login, d.get("created_at"))
    for r in client.get(f"repos/{gh.repo}/releases", {"per_page": 100}) or []:
        if not r.get("draft"):
            login = (r.get("author") or {}).get("login")
            gh.events.append({"login": login, "when": parse_time(r.get("published_at"))})
            gh.see(login, r.get("published_at"))


def _review_activity(client, gh: _Repository, branch: str) -> None:
    """Pull requests merged and reviews given, in the most recent merged pull requests."""
    pulls = client.get(
        f"repos/{gh.repo}/pulls",
        {"state": "closed", "base": branch, "sort": "updated", "direction": "desc",
         "per_page": 100},
    ) or []  # fmt: skip
    merged = sorted((p for p in pulls if p.get("merged_at")), key=lambda p: p["merged_at"])
    for pull in merged[-REVIEWED_PULLS:]:
        gh.see((pull.get("user") or {}).get("login"), pull["merged_at"])
        for review in client.get(
            f"repos/{gh.repo}/pulls/{pull['number']}/reviews", {"per_page": 100}
        ) or []:  # fmt: skip
            gh.see((review.get("user") or {}).get("login"), review.get("submitted_at"))


# Check


def check_package(
    package: str,
    client,
    fetch: Fetch = fetch_json,
    now: Optional[datetime] = None,
    repo: Optional[str] = None,
    inactive_days: int = DEFAULT_INACTIVE_DAYS,
    show_people: bool = False,
    read_reviews: bool = True,
) -> Dict[str, Any]:
    """Check how ``package`` is published. Raises CheckError if it cannot be checked."""
    now = now or datetime.now(timezone.utc)
    release = _pypi(package, fetch, now)
    repo = repo or _repository_of(release)
    gh = _github(client, repo, now, read_reviews) if repo else _Repository()
    path = release_path(release.publishers, gh.repo or "", gh.gates) if release.files else "U"
    seen = human_publishers(gh.events, now)
    dormant = [u for u in gh.reviewers if is_dormant(gh.activity.get(u), now, inactive_days)]
    solo = {
        u
        for g in gh.gates
        if g["publishing"] and g["gated"] and g["self_review"]
        for u in g["user_reviewers"]
        if u in dormant
    }
    gate = publish_gate(gh.gates)
    result: Dict[str, Any] = {
        "package": release.name,
        "version": release.version,
        "files": len(release.files),
        "attested_files": sum(1 for p in release.publishers if p),
        "repository": gh.repo,
        "repository_visible": gh.visible,
        "path": path,
        "path_meaning": PATH_NAMES[path],
        "environments": [
            _environment_summary(g, release.publishers) for g in gh.gates if g["publishing"]
        ],
        "configured_gate": gate,
        "configured_gate_meaning": GATE_NAMES[gate],
        "publishers_seen": len(seen),
        "reviewers": len(gh.reviewers),
        "dormant_reviewers": len(dormant),
        "dormant_solo_reviewers": len(solo),
        "inactive_days": inactive_days,
        "checked_at": now.isoformat(timespec="seconds"),
        "notes": _notes(gh, read_reviews, release.files),
    }
    result["findings"] = findings(result)
    if show_people:
        result["people"] = {
            "publishers_seen": sorted(seen),
            "reviewers": gh.reviewers,
            "dormant_reviewers": [
                {
                    "login": u,
                    "last_seen": gh.activity[u].date().isoformat() if u in gh.activity else None,
                    "can_approve_alone": u in solo,
                }
                for u in dormant
            ],
        }
    return result


def _environment_summary(gate: Dict[str, Any], publishers) -> Dict[str, Any]:
    used = any(
        p and (p.get("environment") or "").lower() == gate["name"].lower() for p in publishers
    )
    return {
        "name": gate["name"],
        "used_by_latest_release": used,
        "required_reviewers": len(gate["user_reviewers"]) + len(gate["team_reviewers"]),
        "prevent_self_review": not gate["self_review"],
        "admins_can_bypass": gate["admin_bypass"],
        "two_person_gate": gate["two_person"],
    }


def _notes(gh: _Repository, read_reviews: bool, files: List[str]) -> List[str]:
    notes = []
    if not files:
        notes.append("No release files on PyPI.")
    if not gh.repo:
        notes.append("No GitHub repository found; pass --repo OWNER/REPO.")
    elif not gh.visible:
        notes.append(f"Repository {gh.repo} is not visible to this token.")
    elif not gh.environments_visible:
        notes.append("Deployment environments are not visible.")
    if gh.reviewers and not read_reviews:
        notes.append("Without a GitHub token, reviews are not read: activity is incomplete.")
    if any(g["team_reviewers"] for g in gh.gates if g["publishing"]):
        notes.append("Team reviewers are not checked for activity: team members are not public.")
    return notes


# Findings


def findings(r: Dict[str, Any]) -> List[Dict[str, str]]:
    """What the result means, worst first, each with advice."""
    out = _path_findings(r) + _people_findings(r)
    return sorted(out, key=lambda f: -LEVELS.index(f["level"]))


def _finding(level: str, title: str, advice: str = "") -> Dict[str, str]:
    return {"level": level, "title": title, "advice": advice}


def _path_findings(r: Dict[str, Any]) -> List[Dict[str, str]]:
    path = r["path"]
    used = [e["name"] for e in r["environments"] if e["used_by_latest_release"]]
    where = f" (environment {', '.join(used)})" if used else ""
    by_path = {
        "V2": _finding("ok", f"The latest release went through a two-person gate{where}."),
        "V1": _finding(
            "warning",
            f"The latest release went through a reviewer gate{where} that one person can pass "
            "alone: reviewers can approve their own run, or administrators can bypass it.",
            GATE_ADVICE,
        ),
        "V0": _finding(
            "warning",
            f"The latest release was published without a reviewer gate{where}.",
            GATE_ADVICE if used else NO_ENVIRONMENT_ADVICE,
        ),
        "P": _finding(
            "warning",
            f"Only {r['attested_files']} of {r['files']} files of the latest release have "
            "provenance; the others were uploaded another way, such as an API token.",
            "Publish every file with Trusted Publishing and remove API tokens from the project.",
        ),
        "O": _finding(
            "note",
            "The latest release was published by another repository or service; its gate is "
            "not checked here.",
        ),
        "U": _finding(
            "note",
            "The latest release has no provenance, so how it was published cannot be seen.",
            "Publish with Trusted Publishing and attestations (pypa/gh-action-pypi-publish "
            "creates them by default), from an environment with a two-person gate.",
        ),
    }
    out = [by_path[path]]
    if r["configured_gate"] == "G2" and path in ("V1", "V0", "P"):
        out.append(
            _finding(
                "warning",
                "A two-person gate is configured, but the latest release did not go through it.",
                "Publish only from the gated environment and remove other paths (other "
                "workflows, API tokens).",
            )
        )
    return out


def _people_findings(r: Dict[str, Any]) -> List[Dict[str, str]]:
    out = []
    days = r["inactive_days"]
    if r["dormant_solo_reviewers"]:
        out.append(
            _finding(
                "error",
                f"{r['dormant_solo_reviewers']} reviewer(s) of a publishing environment, with no "
                f"activity seen in the repository for over {days} days, can approve a release "
                "they start themselves.",
                "Confirm each reviewer still needs the role, remove those who do not, and "
                "enable Prevent self-review.",
            )
        )
    elif r["dormant_reviewers"]:
        out.append(
            _finding(
                "warning",
                f"{r['dormant_reviewers']} reviewer(s) of a publishing environment have no "
                f"activity seen in the repository for over {days} days.",
                "Confirm each reviewer still needs the role.",
            )
        )
    if r["publishers_seen"] == 1:
        out.append(
            _finding(
                "warning",
                "One person published every release seen on GitHub in the last year.",
                "Give a second maintainer the ability to release, and document how.",
            )
        )
    return out


def worst_level(result: Dict[str, Any]) -> str:
    return max((f["level"] for f in result["findings"]), key=LEVELS.index, default="ok")


def people_names(result: Dict[str, Any]) -> Set[str]:
    """Every login in a result's ``people`` section (empty without ``show_people``)."""
    people = result.get("people") or {}
    names = set(people.get("publishers_seen", [])) | set(people.get("reviewers", []))
    return names | {d["login"] for d in people.get("dormant_reviewers", [])}
