"""
Build a draft organization from a GitHub repository.

Evidence used, all readable with a token that can read the repository:

- Pull request reviews: who approved whose merged pull requests (``approval``).
- CODEOWNERS: who must approve changes to the files a pull request touched (``approval``).
- Pull requests merged without an approving review from someone else, when the branch
  visibly requires reviews (``bypass`` from the person who merged to the approvers).
- Branch rules and ruleset bypass actors, when the token can see them (``bypass``).
- Deployment environments: required reviewers, self-review and admin bypass settings, and
  who created recent deployments (the ``deploy-*`` functions of model hrg-3).
- For people with authority over a function, the date they were last seen active
  (``last_active``), unless the scan runs with ``record_activity=False``.

Technical permissions and history do not prove real authority, so every dependency is
written with ``source``, ``evidence`` and ``confirmed: false`` for a person to review, and
what the token could not see is listed under ``coverage.gaps``.
"""

import base64
import json
import os
import re
import shutil

# subprocess runs only `gh auth token`, with fixed arguments and no shell.
import subprocess  # nosec B404
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from .activity import NEVER, latest

API = "https://api.github.com"
CODEOWNERS_PATHS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
ADMIN_ROLE_ID = 5  # built-in "admin" repository role in ruleset bypass actors
TRANSIENT = (500, 502, 503, 504)  # GitHub server errors worth retrying
# Environments drafted as a deploy function even without required reviewers.
PRODUCTION_LIKE = re.compile(
    r"prod|live|release|publish|pypi|npm|crates|rubygems|maven|nuget|docker|registry",
    re.IGNORECASE,
)
MAX_DEPLOYMENTS = 30  # most recent deployments read per environment
MAX_ACTIVITY_LOOKUPS = 30  # people per repository whose last commit is looked up
RECENT_DAYS = 30  # activity seen in pull requests more recent than this needs no lookup


class GitHubError(RuntimeError):
    pass


def _not_available(error: urllib.error.HTTPError, url: str, final: bool) -> bool:
    """
    Classify an HTTP error: True when optional data is not available (403, 404, 409, 422),
    False when the request is worth retrying; raises GitHubError when it is fatal.
    """
    if error.code in (403, 404, 409, 422):
        if error.code == 403 and error.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubError(
                "GitHub API rate limit reached; use a token (--token, GITHUB_TOKEN "
                "or `gh auth login`)"
            ) from error
        return True
    if error.code == 401:
        raise GitHubError("GitHub rejected the token (401)") from error
    if error.code not in TRANSIENT or final:
        raise GitHubError(f"GitHub API error {error.code} for {url}") from error
    return False


class GitHubClient:
    """Minimal REST client: GET with pagination; returns None for 403/404 on optional data.

    Server errors (5xx) and network failures are retried with exponential backoff.
    """

    def __init__(self, token: Optional[str] = None, api: str = API):
        if urllib.parse.urlsplit(api).scheme != "https":
            raise ValueError(f"GitHub API URL must use https, got {api!r}")
        self.token = token
        self.api = api.rstrip("/")
        self.calls = 0
        self.retry_delays: Tuple[float, ...] = (1, 2, 4)  # seconds before each retry
        self._lock = threading.Lock()

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "human-risk-graph",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, url: str):
        # Pagination follows Link headers: never send the token outside the API.
        if not url.startswith(self.api + "/"):
            raise GitHubError(f"Refusing to request {url}: not under {self.api}")
        request = urllib.request.Request(url, headers=self._headers())
        for delay in (*self.retry_delays, None):
            with self._lock:
                self.calls += 1
            try:
                # https only: checked in __init__ and above (bandit B310).
                with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
                    return json.loads(response.read().decode("utf-8")), response.headers.get("Link")
            except urllib.error.HTTPError as e:
                if _not_available(e, url, final=delay is None):
                    return None, None
            except (urllib.error.URLError, TimeoutError) as e:
                if delay is None:
                    reason = getattr(e, "reason", e)
                    raise GitHubError(f"Cannot reach GitHub: {reason}") from e
            time.sleep(delay or 0)
        raise AssertionError("unreachable")  # pragma: no cover

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


