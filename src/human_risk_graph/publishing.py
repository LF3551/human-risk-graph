"""
How a package is published, and whether a second person stands in the way.

Shared definitions of ``hrg check`` and the two-person study (docs/study-two-person.md);
the study's registered code keeps its own copy of the same functions.

- A *publishing environment* is a GitHub deployment environment whose name looks like a
  production or publishing target (the rule of ``hrg scan github``).
- An environment is *gated* when its required-reviewers rule names someone, and a
  *two-person gate* when reviewers also cannot approve their own run and administrators
  cannot bypass it.
- The *release path* of the latest release comes from PyPI provenance (PEP 740): which
  repository, workflow and environment published each file.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .github_scan import PRODUCTION_LIKE, _is_bot

PATHS = ("U", "P", "O", "V0", "V1", "V2")  # weakest first
PATH_NAMES = {
    "V2": "published through a two-person gate",
    "V1": "published through a reviewer gate one person can pass alone",
    "V0": "published without a reviewer gate",
    "O": "published by another repository or service",
    "P": "only some files have provenance",
    "U": "no provenance: the path is not observable",
}
GATES = ("G2", "G1", "G0", "NE")
GATE_NAMES = {
    "G2": "a two-person gate",
    "G1": "a reviewer gate one person can pass alone",
    "G0": "publishing environments without reviewers",
    "NE": "no publishing environment",
}
URL_KEYS = ("source", "source code", "repository", "code", "github", "homepage")
GITHUB_URL = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)", re.I)
NOT_REPOS = {"sponsors", "orgs", "apps", "features", "marketplace", "topics", "collections"}


def parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def github_repo(info: Dict[str, Any]) -> Optional[str]:
    """OWNER/REPO from PyPI project metadata, preferring source-like links."""
    urls = {(k or "").strip().lower(): v for k, v in (info.get("project_urls") or {}).items()}
    ordered = [urls[k] for k in URL_KEYS if k in urls]
    ordered += [v for k, v in sorted(urls.items()) if k not in URL_KEYS]
    ordered.append(info.get("home_page") or "")
    for url in ordered:
        match = GITHUB_URL.search(url or "")
        if match and match.group(1).lower() not in NOT_REPOS:
            repo = re.sub(r"\.git$", "", match.group(2))
            if repo:
                return f"{match.group(1)}/{repo}"
    return None


def is_publishing(name: str) -> bool:
    return bool(PRODUCTION_LIKE.search(name or ""))


def environment_gate(env: Dict[str, Any]) -> Dict[str, Any]:
    """Required reviewers of one environment and whether they make a two-person gate."""
    rule = next(
        (r for r in env.get("protection_rules") or [] if r.get("type") == "required_reviewers"),
        None,
    )
    users: List[str] = []
    teams: List[str] = []
    for entry in (rule or {}).get("reviewers") or []:
        reviewer = entry.get("reviewer") or {}
        if entry.get("type") == "Team":
            teams.append(reviewer.get("slug") or "team")
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
        "team_reviewers": sorted(set(teams)),
    }


def publish_gate(gates: Iterable[Dict[str, Any]]) -> str:
    """The strongest gate configured on a publishing environment (G2 > G1 > G0 > NE)."""
    publishing = [g for g in gates if g["publishing"]]
    if not publishing:
        return "NE"
    if any(g["two_person"] for g in publishing):
        return "G2"
    if any(g["gated"] for g in publishing):
        return "G1"
    return "G0"


def latest_release(
    releases: Dict[str, List[Dict[str, Any]]], now: datetime
) -> Tuple[Optional[str], List[str]]:
    """The version whose last non-yanked upload before ``now`` is the most recent, and its files."""
    best: Tuple[Optional[datetime], Optional[str]] = (None, None)
    for version, files in releases.items():
        times = [parse_time(f.get("upload_time_iso_8601")) for f in files if not f.get("yanked")]
        before = [t for t in times if t and t < now]
        if before and (best[0] is None or max(before) > best[0]):
            best = (max(before), version)
    latest = best[1]
    if latest is None:
        return None, []
    return latest, sorted(
        f["filename"]
        for f in releases[latest]
        if not f.get("yanked") and (parse_time(f.get("upload_time_iso_8601")) or now) < now
    )


def publisher_repository(publisher: Dict[str, Any]) -> str:
    """OWNER/REPO of a GitHub publisher: ``repository`` (PyPI) or owner and name (PEP 740)."""
    if publisher.get("repository"):
        return str(publisher["repository"])
    owner, name = publisher.get("repository_owner"), publisher.get("repository_name")
    return f"{owner}/{name}" if owner and name else ""


def release_path(
    publishers: Sequence[Optional[Dict[str, Any]]], repo: str, gates: List[Dict[str, Any]]
) -> str:
    """Class of the path the latest release took; the weakest file decides."""
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


def human_publishers(events: Iterable[Dict[str, Any]], now: datetime, days: int = 365) -> Set[str]:
    """People (not bots) behind publishing events (``login``, ``when``) in the window."""
    start = now - timedelta(days=days)
    return {
        e["login"]
        for e in events
        if e.get("login") and e.get("when") and start <= e["when"] < now and not _is_bot(e["login"])
    }


def is_dormant(last_seen: Optional[datetime], now: datetime, days: int) -> bool:
    return last_seen is None or last_seen < now - timedelta(days=days)
