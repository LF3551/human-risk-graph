"""
Build a draft organization from a GitHub repository.

Evidence used, all readable with a token that can read the repository:

- Pull request reviews: who approved whose merged pull requests (``approval``).
- CODEOWNERS: who must approve changes to the files a pull request touched (``approval``).
- Pull requests merged without an approving review from someone else, when the branch
  visibly requires reviews (``bypass`` from the person who merged to the approvers).
- Branch rules and ruleset bypass actors, when the token can see them (``bypass``).

Technical permissions and history do not prove real authority, so every dependency is
written with ``source``, ``evidence`` and ``confirmed: false`` for a person to review, and
what the token could not see is listed under ``coverage.gaps``.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

API = "https://api.github.com"
CODEOWNERS_PATHS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
ADMIN_ROLE_ID = 5  # built-in "admin" repository role in ruleset bypass actors


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    """Minimal REST client: GET with pagination; returns None for 403/404 on optional data."""

    def __init__(self, token: Optional[str] = None, api: str = API):
        self.token = token
        self.api = api.rstrip("/")
        self.calls = 0
        self._lock = threading.Lock()

    def _request(self, url: str):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "human-risk-graph",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        with self._lock:
            self.calls += 1
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8")), response.headers.get("Link")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 409, 422):
                if e.code == 403 and e.headers.get("X-RateLimit-Remaining") == "0":
                    raise GitHubError(
                        "GitHub API rate limit reached; use a token (--token, GITHUB_TOKEN "
                        "or `gh auth login`)"
                    ) from e
                return None, None
            if e.code == 401:
                raise GitHubError("GitHub rejected the token (401)") from e
            raise GitHubError(f"GitHub API error {e.code} for {url}") from e
        except urllib.error.URLError as e:
            raise GitHubError(f"Cannot reach GitHub: {e.reason}") from e

    def get(self, path: str, params: Optional[Dict[str, Any]] = None, limit: int = 0):
        """GET a path. Lists are followed across pages up to ``limit`` items (0: one page)."""
        url = f"{self.api}/{path.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data, link = self._request(url)
        if not isinstance(data, list) or not limit:
            return data
        items = list(data)
        while link and len(items) < limit:
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            if not match:
                break
            page, link = self._request(match.group(1))
            if not page:
                break
            items.extend(page)
        return items[:limit]


def default_token() -> Optional[str]:
    """GITHUB_TOKEN, GH_TOKEN, or the token of a logged-in GitHub CLI."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    if shutil.which("gh"):
        try:
            out = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, timeout=10, check=False
            )
            return out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None
    return None


# CODEOWNERS


def _pattern_regex(pattern: str) -> "re.Pattern[str]":
    """Translate a CODEOWNERS (gitignore-style) pattern to a regex over repository paths."""
    anchored = pattern.startswith("/")
    body = pattern.strip("/")
    out, i = [], 0
    while i < len(body):
        if body.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif body.startswith("**", i):
            out.append(".*")
            i += 2
        elif body[i] == "*":
            out.append("[^/]*")
            i += 1
        elif body[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(body[i]))
            i += 1
    prefix = "(?:.*/)?" if not anchored and "/" not in body else ""
    # "docs/*" matches files directly in docs/, not in its subdirectories.
    suffix = "" if body.endswith("/*") else "(?:/.*)?"
    return re.compile(f"^{prefix}{''.join(out)}{suffix}$")


def parse_codeowners(text: str) -> List[Tuple["re.Pattern[str]", str, List[str]]]:
    """Rules as (regex, pattern, owners) in file order; the last matching rule wins."""
    rules = []
    for line in text.splitlines():
        line = re.sub(r"(?<!\\)#.*", "", line).strip()
        if not line:
            continue
        pattern, *owners = line.split()
        rules.append((_pattern_regex(pattern), pattern, [o for o in owners if o.startswith("@")]))
    return rules


def owners_for(path: str, rules) -> List[str]:
    owners: List[str] = []
    for regex, _, rule_owners in rules:
        if regex.match(path):
            owners = rule_owners
    return owners


# Scan


@dataclass
class Edge:
    weight: float
    sources: Set[str] = field(default_factory=set)
    evidence: List[str] = field(default_factory=list)


