"""Tests for hrg check: publishing definitions, the package check, privacy and the CLI."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner

from human_risk_graph import cli as cli_module
from human_risk_graph.cli import cli
from human_risk_graph.package_check import (
    CheckError,
    check_package,
    fetch_json,
    people_names,
    worst_level,
)
from human_risk_graph.publishing import (
    environment_gate,
    github_repo,
    human_publishers,
    is_dormant,
    latest_release,
    publish_gate,
    publisher_repository,
    release_path,
)

NOW = datetime(2026, 12, 1, tzinfo=timezone.utc)


def _iso(days_before):
    return (NOW - timedelta(days=days_before)).isoformat().replace("+00:00", "Z")


def _env(name, users=(), teams=(), self_review=True, admin_bypass=True, rule=True):
    reviewers = [{"type": "User", "reviewer": {"login": u}} for u in users]
    reviewers += [{"type": "Team", "reviewer": {"slug": t}} for t in teams]
    rules = (
        [{"type": "required_reviewers", "prevent_self_review": not self_review,
          "reviewers": reviewers}]
        if rule
        else []
    )  # fmt: skip
    return {"name": name, "protection_rules": rules, "can_admins_bypass": admin_bypass}


# Definitions (the same as in the two-person study)


def test_github_repo_from_pypi_metadata():
    assert github_repo({"project_urls": {"Source": "https://github.com/psf/requests"}}) == (
        "psf/requests"
    )
    assert github_repo({"home_page": "https://github.com/a/b.git"}) == "a/b"
    assert github_repo({"project_urls": {"Funding": "https://github.com/sponsors/x"}}) is None


def test_gates_and_classes():
    two = environment_gate(_env("pypi", ["a"], self_review=False, admin_bypass=False))
    one = environment_gate(_env("release", ["a"], teams=["core"]))
    none = environment_gate(_env("docs", rule=False))
    assert two["two_person"] and one["gated"] and not one["two_person"]
    assert one["team_reviewers"] == ["core"] and not none["publishing"]
    assert publish_gate([]) == "NE" and publish_gate([none]) == "NE"
    assert publish_gate([environment_gate(_env("pypi", rule=False))]) == "G0"
    assert publish_gate([one]) == "G1" and publish_gate([one, two]) == "G2"


def test_release_path_and_publishers():
    gates = [environment_gate(_env("PyPI", ["a"], self_review=False, admin_bypass=False))]
    pypi_form = {"kind": "GitHub", "repository": "o/r", "environment": "pypi"}
    pep_form = {"kind": "GitHub", "repository_owner": "o", "repository_name": "r",
                "environment": "pypi"}  # fmt: skip
    assert publisher_repository(pep_form) == "o/r"
    assert release_path([pypi_form, pep_form], "O/R", gates) == "V2"
    assert release_path([pypi_form, None], "o/r", gates) == "P"
    assert release_path([None], "o/r", gates) == "U"
    assert release_path([{**pypi_form, "repository": "x/y"}], "o/r", gates) == "O"
    assert release_path([{**pypi_form, "environment": None}], "o/r", gates) == "V0"
    events = [{"login": "a", "when": NOW - timedelta(days=1)},
              {"login": "b", "when": NOW - timedelta(days=400)},
              {"login": "ci-bot", "when": NOW - timedelta(days=1)}]  # fmt: skip
    assert human_publishers(events, NOW) == {"a"}
    assert is_dormant(None, NOW, 90) and not is_dormant(NOW, NOW, 90)


def test_latest_release_ignores_yanked_and_future_files():
    def f(name, days, yanked=False):
        return {"filename": name, "upload_time_iso_8601": _iso(days), "yanked": yanked}

    releases = {"1.0": [f("a-1.0.tar.gz", 50)], "1.1": [f("a-1.1.tar.gz", 2, yanked=True)],
                "2.0": [f("a-2.0.tar.gz", -1)]}  # fmt: skip
    assert latest_release(releases, NOW) == ("1.0", ["a-1.0.tar.gz"])


# The check


class FakeClient:
    def __init__(self, routes, token="t"):
        self.routes, self.token, self.requested = routes, token, []

    def get(self, path, params=None, limit=0):
        self.requested.append(path)
        value = self.routes.get(path)
        return value(params or {}) if callable(value) else value


def _pypi(environment="pypi", provenance=True, urls=True, files=("pkg-1.0.tar.gz",)):
    project_urls = {"Source": "https://github.com/acme/pkg"} if urls else {}
    publisher = {"kind": "GitHub", "repository": "acme/pkg", "workflow": "release.yml",
                 "environment": environment}  # fmt: skip

    def fetch(url, accept):
        if url == "https://pypi.org/pypi/pkg/json":
            return {
                "info": {"name": "pkg", "project_urls": project_urls},
                "releases": {
                    "1.0": [{"filename": n, "upload_time_iso_8601": _iso(3)} for n in files]
                },
            }
        if "/integrity/pkg/1.0/" in url:
            filename = url.split("/")[-2]
            attested = provenance is True or (bool(provenance) and filename in provenance)
            return {"attestation_bundles": [{"publisher": publisher}]} if attested else None
        return None  # fmt: skip

    return fetch


def _github(envs, reviewers_last_commit=None, publishers=("pub-lead-x3", "pub-second-x4")):
    reviewers_last_commit = reviewers_last_commit or {}
    return {
        "repos/acme/pkg": {"full_name": "acme/pkg", "default_branch": "main"},
        "repos/acme/pkg/environments": {"environments": envs},
        "repos/acme/pkg/deployments": [],
        "repos/acme/pkg/releases": [
            {"author": {"login": who}, "published_at": _iso(10 + i)} for i, who in enumerate(publishers)
        ],
        "repos/acme/pkg/pulls": [{"number": 1, "merged_at": _iso(5), "user": {"login": "dev"}}],
        "repos/acme/pkg/pulls/1/reviews": [
            {"user": {"login": "rev-active-x1"}, "state": "APPROVED", "submitted_at": _iso(5)}],
        "repos/acme/pkg/commits": lambda params: (
            [{"commit": {"committer": {"date": _iso(reviewers_last_commit[params["author"]])}}}]
            if params["author"] in reviewers_last_commit else []
        ),
    }  # fmt: skip


def test_two_person_gate_is_ok():
    envs = [_env("pypi", ["rev-active-x1"], self_review=False, admin_bypass=False)]
    r = check_package("pkg", FakeClient(_github(envs)), _pypi(), now=NOW)
    assert (r["path"], r["configured_gate"], r["publishers_seen"]) == ("V2", "G2", 2)
    assert worst_level(r) == "ok" and len(r["findings"]) == 1
    assert r["findings"][0]["title"] == (
        "The latest release went through a two-person gate (environment pypi)."
    )
    assert r["environments"] == [{"name": "pypi", "used_by_latest_release": True,
                                  "required_reviewers": 1, "prevent_self_review": True,
                                  "admins_can_bypass": False, "two_person_gate": True}]  # fmt: skip


def test_configured_gate_that_releases_do_not_take():
    envs = [_env("pypi", ["rev-active-x1"], self_review=False, admin_bypass=False),
            _env("release", rule=False)]  # fmt: skip
    r = check_package("pkg", FakeClient(_github(envs)), _pypi(environment="release"), now=NOW)
    assert (r["path"], r["configured_gate"]) == ("V0", "G2")
    titles = [f["title"] for f in r["findings"]]
    assert (
        "A two-person gate is configured, but the latest release did not go through it." in titles
    )
    assert r["findings"][0]["advice"].startswith("On the publishing environment")


def test_dormant_reviewer_who_can_approve_alone_is_an_error_without_names():
    envs = [_env("pypi", ["rev-active-x1", "rev-gone-x2"], teams=["core"])]
    client = FakeClient(_github(envs, {"rev-gone-x2": 200}, publishers=("pub-lead-x3",)))
    r = check_package("pkg", client, _pypi(), now=NOW)
    assert (r["path"], r["dormant_reviewers"], r["dormant_solo_reviewers"]) == ("V1", 1, 1)
    assert worst_level(r) == "error" and r["findings"][0]["level"] == "error"
    assert any("One person published every release" in f["title"] for f in r["findings"])
    assert "Team reviewers are not checked" in " ".join(r["notes"])
    text = json.dumps(r)
    assert "rev-gone-x2" not in text and "rev-active-x1" not in text and "pub-lead-x3" not in text
    assert people_names(r) == set()


def test_show_people_names_them():
    envs = [_env("pypi", ["rev-active-x1", "rev-gone-x2"])]
    client = FakeClient(_github(envs, {"rev-gone-x2": 200}, publishers=("pub-lead-x3",)))
    r = check_package("pkg", client, _pypi(), now=NOW, show_people=True)
    assert r["people"]["dormant_reviewers"] == [
        {"login": "rev-gone-x2", "last_seen": _iso(200)[:10], "can_approve_alone": True}
    ]
    assert r["people"]["publishers_seen"] == ["pub-lead-x3"]
    assert people_names(r) == {"rev-active-x1", "rev-gone-x2", "pub-lead-x3"}


def test_unobservable_and_partial_paths():
    no_env = FakeClient(_github([]))
    r = check_package("pkg", no_env, _pypi(provenance=False), now=NOW)
    assert (r["path"], r["configured_gate"], worst_level(r)) == ("U", "NE", "note")
    assert "Trusted Publishing" in r["findings"][0]["advice"]
    files = ("pkg-1.0.tar.gz", "pkg-1.0-py3-none-any.whl")
    r = check_package("pkg", no_env, _pypi(provenance=("pkg-1.0.tar.gz",), files=files), now=NOW)
    assert r["path"] == "P" and "Only 1 of 2 files" in r["findings"][0]["title"]
    r = check_package("pkg", no_env, _pypi(environment=None), now=NOW)
    assert r["path"] == "V0" and r["findings"][0]["advice"].startswith("Publish from a GitHub")


def test_repository_from_provenance_and_missing_repository():
    r = check_package("pkg", FakeClient(_github([])), _pypi(urls=False), now=NOW)
    assert r["repository"] == "acme/pkg"  # PyPI has no link, the provenance names it
    r = check_package("pkg", FakeClient({}), _pypi(urls=False, provenance=False), now=NOW)
    assert r["repository"] is None and "pass --repo" in " ".join(r["notes"])
    r = check_package("pkg", FakeClient({}), _pypi(), now=NOW, repo="acme/pkg")
    assert not r["repository_visible"] and "not visible" in " ".join(r["notes"])


def test_without_a_token_reviews_are_not_read():
    envs = [_env("pypi", ["rev-active-x1"])]
    client = FakeClient(_github(envs), token=None)
    r = check_package("pkg", client, _pypi(), now=NOW, read_reviews=False)
    assert not any("/pulls" in path for path in client.requested)
    assert "reviews are not read" in " ".join(r["notes"])
    assert r["dormant_reviewers"] == 1  # only commits, releases and deployments count


def test_errors():
    with pytest.raises(CheckError, match="not a PyPI package name"):
        check_package("../etc", FakeClient({}), _pypi())
    with pytest.raises(CheckError, match="is not on PyPI"):
        check_package("other", FakeClient({}), _pypi())
    with pytest.raises(ValueError, match="not a PyPI URL"):
        fetch_json("https://evil.example/pkg/json")


# CLI


@pytest.fixture
def fake(monkeypatch):
    def install(routes, fetch):
        monkeypatch.setattr(cli_module, "GitHubClient", lambda token, api=None: FakeClient(routes))
        monkeypatch.setattr(cli_module, "default_token", lambda api=None: "t")
        original = cli_module.check_package
        monkeypatch.setattr(
            cli_module, "check_package",
            lambda *a, **k: original(*a, fetch=fetch, now=NOW, **k),
        )  # fmt: skip

    return install


def test_cli_check_text_json_and_fail_on(fake):
    envs = [_env("pypi", ["rev-active-x1", "rev-gone-x2"])]
    fake(_github(envs, {"rev-gone-x2": 200}, publishers=("pub-lead-x3",)), _pypi())
    result = CliRunner().invoke(cli, ["check", "pkg"])
    assert result.exit_code == 0, result.output
    assert "hrg check pkg 1.0 · acme/pkg" in result.output
    assert "Release path  V1" in result.output and "rev-gone-x2" not in result.output
    assert "use --show-people" in result.output
    shown = CliRunner().invoke(cli, ["check", "pkg", "--show-people"]).output
    assert "Inactive reviewer: rev-gone-x2" in shown
    data = json.loads(CliRunner().invoke(cli, ["check", "pkg", "--format", "json"]).output)
    assert data["path"] == "V1" and "people" not in data
    assert CliRunner().invoke(cli, ["check", "pkg", "--fail-on", "error"]).exit_code == 3
    assert CliRunner().invoke(cli, ["check", "pkg", "--fail-on", "warning"]).exit_code == 3


def test_cli_check_passes_on_a_clean_package_and_reports_errors(fake):
    envs = [_env("pypi", ["rev-active-x1"], self_review=False, admin_bypass=False)]
    fake(_github(envs), _pypi())
    assert CliRunner().invoke(cli, ["check", "pkg", "--fail-on", "warning"]).exit_code == 0
    result = CliRunner().invoke(cli, ["check", "missing-package"])
    assert result.exit_code == 1 and "is not on PyPI" in result.output


def test_fetch_json(monkeypatch):
    import io
    import urllib.error

    from human_risk_graph import package_check

    def opener(outcome):
        def urlopen(request, timeout):
            assert request.full_url.startswith("https://pypi.org/")
            if isinstance(outcome, Exception):
                raise outcome
            return io.BytesIO(json.dumps(outcome).encode())

        return urlopen

    url = "https://pypi.org/pypi/pkg/json"
    monkeypatch.setattr(package_check.urllib.request, "urlopen", opener({"ok": 1}))
    assert fetch_json(url) == {"ok": 1}
    for code, expected in ((404, None), (500, CheckError)):
        error = urllib.error.HTTPError(url, code, "x", {}, None)
        monkeypatch.setattr(package_check.urllib.request, "urlopen", opener(error))
        if expected is None:
            assert fetch_json(url) is None
        else:
            with pytest.raises(CheckError, match="PyPI error 500"):
                fetch_json(url)
    monkeypatch.setattr(
        package_check.urllib.request, "urlopen", opener(urllib.error.URLError("offline"))
    )
    with pytest.raises(CheckError, match="Cannot reach PyPI: offline"):
        fetch_json(url)


def test_deployments_count_as_publishing_and_activity():
    envs = [_env("pypi", ["rev-deployer-x5"])]
    routes = _github(envs, publishers=())
    routes["repos/acme/pkg/deployments"] = [
        {"creator": {"login": "rev-deployer-x5"}, "created_at": _iso(2)},
        {"creator": {"login": "github-actions[bot]"}, "created_at": _iso(1)},
    ]
    r = check_package("pkg", FakeClient(routes), _pypi(), now=NOW, show_people=True)
    assert r["publishers_seen"] == 1 and r["dormant_reviewers"] == 0
    assert r["people"]["publishers_seen"] == ["rev-deployer-x5"]


def test_notes_for_missing_files_and_hidden_environments():
    routes = _github([])
    routes["repos/acme/pkg/environments"] = None
    r = check_package("pkg", FakeClient(routes), _pypi(files=()), now=NOW)
    assert r["version"] is None and r["path"] == "U"
    assert "No release files on PyPI." in r["notes"]
    assert "Deployment environments are not visible." in r["notes"]
    assert worst_level({"findings": []}) == "ok"


def test_inactive_reviewer_who_cannot_approve_alone_is_a_warning(fake):
    envs = [
        _env("docs", ["rev-docs-x6"]),  # not a publishing environment: ignored
        _env("pypi", ["rev-gone-x2"], teams=["core"], self_review=False),
    ]
    fake(_github(envs, {"rev-gone-x2": 200}), _pypi())
    result = CliRunner().invoke(cli, ["check", "pkg"])
    assert result.exit_code == 0, result.output
    assert "△ 1 reviewer(s) of a publishing environment have no activity seen" in result.output
    assert "▲" not in result.output  # self-review is prevented: not solo
    assert "Note: Team reviewers are not checked for activity" in result.output
    data = json.loads(CliRunner().invoke(cli, ["check", "pkg", "--format", "json"]).output)
    assert (data["reviewers"], data["dormant_reviewers"], data["dormant_solo_reviewers"]) == (
        1,
        1,
        0,
    )
    assert [e["name"] for e in data["environments"]] == ["pypi"]


def test_parse_time_of_nothing():
    from human_risk_graph.publishing import parse_time

    assert parse_time(None) is None and parse_time("") is None
