"""Tests for benchmark/two_person.py: definitions of the measures and the collection logic."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "benchmark_two_person", Path(__file__).resolve().parent.parent / "benchmark" / "two_person.py"
)
tp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tp)

T0 = datetime(2026, 12, 1, tzinfo=timezone.utc)


def _iso(days_before: int) -> str:
    return (T0 - timedelta(days=days_before)).isoformat().replace("+00:00", "Z")


def _env(name, users=(), teams=0, self_review=True, admin_bypass=True, rule=True):
    reviewers = [{"type": "User", "reviewer": {"login": u}} for u in users]
    reviewers += [{"type": "Team", "reviewer": {"slug": f"t{i}"}} for i in range(teams)]
    rules = (
        [{"type": "required_reviewers", "prevent_self_review": not self_review,
          "reviewers": reviewers}]
        if rule
        else []
    )  # fmt: skip
    return {"name": name, "protection_rules": rules, "can_admins_bypass": admin_bypass}


# Definitions


@pytest.mark.parametrize(
    "name, expected",
    [("pypi", True), ("Production", True), ("release", True), ("github-pages", False),
     ("copilot", False), ("docs", False)],
)  # fmt: skip
def test_publishing_environment_names(name, expected):
    assert tp.is_publishing(name) is expected


def test_environment_gate():
    gate = tp.environment_gate(_env("pypi", ["a", "release-bot"], teams=1))
    assert gate["gated"] and not gate["two_person"]
    assert gate["user_reviewers"] == ["a"] and gate["team_reviewers"] == 1
    strict = tp.environment_gate(_env("pypi", ["a"], self_review=False, admin_bypass=False))
    assert strict["two_person"]
    # Both conditions are needed: self-review or admin bypass alone breaks the rule.
    assert not tp.environment_gate(_env("pypi", ["a"], self_review=False))["two_person"]
    assert not tp.environment_gate(_env("pypi", ["a"], admin_bypass=False))["two_person"]
    assert not tp.environment_gate(_env("pypi", rule=False))["gated"]
    assert not tp.environment_gate(_env("pypi", []))["gated"]  # a rule with nobody in it


def test_publish_gate_classes():
    def gate(*envs, any_name=False):
        return tp.publish_gate([tp.environment_gate(e) for e in envs], any_name)

    assert gate() == "NE"
    assert gate(_env("github-pages", rule=False)) == "NE"
    assert gate(_env("pypi", rule=False)) == "G0"
    assert gate(_env("pypi", rule=False), _env("release", ["a"])) == "G1"
    two = _env("pypi", ["a"], self_review=False, admin_bypass=False)
    assert gate(_env("release", ["a"]), two) == "G2"
    # Sensitivity: a gated environment counts whatever its name.
    assert gate(_env("ship-it", ["a"])) == "NE"
    assert gate(_env("ship-it", ["a"]), any_name=True) == "G1"
    assert gate(_env("ship-it", rule=False), any_name=True) == "NE"


def _file(name, days, yanked=False):
    return {"filename": name, "upload_time_iso_8601": _iso(days), "yanked": yanked}


def test_latest_release():
    releases = {
        "1.0": [_file("a-1.0.tar.gz", 100)],
        "2.0": [_file("a-2.0.tar.gz", 10), _file("a-2.0-py3-none-any.whl", 10)],
        "2.1": [_file("a-2.1.tar.gz", 5, yanked=True)],  # yanked: ignored
        "3.0": [_file("a-3.0.tar.gz", -1)],  # after T0: ignored
    }
    assert tp.latest_release(releases, T0) == ("2.0", ["a-2.0-py3-none-any.whl", "a-2.0.tar.gz"])
    assert tp.latest_release({}, T0) == (None, [])
    many = {"9.0": [_file(f"a-9.0-{i:02}.whl", 2) for i in range(80)]}
    assert len(tp.latest_release(many, T0)[1]) == 80  # every file, no cap


# The publisher object PyPI's integrity API returned for pip 26.3 (2026-11-14), and the
# form in PEP 740's example. Both must be read the same way.
PYPI_PUBLISHER = {"environment": "pypi", "kind": "GitHub", "repository": "pypa/pip",
                  "workflow": "release.yml"}  # fmt: skip
PEP_740_PUBLISHER = {
    "kind": "GitHub", "claims": {"ref": "refs/tags/v1.0.0"}, "repository_name": "pip",
    "repository_owner": "pypa", "repository_owner_id": "1",
    "workflow_filename": "release.yml", "environment": "pypi",
}  # fmt: skip


def test_publisher_repository_both_forms():
    assert tp.publisher_repository(PYPI_PUBLISHER) == "pypa/pip"
    assert tp.publisher_repository(PEP_740_PUBLISHER) == "pypa/pip"
    assert tp.publisher_repository({"kind": "GitHub", "repository_owner": "pypa"}) == ""
    gates = [tp.environment_gate(_env("PyPI", ["a"], self_review=False, admin_bypass=False))]
    for publisher in (PYPI_PUBLISHER, PEP_740_PUBLISHER):
        assert tp.release_path([publisher, publisher], "pypa/pip", gates) == "V2"


def test_release_path():
    gates = [
        tp.environment_gate(_env("PyPI", ["a"], self_review=False, admin_bypass=False)),
        tp.environment_gate(_env("release", ["a"])),
        tp.environment_gate(_env("build", rule=False)),
    ]

    def publisher(env, repo="acme/lib", kind="GitHub"):
        return {"kind": kind, "repository": repo, "environment": env, "workflow": "r.yml"}

    def path(*publishers):
        return tp.release_path(list(publishers), "Acme/Lib", gates)

    assert path(publisher("pypi"), publisher("pypi")) == "V2"  # names are case-insensitive
    assert path(publisher("pypi"), publisher("release")) == "V1"  # the weakest file decides
    assert path(publisher("pypi"), publisher(None)) == "V0"  # no environment
    assert path(publisher("build")) == "V0"
    assert path(publisher("pypi"), None) == "P"
    assert path(None, None) == "U"
    assert path(publisher("pypi", repo="other/repo")) == "O"
    assert path(publisher("pypi", kind="GitLab")) == "O"


def test_human_publishers_window_and_bots():
    def item(login, days):
        return {"login": login, "when": T0 - timedelta(days=days)}

    releases = [item("a", 10), item("b", 400), item("dependabot[bot]", 5), item(None, 5)]
    deployments = [item("c", 364), item("a", 1), {"login": "d", "when": T0}]  # T0 excluded
    assert tp.human_publishers(releases, deployments, T0) == {"a", "c"}


def test_standing_approvals():
    def review(login, state, minute):
        return {"user": {"login": login}, "state": state,
                "submitted_at": f"2026-11-01T10:{minute:02}:00Z"}  # fmt: skip

    reviews = [
        review("a", "APPROVED", 1),
        review("a", "COMMENTED", 2),  # a comment does not withdraw an approval
        review("b", "APPROVED", 3),
        review("b", "CHANGES_REQUESTED", 4),  # withdrawn
        review("c", "DISMISSED", 5),  # a dismissed approval
        review("d", "CHANGES_REQUESTED", 6),
        review("d", "APPROVED", 7),  # approved after requesting changes
        review("author", "APPROVED", 8),  # self
        review("ci-bot", "APPROVED", 9),
        {"user": None, "state": "APPROVED"},  # deleted account
    ]
    assert tp.standing_approvals(list(reversed(reviews)), "author") == ["a", "d"]


def test_effective_approvers():
    assert tp.effective_approvers({}) is None
    assert tp.effective_approvers({"a": 10}) == 1
    assert tp.effective_approvers({"a": 5, "b": 5}) == pytest.approx(2)
    assert tp.effective_approvers({"a": 9, "b": 1}) == pytest.approx(1 / 0.82)


def test_is_dormant():
    assert tp.is_dormant(None, T0, 90)
    assert tp.is_dormant(T0 - timedelta(days=91), T0, 90)
    assert not tp.is_dormant(T0 - timedelta(days=90), T0, 90)


@pytest.mark.parametrize(
    "k, n, low, high",
    [(5, 10, 0.2366, 0.7634), (0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0), (1, 20, 0.0089, 0.2361)],
)
def test_wilson_interval(k, n, low, high):
    result = tp.wilson(k, n)
    assert result["low"] == pytest.approx(low, abs=1e-4)
    assert result["high"] == pytest.approx(high, abs=1e-4)
    assert tp.wilson(0, 0)["p"] is None


# Collection and analysis


class FakeClient:
    def __init__(self, routes):
        self.routes, self.calls, self.requested = routes, 0, []

    def get(self, path, params=None, limit=0):
        self.calls += 1
        self.requested.append((path, dict(params or {})))
        value = self.routes.get(path)
        return value(params or {}) if callable(value) else value


def _routes(**extra):
    pulls = [
        {"number": n, "merged_at": _iso(n), "user": {"login": "dev"}} for n in range(1, 13)
    ] + [{"number": 99, "merged_at": None, "user": {"login": "dev"}}]
    routes = {
        "repos/acme/lib": {
            "full_name": "acme/lib",
            "default_branch": "main",
            "archived": False,
            "owner": {"type": "Organization"},
        },
        "repos/acme/lib/environments": {
            "environments": [
                _env("pypi", ["old", "lead"], teams=1),
                _env("docs", ["x"]),
            ]
        },
        "repos/acme/lib/deployments": [
            {"creator": {"login": "lead"}, "created_at": _iso(3)},
            {"creator": {"login": "github-actions[bot]"}, "created_at": _iso(2)},
        ],
        "repos/acme/lib/releases": [
            {"author": {"login": "lead"}, "published_at": _iso(3)},
            {"author": {"login": "ghost"}, "published_at": _iso(30), "draft": True},
        ],
        "repos/acme/lib/rules/branches/main": [
            {"type": "pull_request", "parameters": {"required_approving_review_count": 1}}
        ],
        "repos/acme/lib/pulls": pulls,
        "repos/acme/lib/commits": lambda params: (
            [{"commit": {"committer": {"date": _iso(120)}}}] if params["author"] == "old" else []
        ),
    }
    for n in range(1, 13):
        routes[f"repos/acme/lib/pulls/{n}/reviews"] = [
            {"user": {"login": "lead" if n < 11 else "rev"}, "state": "APPROVED",
             "submitted_at": _iso(n)},
            {"user": {"login": "dev"}, "state": "APPROVED", "submitted_at": _iso(n)},  # self
        ]  # fmt: skip
    routes.update(extra)
    return routes


@pytest.fixture
def pypi(monkeypatch):
    """PyPI JSON and provenance: release 1.0 of acme-lib, attested through environment pypi."""

    def get_json(url, accept="application/json"):
        if url.endswith("/acme-lib/json"):
            return {"releases": {"1.0": [_file("acme_lib-1.0.tar.gz", 3)]}}
        if "/integrity/acme-lib/1.0/acme_lib-1.0.tar.gz/" in url:
            publisher = {"kind": "GitHub", "repository": "acme/lib", "environment": "pypi"}
            return {"attestation_bundles": [{"publisher": publisher}]}
        return None

    monkeypatch.setattr(tp, "_get_json", get_json)


def test_collect_repo(tmp_path, pypi):
    client = FakeClient(_routes())
    row = tp.collect_repo(client, tp.Cache(tmp_path), "acme/lib", T0, "acme-lib")
    assert row["gate"] == "G1" and row["gate_any_name"] == "G1"
    assert (row["latest_version"], row["release_files"], row["path"]) == ("1.0", 1, "V1")
    assert row["release_age_days"] == 3
    assert row["publishing_environments"] == 1  # docs is not a publishing environment
    assert row["publishers"] == 1  # lead; the bot deployment and the draft do not count
    assert row["assessable_reviewers"] == 2  # old and lead; the team is not assessable
    # old: last commit 120 days before T0 -> dormant at 90 days, not at 180.
    assert (row["dormant_90"], row["dormant_180"]) == (1, 0)
    assert row["dormant_solo_90"] and not row["dormant_solo_180"]
    assert row["review_required_visible"]
    assert (row["merged_pulls"], row["approved_pulls"]) == (12, 12)
    assert row["effective_approvers"] == pytest.approx(
        1 / ((10 / 12) ** 2 + (2 / 12) ** 2), abs=1e-3
    )
    assert row["unapproved_share"] == 0
    # Commits are looked up only for reviewers of publishing environments, in the window.
    looked_up = [p for path, p in client.requested if path == "repos/acme/lib/commits"]
    assert sorted(p["author"] for p in looked_up) == ["lead", "old"]
    assert looked_up[0]["until"] == T0.isoformat()


def test_collect_repo_exclusions(tmp_path, pypi):
    cache = tp.Cache(tmp_path)
    missing = tp.collect_repo(FakeClient({}), cache, "x/y", T0, "y")
    assert missing["status"].endswith("not reachable")
    archived = {"repos/a/b": {"full_name": "a/b", "default_branch": "main", "archived": True}}
    assert tp.collect_repo(FakeClient(archived), cache, "a/b", T0, "b")["status"] == (
        "excluded: archived"
    )


def test_unattested_release_is_not_observable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tp, "_get_json",
        lambda url, accept="application/json": (
            {"releases": {"1.0": [_file("acme_lib-1.0.tar.gz", 3)]}} if url.endswith("/json")
            else None
        ),
    )  # fmt: skip
    row = tp.collect_repo(FakeClient(_routes()), tp.Cache(tmp_path), "acme/lib", T0, "acme-lib")
    assert row["path"] == "U"


def _row(**values):
    row = {
        "status": "included", "rank": 50, "owner_type": "Organization", "gate": "NE", "path": "U",
        "gate_any_name": "NE", "publishers": 1, "assessable_reviewers": 0, "dormant_90": 0,
        "dormant_180": 0, "dormant_solo_90": False, "dormant_solo_180": False,
        "review_required_visible": False, "approved_pulls": 0, "effective_approvers": None,
        "unapproved_share": None,
    }  # fmt: skip
    row.update(values)
    return row


def test_analyze():
    rows = [
        _row(gate="G2", gate_any_name="G2", publishers=2, assessable_reviewers=1, path="V2"),
        _row(gate="G1", gate_any_name="G1", assessable_reviewers=2, dormant_90=1,
             dormant_180=1, dormant_solo_90=True, dormant_solo_180=True, rank=150,
             owner_type="User"),
        _row(gate="G1", gate_any_name="G1", assessable_reviewers=0),  # teams only
        _row(gate="G0", gate_any_name="G0", publishers=0, approved_pulls=12,
             effective_approvers=1.2, review_required_visible=True, unapproved_share=0.25),
        _row(approved_pulls=20, effective_approvers=3.0),
        _row(status="excluded: archived"),
    ]  # fmt: skip
    a = tp.analyze(rows)
    assert a["included"] == 5
    rq1 = a["rq1_publish_gate"]
    assert rq1["primary_no_observed_two_person_path"]["k"] == 4
    assert rq1["secondary_no_configured_two_person_gate"]["k"] == 4
    assert (rq1["latest_release_path"]["V2"]["k"], rq1["latest_release_path"]["U"]["k"]) == (1, 4)
    assert rq1["configured_gate_by_path"]["G2"]["V2"]["k"] == 1
    assert {g: v["k"] for g, v in a["rq1_publish_gate"]["distribution"].items()} == {
        "G2": 1,
        "G1": 2,
        "G0": 1,
        "NE": 1,
    }
    assert a["rq1_publish_gate"]["exploratory_by_group"]["user"]["n"] == 1
    assert (
        a["rq2_single_publisher"]["primary"]["k"],
        a["rq2_single_publisher"]["primary"]["n"],
    ) == (3, 4)
    assert a["rq2_single_publisher"]["no_visible_publisher"] == 1
    rq3 = a["rq3_dormant_authority"]
    assert (
        rq3["primary_gated_with_dormant_reviewer"]["k"],
        rq3["primary_gated_with_dormant_reviewer"]["n"],
    ) == (1, 2)
    assert (
        rq3["primary_dormant_solo_authority"]["k"],
        rq3["primary_dormant_solo_authority"]["n"],
    ) == (1, 5)
    assert rq3["gated_with_team_reviewers_only"] == 1
    rq4 = a["rq4_review_concentration"]
    assert (rq4["primary_single_reviewer"]["k"], rq4["primary_single_reviewer"]["n"]) == (1, 2)
    assert rq4["review_visibly_required"]["n"] == 1
    assert rq4["exploratory_unapproved_merges_where_required"] == 0.25


def test_measurement_sample_is_seeded():
    rows = [_row(repo=f"o/r{i}") for i in range(100)] + [
        _row(repo="o/x", status="excluded: archived")
    ]
    first = tp.measurement_sample(rows)
    assert len(first) == 40 and first == tp.measurement_sample(list(reversed(rows)))
    assert "o/x" not in first
    assert tp.measurement_sample(rows[:5]) == sorted(r["repo"] for r in rows[:5])