@dataclass
class ScanResult:
    repo: str
    branch: str
    pull_requests: int
    people: List[Dict[str, Any]]
    dependencies: List[Dict[str, Any]]
    notes: List[str]
    api_calls: int
    review_required: Optional[bool] = None
    gaps: List[str] = field(default_factory=list)

    def coverage(self) -> Dict[str, Any]:
        return {
            "source": f"github {self.repo}",
            "branch": self.branch,
            "pull_requests": self.pull_requests,
            "review_required": (
                "unknown" if self.review_required is None else self.review_required
            ),
            "gaps": self.gaps,
        }


def _is_bot(login: str) -> bool:
    return login.endswith("[bot]")


class GitHubScanner:
    def __init__(
        self,
        client: GitHubClient,
        repo: str,
        branch: Optional[str] = None,
        max_prs: int = 100,
        include_bots: bool = False,
        progress: Optional[Callable[[str], None]] = None,
    ):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ValueError(f"expected OWNER/REPO, got {repo!r}")
        self.client = client
        self.repo = repo
        self.org = repo.split("/")[0]
        self.branch = branch
        self.max_prs = max_prs
        self.include_bots = include_bots
        self.progress = progress or (lambda message: None)
        self.notes: List[str] = []
        self.gaps: List[str] = []
        self.team_members: Dict[str, Optional[List[str]]] = {}

    # Helpers

    def _keep(self, login: Optional[str]) -> bool:
        if not login:
            return False
        return self.include_bots or not _is_bot(login)

    def _expand(self, owner: str) -> List[str]:
        """@user -> [user]; @org/team -> members if visible, else the team handle."""
        handle = owner.lstrip("@")
        if "/" not in handle:
            return [handle]
        if handle not in self.team_members:
            org, slug = handle.split("/", 1)
            members = self.client.get(f"orgs/{org}/teams/{slug}/members", {"per_page": 100}, 500)
            if members is None:
                self.gaps.append(f"Members of team @{handle} are not visible; kept as one node.")
            self.team_members[handle] = [m["login"] for m in members] if members else None
        return self.team_members[handle] or [f"@{handle}"]

    def _codeowners(self):
        for path in CODEOWNERS_PATHS:
            data = self.client.get(f"repos/{self.repo}/contents/{path}", {"ref": self.branch})
            if data and data.get("content"):
                text = base64.b64decode(data["content"]).decode("utf-8", "replace")
                self.notes.append(f"CODEOWNERS read from {path}.")
                return parse_codeowners(text)
        self.notes.append("No CODEOWNERS file found.")
        return []

    def _bypass_actors(self) -> Tuple[Set[str], Optional[bool]]:
        """People who can bypass branch rules, and whether reviews are required (None: unknown)."""
        actors: Set[str] = set()
        review_required: Optional[bool] = False
        rules = self.client.get(f"repos/{self.repo}/rules/branches/{self.branch}")
        ruleset_ids = set()
        for rule in rules or []:
            ruleset_ids.add(rule.get("ruleset_id"))
            if rule.get("type") == "pull_request":
                params = rule.get("parameters") or {}
                if params.get("required_approving_review_count") or params.get(
                    "require_code_owner_review"
                ):
                    review_required = True
        for ruleset_id in sorted(i for i in ruleset_ids if i):
            ruleset = self.client.get(
                f"repos/{self.repo}/rulesets/{ruleset_id}", {"includes_parents": "true"}
            )
            bypass = (ruleset or {}).get("bypass_actors")
            if bypass is None:
                self.gaps.append(
                    f"Bypass actors of ruleset {ruleset_id} are not visible (needs admin access)."
                )
                continue
            for actor in bypass:
                actors |= self._actor_logins(actor)

        branch = self.client.get(f"repos/{self.repo}/branches/{self.branch}") or {}
        protection = self.client.get(f"repos/{self.repo}/branches/{self.branch}/protection")
        if protection:
            reviews = protection.get("required_pull_request_reviews") or {}
            if reviews.get("required_approving_review_count") or reviews.get(
                "require_code_owners_reviews"
            ):
                review_required = True
            allowances = reviews.get("bypass_pull_request_allowances") or {}
            actors |= {u["login"] for u in allowances.get("users", [])}
            for team in allowances.get("teams", []):
                actors |= set(self._expand(f"@{self.org}/{team['slug']}"))
            if reviews and not (protection.get("enforce_admins") or {}).get("enabled"):
                actors |= self._admins("branch protection does not apply to admins")
        elif branch.get("protected") and not rules:
            self.gaps.append(
                f"Branch {self.branch} is protected but its protection settings are not "
                "visible (needs admin access): required reviews and bypass allowances unknown."
            )
            review_required = None
        elif branch.get("protected"):
            self.gaps.append(
                f"Classic protection settings of {self.branch} are not visible (needs admin "
                "access); only rulesets were read."
            )
            review_required = review_required or None
        return {a for a in actors if self._keep(a)}, review_required

    def _admins(self, why: str) -> Set[str]:
        admins = self.client.get(
            f"repos/{self.repo}/collaborators", {"permission": "admin", "per_page": 100}, 500
        )
        if admins is None:
            self.gaps.append(f"Repository admins are not visible ({why}; needs push access).")
            return set()
        return {a["login"] for a in admins}

    def _actor_logins(self, actor: Dict[str, Any]) -> Set[str]:
        kind = actor.get("actor_type")
        if kind == "RepositoryRole" and actor.get("actor_id") == ADMIN_ROLE_ID:
            return self._admins("admins are ruleset bypass actors")
        if kind == "OrganizationAdmin":
            owners = self.client.get(
                f"orgs/{self.org}/members", {"role": "admin", "per_page": 100}, 500
            )
            if owners is None:
                self.gaps.append("Organization owners can bypass rules but are not visible.")
                return set()
            return {o["login"] for o in owners}
        if kind == "Team":
            team = self.client.get(f"teams/{actor.get('actor_id')}")
            if team and team.get("slug"):
                return set(self._expand(f"@{self.org}/{team['slug']}"))
            self.gaps.append(f"Team {actor.get('actor_id')} can bypass rules but is not visible.")
            return set()
        self.notes.append(f"Bypass actor of type {kind} ignored (not a person).")
        return set()

    # Main

    def scan(self) -> ScanResult:
        repo = self.client.get(f"repos/{self.repo}")
        if repo is None:
            raise GitHubError(f"Repository {self.repo} not found or not visible to this token")
        self.branch = self.branch or repo["default_branch"]

        self.progress("Reading CODEOWNERS and branch rules")
        codeowners = self._codeowners()
        only_default_rule = all(pattern in ("*", "/*", "**") for _, pattern, _ in codeowners)
        bypassers, review_required = self._bypass_actors()
        if review_required:
            self.notes.append(f"Branch {self.branch} requires approving reviews.")
        elif review_required is False:
            self.notes.append(f"Branch {self.branch} does not require approving reviews.")

        self.progress(f"Reading up to {self.max_prs} merged pull requests")
        pulls = self.client.get(
            f"repos/{self.repo}/pulls",
            {"state": "closed", "base": self.branch, "sort": "updated", "direction": "desc",
             "per_page": 100},
            self.max_prs * 2,
        ) or []  # fmt: skip
        merged = [
            p
            for p in pulls
            if p.get("merged_at") and self._keep((p.get("user") or {}).get("login"))
        ][: self.max_prs]

        authored: Counter = Counter()
        approvals: Dict[Tuple[str, str], int] = Counter()
        owner_reviews: Dict[Tuple[str, str], int] = Counter()
        unreviewed_merges: Dict[str, List[int]] = defaultdict(list)
        approvers_seen: Counter = Counter()
        owners_seen: Set[str] = set()
        fetch_files = bool(codeowners) and not only_default_rule

        def fetch(pr):
            """Approvers, changed files and the merger of one pull request."""
            author, number = pr["user"]["login"], pr["number"]
            reviews = self.client.get(
                f"repos/{self.repo}/pulls/{number}/reviews", {"per_page": 100}, 300
            ) or []  # fmt: skip
            approved_by = {
                r["user"]["login"]
                for r in reviews
                if r.get("state") == "APPROVED" and r.get("user") and r["user"]["login"] != author
            }
            approved_by = {a for a in approved_by if self._keep(a)}
            files = None
            if fetch_files:
                files = self.client.get(
                    f"repos/{self.repo}/pulls/{number}/files", {"per_page": 100}, 300
                ) or []  # fmt: skip
            merger = None
            if not approved_by:
                detail = self.client.get(f"repos/{self.repo}/pulls/{number}") or {}
                merger = (detail.get("merged_by") or {}).get("login")
            return author, number, approved_by, files, merger

        with ThreadPoolExecutor(max_workers=8) as pool:
            fetched = []
            for i, item in enumerate(pool.map(fetch, merged), 1):
                fetched.append(item)
                if i % 10 == 0:
                    self.progress(f"Pull request {i}/{len(merged)}")

        for author, number, approved_by, files, merger in fetched:
            authored[author] += 1
            for approver in approved_by:
                approvals[(approver, author)] += 1
                approvers_seen[approver] += 1

            if codeowners:
                if files is None:
                    pr_owners = owners_for("README.md", codeowners)
                else:
                    pr_owners = sorted(
                        {o for f in files for o in owners_for(f["filename"], codeowners)}
                    )
                for owner in pr_owners:
                    for login in self._expand(owner):
                        if self._keep(login) and login != author:
                            owner_reviews[(login, author)] += 1
                            owners_seen.add(login)

            if self._keep(merger):
                unreviewed_merges[merger].append(number)

        unreviewed = sum(len(n) for n in unreviewed_merges.values())
        if unreviewed and not review_required:
            why = (
                "the branch does not require reviews"
                if review_required is False
                else "whether the branch requires reviews is not visible"
            )
            message = (
                f"{unreviewed} pull request(s) were merged without an approving review; "
                f"{why}, so they are not counted as bypasses."
            )
            (self.notes if review_required is False else self.gaps).append(message)
            unreviewed_merges.clear()

        result = self._build(
            merged, authored, approvals, owner_reviews, unreviewed_merges, bypassers,
            approvers_seen, owners_seen,
        )  # fmt: skip
        result.review_required = review_required
        result.gaps = self.gaps
        return result

    def _build(
        self, merged, authored, approvals, owner_reviews, unreviewed_merges, bypassers,
        approvers_seen, owners_seen,
    ) -> ScanResult:  # fmt: skip
        edges: Dict[Tuple[str, str, str], Edge] = {}

        def add(source, target, kind, weight, origin, evidence):
            edge = edges.setdefault((source, target, kind), Edge(weight=0.0))
            edge.weight = max(edge.weight, round(min(1.0, weight), 2))
            edge.sources.add(origin)
            edge.evidence.append(evidence)

        for (approver, author), count in sorted(approvals.items()):
            add(approver, author, "approval", count / authored[author], "pr-reviews",
                f"approved {count} of {authored[author]} merged PRs by {author}")  # fmt: skip
        for (owner, author), count in sorted(owner_reviews.items()):
            add(owner, author, "approval", count / authored[author], "codeowners",
                f"code owner of files in {count} of {authored[author]} merged PRs by {author}")  # fmt: skip

        approvers = set(approvers_seen) | owners_seen
        for merger, numbers in sorted(unreviewed_merges.items()):
            shown = ", ".join(f"#{n}" for n in numbers[:5]) + (" ..." if len(numbers) > 5 else "")
            for approver in sorted(approvers - {merger}):
                add(merger, approver, "bypass", 1.0, "merge-history",
                    f"merged {len(numbers)} PR(s) without an approving review ({shown})")  # fmt: skip
        for actor in sorted(bypassers):
            for approver in sorted(approvers - {actor}):
                add(actor, approver, "bypass", 1.0, "branch-rules",
                    "can bypass the branch rules that require reviews")  # fmt: skip

        logins = set(authored) | approvers | set(unreviewed_merges) | set(bypassers)
        total_approvals = sum(approvers_seen.values()) or 1
        people = []
        for login in logins:
            crit, reasons = 0.3, []
            if login in owners_seen:
                crit += 0.3
                reasons.append("code owner")
            if login in bypassers or login in unreviewed_merges:
                crit += 0.2
                reasons.append("can bypass review")
            share = approvers_seen[login] / total_approvals
            if share:
                crit += 0.2 * share
                reasons.append(f"gave {share:.0%} of approvals")
            if authored[login]:
                reasons.append(f"authored {authored[login]} merged PRs")
            people.append(
                {
                    "id": login,
                    "name": login,
                    "role": ", ".join(reasons[:2]) or "contributor",
                    "criticality": round(min(1.0, crit), 2),
                    "source": "github",
                    "evidence": "; ".join(reasons),
                }
            )
        people.sort(key=lambda p: (-p["criticality"], p["id"]))

        dependencies: List[Dict[str, Any]] = [
            {
                "from": source,
                "to": target,
                "type": kind,
                "weight": edge.weight,
                "source": "+".join(sorted(edge.sources)),
                "evidence": "; ".join(edge.evidence),
                "confirmed": False,
            }
            for (source, target, kind), edge in sorted(edges.items())
            if source != target
        ]
        # The model keeps one dependency per (from, to); a bypass outranks an approval.
        best: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for dep in dependencies:
            key = (dep["from"], dep["to"])
            if key not in best or dep["type"] == "bypass":
                if key in best:
                    dep["evidence"] = f"{dep['evidence']}; also {best[key]['evidence']}"
                best[key] = dep
        return ScanResult(
            repo=self.repo,
            branch=self.branch or "",
            pull_requests=len(merged),
            people=people,
            dependencies=list(best.values()),
            notes=self.notes,
            api_calls=self.client.calls,
        )


