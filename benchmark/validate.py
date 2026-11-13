"""
Predictive check of hrg-3: does a single releaser before T0 predict a release stall after it?

Protocol: docs/validation-hrg3.md (fixed before the data was collected).

Usage:
    python benchmark/validate.py [--limit 1000] [--output-dir benchmark/validation]

Needs a GitHub token (GITHUB_TOKEN, GH_TOKEN or `gh auth login`). API responses are cached
in benchmark/.cache/, so an interrupted run resumes where it stopped.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from human_risk_graph import __version__
from human_risk_graph.github_scan import GitHubClient, GitHubError, _is_bot, default_token

HERE = Path(__file__).resolve().parent
T0 = datetime(2024, 11, 1, tzinfo=timezone.utc)
W_START = T0 - timedelta(days=730)
O_END = T0 + timedelta(days=365)
COMMITS_SINCE = T0 - timedelta(days=365)
LONG_GAP_DAYS = 180
MIN_RELEASES = 3
LAST_RELEASES = 30  # as `hrg scan github` reads them
MAX_COMMITS = 500
MAX_RELEASE_PAGES = 30
FRAME_URL = (
    "https://raw.githubusercontent.com/hugovk/top-pypi-packages/"
    "9a7168eafc044ad06176f08dfb91405ca6f155b8/top-pypi-packages-30-days.min.json"
)
URL_KEYS = ("source", "source code", "repository", "code", "github", "homepage")
GITHUB_URL = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)", re.I)
NOT_REPOS = {"sponsors", "orgs", "apps", "features", "marketplace", "topics", "collections"}


# Pure functions (unit-tested)


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


def releases_before(releases: Iterable[Dict[str, Any]], t0: datetime = T0) -> List[Dict]:
    """Non-draft releases published before t0, newest first."""
    out = [r for r in releases if not r.get("draft") and r["published"] and r["published"] < t0]
    return sorted(out, key=lambda r: r["published"], reverse=True)


def release_margin(releases: Iterable[Dict[str, Any]], t0: datetime = T0) -> Tuple[int, int, int]:
    """
    (human release authors, releases by people, releases by bots) among the last 30 releases
    published in the predictor window before t0.
    """
    start = t0 - (T0 - W_START)
    last = [r for r in releases_before(releases, t0) if r["published"] >= start][:LAST_RELEASES]
    by_people = [r["author"] for r in last if r["author"] and not _is_bot(r["author"])]
    bots = sum(1 for r in last if r["author"] and _is_bot(r["author"]))
    return len(set(by_people)), len(by_people), bots


def truck_factor(authors: Iterable[Optional[str]]) -> Optional[int]:
    """Fewest people who authored more than half of the human-authored commits."""
    counts = Counter(a for a in authors if a and not _is_bot(a))
    total = sum(counts.values())
    if not total:
        return None
    covered = 0
    for k, (_, n) in enumerate(counts.most_common(), 1):
        covered += n
        if covered * 2 > total:
            return k
    return len(counts)  # pragma: no cover - unreachable, the loop always crosses half


def outcomes(release_times: Iterable[datetime]) -> Dict[str, Any]:
    """Stall (no release in O) and long gap (first release after T0 later than 180 days)."""
    after = sorted(t for t in release_times if T0 <= t < O_END)
    first = after[0] if after else None
    return {
        "first_release_after_t0": first.date().isoformat() if first else "",
        "stall": first is None,
        "long_gap": first is None or (first - T0).days > LONG_GAP_DAYS,
    }


def risk_ratio(a: int, n1: int, c: int, n0: int) -> Dict[str, Optional[float]]:
    """
    Risk ratio of exposed (a events of n1) vs unexposed (c of n0), 95% CI by the Katz log
    method; 0.5 is added to every cell when one is zero (Haldane-Anscombe).
    """
    if not n1 or not n0:
        return {"rr": None, "low": None, "high": None}
    b, d = n1 - a, n0 - c
    if 0 in (a, b, c, d):
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    m1, m0 = a + b, c + d
    rr = (a / m1) / (c / m0)
    se = math.sqrt(1 / a - 1 / m1 + 1 / c - 1 / m0)
    return {"rr": rr, "low": rr * math.exp(-1.96 * se), "high": rr * math.exp(1.96 * se)}


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test for the 2x2 table [[a, b], [c, d]]."""
    r1, r2, c1 = a + b, c + d, a + c
    n = r1 + r2

    def p(x: int) -> float:
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)

    observed = p(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= observed * (1 + 1e-9)))