def default_token(api: str = API) -> Optional[str]:
    """
    GITHUB_TOKEN, GH_TOKEN, or the token of a logged-in GitHub CLI; for GitHub Enterprise
    Server (``api`` other than api.github.com), the CLI's token for that host.
    """
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    if shutil.which("gh"):
        command = ["gh", "auth", "token"]
        host = urllib.parse.urlsplit(api).hostname
        if host and api.rstrip("/") != API:
            command += ["--hostname", host]
        try:
            out = subprocess.run(  # nosec B603
                command, capture_output=True, text=True, timeout=10, check=False
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
    # Approving reviews given per person, and code owners seen, before dependencies are merged.
    approvals_given: Dict[str, int] = field(default_factory=dict)
    code_owners: List[str] = field(default_factory=list)
    # Critical functions for model hrg-3: merge, release, admin, deploy-<environment>.
    functions: List[Dict[str, Any]] = field(default_factory=list)
    # Repositories an organization scan covered; empty for a single repository.
    repositories: List[str] = field(default_factory=list)

    def coverage(self) -> Dict[str, Any]:
        coverage = {
            "source": f"github {self.repo}",
            "branch": self.branch,
            "pull_requests": self.pull_requests,
            "review_required": (
                "unknown" if self.review_required is None else self.review_required
            ),
            "gaps": self.gaps,
        }
        if self.repositories:
            coverage["repositories"] = self.repositories
        return coverage


@dataclass
class _PullRequest:
    author: str
    number: int
    approved_by: Set[str]
    files: Optional[List[Dict[str, Any]]]
    merger: Optional[str]
    merged_at: Optional[str] = None
    approved_at: Dict[str, str] = field(default_factory=dict)  # approver -> latest approval


@dataclass
class _Tally:
    authored: Counter = field(default_factory=Counter)
    approvals: Counter = field(default_factory=Counter)  # (approver, author) -> count
    owner_reviews: Counter = field(default_factory=Counter)  # (owner, author) -> count
    unreviewed_merges: Dict[str, List[int]] = field(default_factory=lambda: defaultdict(list))
    approvers_seen: Counter = field(default_factory=Counter)
    owners_seen: Set[str] = field(default_factory=set)


def _function(fid, name, criticality, requires, performers, alone, evidence) -> Dict[str, Any]:
    """A drafted function for model hrg-3, to be confirmed by a person."""
    return {
        "id": fid,
        "name": name,
        "criticality": criticality,
        "requires": requires,
        "performers": sorted(performers),
        "alone": sorted(alone),
        "source": "github",
        "evidence": "; ".join(evidence),
        "confirmed": False,
    }


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "default"


def _is_bot(login: str) -> bool:
    """GitHub Apps ("name[bot]") and machine users named like bots (prombot, k8s-ci-robot)."""
    name = login.lower()
    return name.endswith("[bot]") or name.endswith("bot") or bool(re.search(r"[-_]bot[-_]", name))


class GitHubScanner:
    def __init__(
        self,
        client: GitHubClient,
        repo: str,
        branch: Optional[str] = None,
        max_prs: int = 100,
        include_bots: bool = False,
        progress: Optional[Callable[[str], None]] = None,
        record_activity: bool = True,
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
        self._admin_cache: Optional[Set[str]] = None
        self.record_activity = record_activity
        self.seen: Dict[str, str] = {}  # login -> latest activity date seen (YYYY-MM-DD)

    # Helpers

    def _keep(self, login: Optional[str]) -> bool:
        if not login:
            return False
        return self.include_bots or not _is_bot(login)

    def _saw(self, login: Optional[str], timestamp: Optional[str]) -> None:
        """Record that ``login`` was active at ``timestamp`` (an API date-time)."""
        if login and timestamp:
            day = timestamp[:10]
            self.seen[login] = max(self.seen.get(login, day), day)

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
        rules = self.client.get(f"repos/{self.repo}/rules/branches/{self.branch}")
        actors, review_required = self._ruleset_bypass(rules or [])
        classic, review_required = self._classic_bypass(bool(rules), review_required)
        return {a for a in actors | classic if self._keep(a)}, review_required

    def _ruleset_bypass(self, rules: List[Dict[str, Any]]) -> Tuple[Set[str], Optional[bool]]:
        """Bypass actors of the rulesets that apply to the branch, and whether they need reviews."""
        actors: Set[str] = set()
        review_required: Optional[bool] = False
        ruleset_ids = set()
        for rule in rules:
            ruleset_ids.add(rule.get("ruleset_id"))
            params = rule.get("parameters") or {}
            if rule.get("type") == "pull_request" and (
                params.get("required_approving_review_count")
                or params.get("require_code_owner_review")
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
        return actors, review_required

    def _classic_bypass(
        self, has_rules: bool, review_required: Optional[bool]
    ) -> Tuple[Set[str], Optional[bool]]:
        """Bypass allowances of classic branch protection; gaps when it is not visible."""
        branch = self.client.get(f"repos/{self.repo}/branches/{self.branch}") or {}
        protection = self.client.get(f"repos/{self.repo}/branches/{self.branch}/protection")
        if protection:
            return self._protection_bypass(protection, review_required)
        if branch.get("protected") and not has_rules:
            self.gaps.append(
                f"Branch {self.branch} is protected but its protection settings are not "
                "visible (needs admin access): required reviews and bypass allowances unknown."
            )
            return set(), None
        if branch.get("protected"):
            self.gaps.append(
                f"Classic protection settings of {self.branch} are not visible (needs admin "
                "access); only rulesets were read."
            )
            return set(), review_required or None
        return set(), review_required

    def _protection_bypass(
        self, protection: Dict[str, Any], review_required: Optional[bool]
    ) -> Tuple[Set[str], Optional[bool]]:
        actors: Set[str] = set()
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
        return actors, review_required

    def _admins(self, why: str) -> Set[str]:
        if self._admin_cache is not None:
            return self._admin_cache
        admins = self.client.get(
            f"repos/{self.repo}/collaborators", {"permission": "admin", "per_page": 100}, 500
        )
        if admins is None:
            self.gaps.append(f"Repository admins are not visible ({why}; needs push access).")
            self._admin_cache = set()
        else:
            self._admin_cache = {a["login"] for a in admins if self._keep(a.get("login"))}
        return self._admin_cache

    def _releases(self) -> Counter:
        releases = self.client.get(f"repos/{self.repo}/releases", {"per_page": 30}) or []
        authors: Counter = Counter()
        for release in releases:
            login = (release.get("author") or {}).get("login")
            if login and not release.get("draft"):
                authors[login] += 1
                self._saw(login, release.get("published_at"))
        return authors

    def _functions(
        self, review_required, bypassers, unreviewed_merges, approvers_seen, owners_seen,
        releases, admins,
    ) -> List[Dict[str, Any]]:  # fmt: skip
        """Merge, release and admin functions for model hrg-3, from what the scan saw."""
        functions = []

        def add(fid, name, criticality, requires, performers, alone, evidence):
            functions.append(
                _function(fid, name, criticality, requires, performers, alone, evidence)
            )

        trusted = {p for p in set(approvers_seen) | owners_seen if not p.startswith("@")}
        solo = set(bypassers) | set(unreviewed_merges)
        requires = 1 if review_required is False else 2
        if trusted or solo:
            evidence = [f"{len(trusted)} people approved merged pull requests or own code"]
            if requires == 2:
                evidence.append(
                    "two trusted persons per change (SLSA Source Level 4)"
                    + (
                        "; whether reviews are required is not visible"
                        if review_required is None
                        else ""
                    )
                )
            else:
                evidence.append("the branch does not require reviews")
            if solo and requires > 1:
                evidence.append("can merge without a second person: " + ", ".join(sorted(solo)))
            add("merge", f"Merge to {self.branch}", 0.8, requires, trusted | solo,
                solo if requires > 1 else set(), evidence)  # fmt: skip

        humans = {login: n for login, n in releases.items() if self._keep(login)}
        automated = sum(n for login, n in releases.items() if not self._keep(login))
        total = sum(releases.values())
        if humans:
            add("release", "Publish a release", 0.9, 1, humans, set(),
                [f"published {n} of the last {total} releases: {login}"
                 for login, n in sorted(humans.items(), key=lambda kv: -kv[1])])  # fmt: skip
        if automated and not humans:
            self.gaps.append(
                f"Releases are published by automation ({automated} of {total}); who can "
                "trigger it is not visible, so no release function was drafted."
            )
        elif not releases:
            self.notes.append("No GitHub releases found; no release function was drafted.")

        if admins:
            add("admin", "Change repository settings and branch protection", 0.9, 1, admins,
                set(), ["repository admins"])  # fmt: skip
        return functions

    def _deploy_functions(
        self, admins: Set[str]
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str]]]:
        """A deploy function per protected or production-like environment, and people's roles."""
        data = self.client.get(f"repos/{self.repo}/environments", {"per_page": 100})
        if data is None:
            self.gaps.append(
                "Deployment environments are not visible; no deploy function was drafted."
            )
            return [], []
        functions, roles = [], []
        for env in sorted(data.get("environments") or [], key=lambda e: e.get("name") or ""):
            drafted = self._deploy_function(env, admins)
            if drafted:
                functions.append(drafted[0])
                roles += drafted[1]
        return functions, roles

    def _deploy_function(
        self, env: Dict[str, Any], admins: Set[str]
    ) -> Optional[Tuple[Dict[str, Any], List[Tuple[str, str]]]]:
        name = env.get("name") or ""
        rule = next(
            (r for r in env.get("protection_rules") or [] if r.get("type") == "required_reviewers"),
            None,
        )
        production = bool(PRODUCTION_LIKE.search(name))
        if rule is None and not production:
            return None
        deployers = self._deployers(name)
        roles = [(login, f"deployed to {name}") for login in deployers]
        if rule is None:
            if not deployers:
                self.notes.append(
                    f"Environment {name} has no required reviewers and no deployments by "
                    "people were seen; no deploy function was drafted."
                )
                return None
            evidence = ["no required reviewers: whoever can run the deployment deploys alone"]
            requires, performers, alone = 1, set(deployers), set()
        else:
            reviewers = self._environment_reviewers(rule)
            roles += [(login, f"approves deployments to {name}") for login in reviewers]
            self_review = not rule.get("prevent_self_review")
            admin_bypass = env.get("can_admins_bypass", True) and bool(admins)
            alone = (set(reviewers) if self_review else set()) | (admins if admin_bypass else set())
            requires, performers = 2, set(reviewers) | set(deployers) | alone
            evidence = [
                "one of the required reviewers approves each deployment: "
                + (", ".join(sorted(reviewers)) or "none visible"),
                (
                    "reviewers can approve their own deployments"
                    if self_review
                    else "reviewers cannot approve their own deployments"
                ),
            ]
            if admin_bypass:
                evidence.append("admins can bypass the environment's protection rules")
        if deployers:
            evidence.append(
                "recent deployments by "
                + ", ".join(f"{login} ({n})" for login, n in deployers.most_common())
            )
        if any(r.get("type") == "branch_policy" for r in env.get("protection_rules") or []):
            evidence.append("deployments are limited to selected branches")
        function = _function(
            f"deploy-{_slug(name)}", f"Deploy to {name}", 0.9 if production else 0.7,
            requires, performers, alone, evidence,
        )  # fmt: skip
        return function, roles

    def _environment_reviewers(self, rule: Dict[str, Any]) -> Set[str]:
        people: Set[str] = set()
        for entry in rule.get("reviewers") or []:
            reviewer = entry.get("reviewer") or {}
            if entry.get("type") == "Team" and reviewer.get("slug"):
                people |= set(self._expand(f"@{self.org}/{reviewer['slug']}"))
            elif reviewer.get("login"):
                people.add(reviewer["login"])
        return {p for p in people if self._keep(p)}

    def _deployers(self, environment: str) -> Counter:
        """People who created the recent deployments to an environment (not bots)."""
        deployments = (
            self.client.get(
                f"repos/{self.repo}/deployments",
                {"environment": environment, "per_page": MAX_DEPLOYMENTS},
            )
            or []
        )
        counts: Counter = Counter()
        for deployment in deployments:
            login = (deployment.get("creator") or {}).get("login")
            if self._keep(login):
                counts[login] += 1
                self._saw(login, deployment.get("created_at"))
        return counts

    def _activity(self, people: Set[str]) -> Dict[str, str]:
        """
        Last activity of people with authority: the latest date seen in pull requests,
        reviews, releases and deployments, or their last commit to the default branch.
        """
        recent = (date.today() - timedelta(days=RECENT_DAYS)).isoformat()
        logins = sorted(p for p in people if not p.startswith("@"))
        to_look_up = [p for p in logins if self.seen.get(p, "") < recent]
        for login in to_look_up[:MAX_ACTIVITY_LOOKUPS]:
            commits = self.client.get(
                f"repos/{self.repo}/commits",
                {"sha": self.branch, "author": login, "per_page": 1},
            )
            if commits is None:
                continue  # not visible: activity stays unknown
            commit = (commits[0].get("commit") or {}) if commits else {}
            when = (commit.get("committer") or commit.get("author") or {}).get("date")
            if when:
                self._saw(login, when)
            elif login not in self.seen:
                self.seen[login] = NEVER
        if len(to_look_up) > MAX_ACTIVITY_LOOKUPS:
            self.gaps.append(
                f"Last activity was looked up for {MAX_ACTIVITY_LOOKUPS} of "
                f"{len(to_look_up)} people; the others only from pull requests and releases."
            )
        return {p: self.seen[p] for p in logins if p in self.seen}

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
        bypassers, review_required = self._bypass_actors()
        if review_required:
            self.notes.append(f"Branch {self.branch} requires approving reviews.")
        elif review_required is False:
            self.notes.append(f"Branch {self.branch} does not require approving reviews.")

        merged = self._merged_pull_requests()
        tally = self._tally(self._fetch_pull_requests(merged, codeowners), codeowners)
        self._discount_unreviewed(tally.unreviewed_merges, review_required)

        self.progress("Reading releases and admins")
        releases = self._releases()
        admins = self._admins("they can change settings and branch protection")
        functions = self._functions(
            review_required, bypassers, tally.unreviewed_merges, tally.approvers_seen,
            tally.owners_seen, releases, admins,
        )  # fmt: skip
        self.progress("Reading deployment environments")
        deploys, deploy_roles = self._deploy_functions(admins)
        functions += deploys
        labels = [(login, f"published {n} releases") for login, n in releases.items()]
        labels += [(login, "repository admin") for login in sorted(admins)] + deploy_roles
        roles: Dict[str, str] = {}
        for login, label in labels:
            if self._keep(login):
                roles[login] = ", ".join(filter(None, [roles.get(login), label]))

        activity: Dict[str, str] = {}
        if self.record_activity:
            self.progress("Looking up when people with authority were last active")
            activity = self._activity({p for f in functions for p in f["performers"]})
        result = self._build(merged, tally, bypassers, roles, activity)
        result.review_required = review_required
        result.gaps = self.gaps
        result.functions = functions
        return result

    def _merged_pull_requests(self) -> List[Dict[str, Any]]:
        """The most recent merged pull requests into the branch, by people (not bots)."""
        self.progress(f"Reading up to {self.max_prs} merged pull requests")
        pulls = self.client.get(
            f"repos/{self.repo}/pulls",
            {"state": "closed", "base": self.branch, "sort": "updated", "direction": "desc",
             "per_page": 100},
            self.max_prs * 2,
        ) or []  # fmt: skip
        return [
            p
            for p in pulls
            if p.get("merged_at") and self._keep((p.get("user") or {}).get("login"))
        ][: self.max_prs]

    def _fetch_pull_requests(self, merged, codeowners) -> List[_PullRequest]:
        """Approvers, changed files and merger of each pull request, read in parallel."""
        only_default_rule = all(pattern in ("*", "/*", "**") for _, pattern, _ in codeowners)
        fetch_files = bool(codeowners) and not only_default_rule

        def fetch(pr) -> _PullRequest:
            author, number = pr["user"]["login"], pr["number"]
            reviews = self.client.get(
                f"repos/{self.repo}/pulls/{number}/reviews", {"per_page": 100}, 300
            ) or []  # fmt: skip
            approved_at: Dict[str, str] = {}
            for r in reviews:
                login = (r.get("user") or {}).get("login")
                if r.get("state") != "APPROVED" or not login or login == author:
                    continue
                if self._keep(login):
                    at = r.get("submitted_at") or ""
                    approved_at[login] = max(approved_at.get(login, ""), at)
            approved_by = set(approved_at)
            files = None
            if fetch_files:
                files = self.client.get(
                    f"repos/{self.repo}/pulls/{number}/files", {"per_page": 100}, 300
                ) or []  # fmt: skip
            merger = None
            if not approved_by:
                detail = self.client.get(f"repos/{self.repo}/pulls/{number}") or {}
                merger = (detail.get("merged_by") or {}).get("login")
            return _PullRequest(
                author, number, approved_by, files, merger, pr.get("merged_at"), approved_at
            )

        fetched = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            for i, item in enumerate(pool.map(fetch, merged), 1):
                fetched.append(item)
                if i % 10 == 0:
                    self.progress(f"Pull request {i}/{len(merged)}")
        return fetched

    def _tally(self, fetched: List[_PullRequest], codeowners) -> _Tally:
        """Count authorship, approvals, code-owner reviews and merges without review."""
        tally = _Tally()
        for pr in fetched:
            tally.authored[pr.author] += 1
            self._saw(pr.author, pr.merged_at)
            if pr.merger:
                self._saw(pr.merger, pr.merged_at)
            for approver, at in pr.approved_at.items():
                self._saw(approver, at)
            for approver in pr.approved_by:
                tally.approvals[(approver, pr.author)] += 1
                tally.approvers_seen[approver] += 1
            for login in self._pr_owners(pr, codeowners):
                tally.owner_reviews[(login, pr.author)] += 1
                tally.owners_seen.add(login)
            if pr.merger and self._keep(pr.merger):
                tally.unreviewed_merges[pr.merger].append(pr.number)
        return tally

    def _pr_owners(self, pr: _PullRequest, codeowners) -> List[str]:
        """Code owners of the files a pull request changed, other than its author."""
        if not codeowners:
            return []
        if pr.files is None:
            owners = owners_for("README.md", codeowners)
        else:
            owners = sorted({o for f in pr.files for o in owners_for(f["filename"], codeowners)})
        return [
            login
            for owner in owners
            for login in self._expand(owner)
            if self._keep(login) and login != pr.author
        ]

    def _discount_unreviewed(
        self, unreviewed_merges: Dict[str, List[int]], review_required: Optional[bool]
    ) -> None:
        """Merges without review are bypasses only when the branch visibly requires reviews."""
        unreviewed = sum(len(n) for n in unreviewed_merges.values())
        if not unreviewed or review_required:
            return
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

    def _build(self, merged, tally: _Tally, bypassers, roles=None, activity=None) -> ScanResult:
        roles = roles or {}
        activity = activity or {}
        edges = _edges(tally, bypassers)
        approvers = set(tally.approvers_seen) | tally.owners_seen
        logins = (
            set(tally.authored)
            | approvers
            | set(tally.unreviewed_merges)
            | set(bypassers)
            | set(roles)
        )
        total_approvals = sum(tally.approvers_seen.values()) or 1
        people = [
            _person(login, tally, bypassers, roles, total_approvals, activity.get(login))
            for login in logins
        ]
        people.sort(key=lambda p: (-p["criticality"], p["id"]))
        return ScanResult(
            repo=self.repo,
            branch=self.branch or "",
            pull_requests=len(merged),
            people=people,
            dependencies=_strongest_dependencies(edges),
            notes=self.notes,
            api_calls=self.client.calls,
            approvals_given=dict(tally.approvers_seen),
            code_owners=sorted(tally.owners_seen),
        )


def _edges(tally: _Tally, bypassers) -> Dict[Tuple[str, str, str], Edge]:
    """Evidence per (from, to, type): approvals, code ownership and bypasses."""
    edges: Dict[Tuple[str, str, str], Edge] = {}
    authored = tally.authored

    def add(source, target, kind, weight, origin, evidence):
        edge = edges.setdefault((source, target, kind), Edge(weight=0.0))
        edge.weight = max(edge.weight, round(min(1.0, weight), 2))
        edge.sources.add(origin)
        edge.evidence.append(evidence)

    for (approver, author), count in sorted(tally.approvals.items()):
        add(approver, author, "approval", count / authored[author], "pr-reviews",
            f"approved {count} of {authored[author]} merged PRs by {author}")  # fmt: skip
    for (owner, author), count in sorted(tally.owner_reviews.items()):
        add(owner, author, "approval", count / authored[author], "codeowners",
            f"code owner of files in {count} of {authored[author]} merged PRs by {author}")  # fmt: skip

    approvers = set(tally.approvers_seen) | tally.owners_seen
    for merger, numbers in sorted(tally.unreviewed_merges.items()):
        shown = ", ".join(f"#{n}" for n in numbers[:5]) + (" ..." if len(numbers) > 5 else "")
        for approver in sorted(approvers - {merger}):
            add(merger, approver, "bypass", 1.0, "merge-history",
                f"merged {len(numbers)} PR(s) without an approving review ({shown})")  # fmt: skip
    for actor in sorted(bypassers):
        for approver in sorted(approvers - {actor}):
            add(actor, approver, "bypass", 1.0, "branch-rules",
                "can bypass the branch rules that require reviews")  # fmt: skip
    return edges


def _person(
    login: str, tally: _Tally, bypassers, roles, total_approvals: int, last_active=None
) -> Dict[str, Any]:
    """A person of the draft, with a criticality estimated from what the scan saw."""
    crit, reasons = 0.3, []
    if login in tally.owners_seen:
        crit += 0.3
        reasons.append("code owner")
    if login in bypassers or login in tally.unreviewed_merges:
        crit += 0.2
        reasons.append("can bypass review")
    if login in roles:
        crit += 0.2
        reasons.append(roles[login])
    share = tally.approvers_seen[login] / total_approvals
    if share:
        crit += 0.2 * share
        reasons.append(f"gave {share:.0%} of approvals")
    if tally.authored[login]:
        reasons.append(f"authored {tally.authored[login]} merged PRs")
    person = {
        "id": login,
        "name": login,
        "role": ", ".join(reasons[:2]) or "contributor",
        "criticality": round(min(1.0, crit), 2),
    }
    if last_active:
        person["last_active"] = last_active
    return {**person, "source": "github", "evidence": "; ".join(reasons)}


def _strongest_dependencies(edges: Dict[Tuple[str, str, str], Edge]) -> List[Dict[str, Any]]:
    """One dependency per (from, to), as the model keeps; a bypass outranks an approval."""
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for (source, target, kind), edge in sorted(edges.items()):
        if source == target:
            continue
        dep = {
            "from": source,
            "to": target,
            "type": kind,
            "weight": edge.weight,
            "source": "+".join(sorted(edge.sources)),
            "evidence": "; ".join(edge.evidence),
            "confirmed": False,
        }
        key = (source, target)
        if key not in best or kind == "bypass":
            if key in best:
                dep["evidence"] = f"{dep['evidence']}; also {best[key]['evidence']}"
            best[key] = dep
    return list(best.values())


# Organization

TYPE_RANK = {"bypass": 2, "approval": 1}  # one dependency per (from, to): the strongest wins
EVIDENCE_LIMIT = 5


def list_repositories(
    client: GitHubClient, org: str, include_archived: bool = False, include_forks: bool = False
) -> Tuple[List[str], Counter]:
    """Repositories of an organization (or user), most recently pushed first, and skip counts."""
    repos = client.get(f"orgs/{org}/repos", {"type": "all", "per_page": 100}, 5000)
    if repos is None:
        repos = client.get(f"users/{org}/repos", {"type": "owner", "per_page": 100}, 5000)
    if repos is None:
        raise GitHubError(f"Organization or user {org} not found or not visible to this token")
    skipped: Counter = Counter()
    kept = []
    for repo in repos:
        if repo.get("archived") and not include_archived:
            skipped["archived"] += 1
        elif repo.get("fork") and not include_forks:
            skipped["forks"] += 1
        elif repo.get("disabled"):
            skipped["disabled"] += 1
        else:
            kept.append(repo)
    kept.sort(key=lambda r: (r.get("pushed_at") or "", r["full_name"]), reverse=True)
    return [r["full_name"] for r in kept], skipped


def _joined(items: List[str]) -> str:
    shown = "; ".join(items[:EVIDENCE_LIMIT])
    more = len(items) - EVIDENCE_LIMIT
    return shown + (f"; and {more} more" if more > 0 else "")


def _merged_people(results: List[ScanResult]) -> Dict[str, Dict[str, Any]]:
    """Everyone once: the highest criticality, the latest activity, evidence per repository."""
    people: Dict[str, Dict[str, Any]] = {}
    evidence: Dict[str, List[str]] = defaultdict(list)
    activity: Dict[str, List[Any]] = defaultdict(list)
    for result in results:
        short = result.repo.split("/")[-1]
        for person in result.people:
            known = people.get(person["id"])
            if known is None or person["criticality"] > known["criticality"]:
                people[person["id"]] = dict(person)
            activity[person["id"]].append(person.get("last_active"))
            if person.get("evidence"):
                evidence[person["id"]].append(f"{short}: {person['evidence']}")
    for pid, person in people.items():
        last_active = latest(activity[pid])
        if last_active:
            person["last_active"] = last_active
        person["evidence"] = _joined(evidence[pid])
        if len(evidence[pid]) > 1:
            person["role"] = f"{person['role']} (in {len(evidence[pid])} repositories)"
    return people


def merge_scans(scope: str, results: List[ScanResult]) -> ScanResult:
    """
    One organization from the scans of several repositories.

    People appear once, with the highest criticality any repository gave them. Dependencies
    between the same two people are merged: a bypass anywhere outranks approvals, and the
    weight is the highest seen. Functions stay per repository (``REPO/merge``), because who
    can merge or release differs between repositories.
    """
    deps: Dict[Tuple[str, str], List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
    functions: List[Dict[str, Any]] = []
    gaps: List[str] = []
    approvals: Counter = Counter()
    owners: Set[str] = set()
    for result in results:
        short = result.repo.split("/")[-1]
        for dep in result.dependencies:
            deps[(dep["from"], dep["to"])].append((short, dep))
        for f in result.functions:
            functions.append({**f, "id": f"{short}/{f['id']}", "name": f"{f['name']} ({short})"})
        gaps += [f"{short}: {gap}" for gap in result.gaps]
        approvals.update(result.approvals_given)
        owners.update(result.code_owners)
    people = _merged_people(results)

    dependencies = []
    for (source, target), found in sorted(deps.items()):
        kind = max((d["type"] for _, d in found), key=lambda t: TYPE_RANK.get(t, 0))
        dependencies.append(
            {
                "from": source,
                "to": target,
                "type": kind,
                "weight": max(d.get("weight", 0.5) for _, d in found if d["type"] == kind),
                "source": "+".join(
                    sorted({s for _, d in found for s in str(d.get("source", "")).split("+") if s})
                ),
                "evidence": _joined([f"{short}: {d.get('evidence', '')}" for short, d in found]),
                "confirmed": False,
            }
        )

    required = {r.review_required for r in results}
    return ScanResult(
        repo=scope,
        branch="default branch of each repository",
        pull_requests=sum(r.pull_requests for r in results),
        people=sorted(people.values(), key=lambda p: (-p["criticality"], p["id"])),
        dependencies=dependencies,
        notes=[],
        api_calls=max((r.api_calls for r in results), default=0),
        review_required=required.pop() if len(required) == 1 else None,
        gaps=gaps,
        approvals_given=dict(approvals),
        code_owners=sorted(owners),
        functions=functions,
        repositories=[r.repo for r in results],
    )


def scan_organization(
    client: GitHubClient,
    org: str,
    max_repos: int = 30,
    max_prs: int = 30,
    include_bots: bool = False,
    include_archived: bool = False,
    include_forks: bool = False,
    progress: Optional[Callable[[str], None]] = None,
    record_activity: bool = True,
) -> ScanResult:
    """Scan the most recently pushed repositories of an organization and merge the results."""
    if not re.fullmatch(r"[\w.-]+", org):
        raise ValueError(f"expected an organization or user name, got {org!r}")
    report: Callable[[str], None] = progress or (lambda message: None)

    def prefixed(prefix: str) -> Callable[[str], None]:
        return lambda message: report(prefix + message)

    report(f"Listing repositories of {org}")
    names, skipped = list_repositories(client, org, include_archived, include_forks)
    selected = names[:max_repos]
    results: List[ScanResult] = []
    failed: List[str] = []
    for i, repo in enumerate(selected, 1):
        scanner = GitHubScanner(
            client,
            repo,
            max_prs=max_prs,
            include_bots=include_bots,
            progress=prefixed(f"{i}/{len(selected)} {repo}: "),
            record_activity=record_activity,
        )
        try:
            results.append(scanner.scan())
        except GitHubError as e:
            if "rate limit" in str(e):
                raise
            failed.append(f"{repo}: {e}")
    if not results:
        raise GitHubError(
            f"No repository of {org} could be scanned"
            + (f" ({failed[0]})" if failed else " (none found)")
        )

    merged = merge_scans(org, results)
    note = (
        f"Scanned {len(results)} of {len(names)} repositories of {org}, most recently pushed first"
    )
    if skipped:
        note += "; skipped " + ", ".join(f"{n} {kind}" for kind, n in sorted(skipped.items()))
    merged.notes.append(note + ".")
    if len(names) > len(selected):
        merged.notes.append(
            f"{len(names) - len(selected)} less recently pushed repositories were not scanned "
            "(raise --max-repos to include them)."
        )
    merged.gaps += [f"Could not scan {f}" for f in failed]
    merged.api_calls = client.calls
    return merged


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
    _keep_people(result, existing.get("people", []))
    notes = _keep_dependencies(result, existing.get("dependencies", []))
    return notes + _keep_functions(result, existing.get("functions") or [])


def _keep_people(result: ScanResult, old_people: List[Dict[str, Any]]) -> None:
    old_by_id = {p["id"]: p for p in old_people}
    for person in result.people:
        old = old_by_id.get(person["id"], {})
        person.update({attr: old[attr] for attr in ("criticality", "name", "role") if attr in old})
        last_active = latest([person.get("last_active"), old.get("last_active")])
        if last_active:
            person["last_active"] = last_active
    known = {p["id"] for p in result.people}
    for pid, old in old_by_id.items():
        if pid not in known:
            result.people.append(old)
            known.add(pid)


def _keep_dependencies(result: ScanResult, old_dependencies: List[Dict[str, Any]]) -> List[str]:
    old_deps = {(d["from"], d["to"]): d for d in old_dependencies}
    new_keys = set()
    carried = 0
    for dep in result.dependencies:
        key = (dep["from"], dep["to"])
        new_keys.add(key)
        old = old_deps.get(key)
        if old and old.get("confirmed") and old.get("type") == dep["type"]:
            dep["confirmed"] = True
            carried += 1
    kept = [
        old
        for key, old in old_deps.items()
        if key not in new_keys and (old.get("confirmed") or "source" not in old)
    ]
    result.dependencies.extend(kept)
    notes = []
    if carried:
        notes.append(f"Kept confirmation of {carried} dependencies found again.")
    if kept:
        notes.append(
            f"Kept {len(kept)} confirmed or hand-written dependencies the scan did not find."
        )
    return notes


def _keep_functions(result: ScanResult, old_functions: List[Dict[str, Any]]) -> List[str]:
    old_by_id = {f["id"]: f for f in old_functions}
    scanned = {f["id"] for f in result.functions}
    for f in result.functions:
        old = old_by_id.get(f["id"], {})
        keep = ("name", "criticality", "requires", "separation", "confirmed")
        f.update({attr: old[attr] for attr in keep if attr in old})
    own = [f for fid, f in old_by_id.items() if fid not in scanned]
    result.functions.extend(own)
    return [f"Kept {len(own)} functions the scan does not draft."] if own else []


def draft_yaml(result: ScanResult, notes: Iterable[str] = ()) -> str:
    import yaml

    command = (
        f"hrg scan github --org {result.repo}"
        if result.repositories
        else f"hrg scan github {result.repo}"
    )
    where = f"{len(result.repositories)} repositories" if result.repositories else result.branch
    header = [
        f"# Draft generated by `{command}` on {date.today().isoformat()}",
        f"# from {result.pull_requests} merged pull requests into {where}.",
        "#",
        "# Review before relying on the score: GitHub permissions and history do not prove",
        "# real authority. For every dependency check `evidence`, fix `type` or `weight`, and",
        "# set `confirmed: true`. Adjust `criticality` (0-1) to how much the work of each",
        "# person matters. Re-running the scan keeps your confirmations and criticality.",
        "# `coverage.gaps` lists what the token could not see: a missing bypass there is not",
        "# evidence that none exists. `functions` are for model hrg-3 (experimental):",
        "#   hrg analyze FILE --model hrg-3",
        "#",
        *[f"# Note: {n}" for n in [*result.notes, *notes]],
        "",
    ]
    document = {
        "coverage": result.coverage(),
        "people": result.people,
        "dependencies": result.dependencies,
    }
    if result.functions:
        document["functions"] = result.functions
    body = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
    return "\n".join(header) + body