# Draft file


def merge_with_existing(result: ScanResult, existing: Optional[Dict[str, Any]]) -> List[str]:
    """
    Keep human decisions from a previous draft.

    Criticality, names and roles of known people are kept; ``confirmed: true`` is carried
    over for dependencies that are still found; confirmed or hand-written dependencies that
    the scan no longer finds are kept. Returns notes about what was kept.
    """
    if not existing:
        return []
    notes = []
    old_people = {p["id"]: p for p in existing.get("people", [])}
    for person in result.people:
        old = old_people.get(person["id"])
        if old:
            for attr in ("criticality", "name", "role"):
                if attr in old:
                    person[attr] = old[attr]
    known = {p["id"] for p in result.people}
    for pid, old in old_people.items():
        if pid not in known:
            result.people.append(old)
            known.add(pid)

    old_deps = {(d["from"], d["to"]): d for d in existing.get("dependencies", [])}
    new_keys = set()
    carried = 0
    for dep in result.dependencies:
        key = (dep["from"], dep["to"])
        new_keys.add(key)
        old = old_deps.get(key)
        if old and old.get("confirmed") and old.get("type") == dep["type"]:
            dep["confirmed"] = True
            carried += 1
    kept = 0
    for key, old in old_deps.items():
        if key not in new_keys and (old.get("confirmed") or "source" not in old):
            result.dependencies.append(old)
            kept += 1
    if carried:
        notes.append(f"Kept confirmation of {carried} dependencies found again.")
    if kept:
        notes.append(f"Kept {kept} confirmed or hand-written dependencies the scan did not find.")
    return notes


def draft_yaml(result: ScanResult, notes: Iterable[str] = ()) -> str:
    import yaml

    header = [
        f"# Draft generated by `hrg scan github {result.repo}` on {date.today().isoformat()}",
        f"# from {result.pull_requests} merged pull requests into {result.branch}.",
        "#",
        "# Review before relying on the score: GitHub permissions and history do not prove",
        "# real authority. For every dependency check `evidence`, fix `type` or `weight`, and",
        "# set `confirmed: true`. Adjust `criticality` (0-1) to how much the work of each",
        "# person matters. Re-running the scan keeps your confirmations and criticality.",
        "# `coverage.gaps` lists what the token could not see: a missing bypass there is not",
        "# evidence that none exists.",
        "#",
        *[f"# Note: {n}" for n in [*result.notes, *notes]],
        "",
    ]
    body = yaml.safe_dump(
        {
            "coverage": result.coverage(),
            "people": result.people,
            "dependencies": result.dependencies,
        },
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    return "\n".join(header) + body