def mantel_haenszel(strata: Sequence[Tuple[int, int, int, int]]) -> Dict[str, Optional[float]]:
    """
    Mantel-Haenszel risk ratio over strata (a, n1, c, n0) with the Greenland-Robins variance.
    """
    num = den = var_num = 0.0
    for a, n1, c, n0 in strata:
        n = n1 + n0
        if not n1 or not n0:
            continue
        num += a * n0 / n
        den += c * n1 / n
        var_num += (n1 * n0 * (a + c) - a * c * n) / n**2
    if not num or not den:
        return {"rr": None, "low": None, "high": None}
    rr = num / den
    se = math.sqrt(var_num / (num * den))
    return {"rr": rr, "low": rr * math.exp(-1.96 * se), "high": rr * math.exp(1.96 * se)}


def terciles(values: Sequence[float]) -> List[int]:
    """Stratum 0, 1 or 2 for each value, cut at the 1/3 and 2/3 order statistics."""
    ordered = sorted(values)
    n = len(ordered)
    q1, q2 = ordered[n // 3], ordered[2 * n // 3]
    return [0 if v < q1 else 1 if v < q2 else 2 for v in values]


def compare(rows: List[Dict[str, Any]], exposed, outcome: str) -> Dict[str, Any]:
    """2x2 table, risk ratio and Fisher p for a predicate over included rows."""
    ex = [r for r in rows if exposed(r)]
    un = [r for r in rows if not exposed(r)]
    a, c = sum(r[outcome] for r in ex), sum(r[outcome] for r in un)
    return {
        "exposed": {"n": len(ex), "events": a},
        "unexposed": {"n": len(un), "events": c},
        **risk_ratio(a, len(ex), c, len(un)),
        "p": fisher_exact(a, len(ex) - a, c, len(un) - c) if ex and un else None,
    }


def analyze(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    included = [r for r in rows if r["status"] == "included"]
    single = lambda r: r["release_margin"] == 1  # noqa: E731
    out: Dict[str, Any] = {"n": len(included)}
    strata = terciles([r["releases_in_window"] for r in included]) if included else []
    for outcome in ("stall", "long_gap"):
        by_stratum = []
        for s in range(3):
            group = [r for r, k in zip(included, strata) if k == s]
            ex = [r for r in group if single(r)]
            un = [r for r in group if not single(r)]
            by_stratum.append(
                (sum(r[outcome] for r in ex), len(ex), sum(r[outcome] for r in un), len(un))
            )
        with_tf = [r for r in included if r["truck_factor"] is not None]
        out[outcome] = {
            "h1_single_releaser": compare(included, single, outcome),
            "h2_stratified_by_release_count": {
                **mantel_haenszel(by_stratum),
                "strata": [dict(zip(("a", "n1", "c", "n0"), s)) for s in by_stratum],
            },
            "baseline_truck_factor_1": compare(with_tf, lambda r: r["truck_factor"] == 1, outcome),
            "single_releaser_when_truck_factor_2_plus": compare(
                [r for r in with_tf if r["truck_factor"] >= 2], single, outcome
            ),
        }
    return out


# Data collection


class StrictClient(GitHubClient):
    """Like GitHubClient, but 403 and 429 raise: a rate limit must not look like missing data."""

    def _request(self, url: str):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "human-risk-graph-validation",
                "Authorization": f"Bearer {self.token}",
            },
        )
        self.calls += 1
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8")), response.headers.get("Link")
        except urllib.error.HTTPError as e:
            if e.code in (404, 409, 410, 451):  # missing, empty, gone, blocked
                return None, None
            if e.code in (403, 429):
                raise GitHubError(f"rate limit ({e.code}) for {url}") from e
            raise GitHubError(f"GitHub API error {e.code} for {url}") from e


class Cache:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, fetch):
        path = self.root / (hashlib.sha256(key.encode()).hexdigest()[:32] + ".json")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        value = fetch()
        path.write_text(json.dumps(value), encoding="utf-8")
        return value


def _http_json(url: str) -> Optional[Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "human-risk-graph-validation"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def pypi_summary(package: str) -> Optional[Dict[str, Any]]:
    data = _http_json(f"https://pypi.org/pypi/{urllib.parse.quote(package)}/json")
    if not data:
        return None
    info = data.get("info") or {}
    return {
        "info": {"project_urls": info.get("project_urls"), "home_page": info.get("home_page")},
        "times": sorted(
            f["upload_time_iso_8601"]
            for files in (data.get("releases") or {}).values()
            for f in files
            if f.get("upload_time_iso_8601")
        ),
    }


def collect_repo(client: GitHubClient, cache: Cache, repo: str) -> Dict[str, Any]:
    meta = cache.get(f"gh:repo:{repo}", lambda: client.get(f"repos/{repo}"))
    if not meta:
        return {"status": "excluded: repository not reachable"}

    def fetch_releases():
        items: List[Dict[str, Any]] = []
        for page in range(1, MAX_RELEASE_PAGES + 1):
            batch = client.get(f"repos/{repo}/releases", {"per_page": 100, "page": page})
            if not batch:
                break
            items += [
                {
                    "author": (r.get("author") or {}).get("login"),
                    "draft": bool(r.get("draft")),
                    "published": r.get("published_at") or r.get("created_at"),
                }
                for r in batch
            ]
            oldest = min(
                (parse_time(i["published"]) for i in items if i["published"]), default=None
            )
            if len(batch) < 100 or (oldest and oldest < W_START):
                break
        return items

    raw = cache.get(f"gh:releases:{repo}", fetch_releases)
    releases = [{**r, "published": parse_time(r["published"])} for r in raw]
    in_window = [r for r in releases_before(releases) if r["published"] >= W_START]
    humans, by_people, bots = release_margin(releases)

    commits = cache.get(
        f"gh:commits:{repo}",
        lambda: [
            (c.get("author") or {}).get("login")
            for c in client.get(
                f"repos/{repo}/commits",
                {"since": COMMITS_SINCE.isoformat(), "until": T0.isoformat(), "per_page": 100},
                MAX_COMMITS,
            )
            or []
        ],
    )
    row = {
        "repo": meta["full_name"],
        "releases_in_window": len(in_window),
        "release_margin": humans,
        "releases_by_people": by_people,
        "bot_releases": bots,
        "commits_considered": len(commits),
        "truck_factor": truck_factor(commits),
        "github_release_times": [
            r["published"] for r in releases if not r["draft"] and r["published"]
        ],
    }
    if len(in_window) < MIN_RELEASES:
        row["status"] = f"excluded: fewer than {MIN_RELEASES} releases in the window"
    elif not humans:
        row["status"] = "excluded: no release by a person"
    elif bots > by_people:
        row["status"] = "excluded: releases mainly published by automation"
    else:
        row["status"] = "included"
    return row


def collect(limit: int, client: GitHubClient, cache: Cache, log) -> List[Dict[str, Any]]:
    frame = cache.get(f"frame:{FRAME_URL}", lambda: _http_json(FRAME_URL))["rows"][:limit]
    rows: List[Dict[str, Any]] = []
    seen = set()
    for rank, entry in enumerate(frame, 1):
        package = entry["project"]
        pypi = cache.get(f"pypi:{package}", lambda: pypi_summary(package))
        base = {"rank": rank, "package": package}
        repo = github_repo(pypi["info"]) if pypi else None
        if not repo:
            rows.append({**base, "status": "excluded: no GitHub repository"})
            continue
        for attempt in range(5):
            try:
                row = collect_repo(client, cache, repo)
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
        pypi_times = [parse_time(t) for t in pypi["times"]]
        times = pypi_times + row.pop("github_release_times", [])
        rows.append({**base, **row, **outcomes(t for t in times if t)})
        if rank % 50 == 0:
            log(f"{rank}/{len(frame)} packages, {client.calls} GitHub calls")
    return rows


COLUMNS = (
    "rank package repo status releases_in_window release_margin releases_by_people "
    "bot_releases commits_considered truck_factor first_release_after_t0 stall long_gap"
).split()


def write(rows: List[Dict[str, Any]], results: Dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "data.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--limit", type=int, default=1000, help="packages from the frame")
    parser.add_argument("--output-dir", type=Path, default=HERE / "validation")
    parser.add_argument("--cache-dir", type=Path, default=HERE / ".cache")
    args = parser.parse_args(argv)

    token = default_token()
    if not token:
        print("A GitHub token is required.", file=sys.stderr)
        return 2
    client = StrictClient(token)
    rows = collect(args.limit, client, Cache(args.cache_dir), lambda m: print(m, file=sys.stderr))
    results = {
        "protocol": "docs/validation-hrg3.md",
        "hrg_version": __version__,
        "t0": T0.date().isoformat(),
        "frame": FRAME_URL,
        "packages": len(rows),
        "exclusions": dict(Counter(r["status"] for r in rows if r["status"] != "included")),
        "analyses": analyze(rows),
    }
    write(rows, results, args.output_dir)
    print(json.dumps(results["analyses"]["stall"]["h1_single_releaser"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
