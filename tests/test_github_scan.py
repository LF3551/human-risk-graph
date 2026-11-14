"""Tests for hrg scan github, using a fake API instead of the network."""

import base64
import json

import pytest
import yaml
from click.testing import CliRunner

from human_risk_graph import HumanRiskGraph
from human_risk_graph import cli as cli_module
from human_risk_graph.cli import cli
from human_risk_graph.github_scan import (
    GitHubClient,
    GitHubError,
    GitHubScanner,
    ScanResult,
    draft_yaml,
    list_repositories,
    merge_scans,
    merge_with_existing,
    owners_for,
    parse_codeowners,
    scan_organization,
)
from human_risk_graph.loader import load_organization


class FakeClient:
    """Maps API paths to responses; unknown paths behave like 404 (None)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = 0
        self.token = "test-value"
        self.requested = []

    def get(self, path, params=None, limit=0):
        self.calls += 1
        self.requested.append(path)
        response = self.routes.get(path)
        return response(params or {}) if callable(response) else response


def _codeowners(text):
    return {"content": base64.b64encode(text.encode()).decode()}


def _pr(number, author):
    return {"number": number, "user": {"login": author}, "merged_at": "2026-01-01T00:00:00Z"}


def _review(login, state="APPROVED"):
    return {"user": {"login": login}, "state": state}


def _routes(**extra):
    routes = {
        "repos/acme/api": {"default_branch": "main"},
        "repos/acme/api/environments": {"total_count": 0, "environments": []},
        "repos/acme/api/pulls": [
            _pr(1, "dev"),
            _pr(2, "dev"),
            _pr(3, "lead"),
            _pr(4, "dependabot[bot]"),
            {"number": 5, "user": {"login": "dev"}, "merged_at": None},
        ],
        "repos/acme/api/pulls/1/reviews": [_review("lead"), _review("dev")],
        "repos/acme/api/pulls/2/reviews": [_review("lead", "COMMENTED")],
        "repos/acme/api/pulls/2": {"merged_by": {"login": "lead"}},
        "repos/acme/api/pulls/3/reviews": [_review("dev"), _review("renovate[bot]")],
    }
    routes.update(extra)
    return routes


def _deps(result):
    return {(d["from"], d["to"]): d for d in result.dependencies}


REVIEW_RULE = {
    "repos/acme/api/rules/branches/main": [
        {"type": "pull_request", "parameters": {"required_approving_review_count": 1}}
    ]
}


# CODEOWNERS


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("*", "src/a.py", True),
        ("*.py", "src/a.py", True),
        ("*.py", "src/a.go", False),
        ("/docs/", "docs/x.md", True),
        ("/docs/", "src/docs/x.md", False),
        ("docs/", "docs/x.md", True),
        ("apps/", "src/apps/x.py", True),
        ("/build/logs/", "build/logs/a/b.log", True),
        ("docs/*", "docs/a.md", True),
        ("docs/*", "docs/sub/a.md", False),
        ("**/logs", "a/b/logs/x", True),
        ("/src/**/test.py", "src/a/b/test.py", True),
    ],
)
def test_codeowners_patterns(pattern, path, expected):
    rules = parse_codeowners(f"{pattern} @owner")
    assert (owners_for(path, rules) == ["@owner"]) is expected


def test_codeowners_last_match_wins_and_comments():
    rules = parse_codeowners(
        "# comment\n*       @all  # trailing\n\n*.go    @gophers @acme/go-team\n/docs/  \n"
    )
    assert owners_for("main.py", rules) == ["@all"]
    assert owners_for("cmd/main.go", rules) == ["@gophers", "@acme/go-team"]
    assert owners_for("docs/a.md", rules) == []  # rule without owners unsets ownership


# Scanner


def test_scan_reviews_unreviewed_merges_and_bots():
    client = FakeClient(_routes())
    result = GitHubScanner(client, "acme/api").scan()
    deps = _deps(result)

    assert result.branch == "main"
    assert result.pull_requests == 3  # PR 4 is by a bot, PR 5 was closed without merge
    # No review requirement: merging PR 2 without review bypasses nothing.
    assert result.review_required is False
    assert deps[("lead", "dev")]["type"] == "approval"
    assert deps[("lead", "dev")]["weight"] == 0.5
    assert any("not counted as bypasses" in n for n in result.notes)
    assert result.gaps == [
        "Repository admins are not visible (they can change settings and branch protection; "
        "needs push access)."
    ]
    # dev approved lead's only PR; self-approval on PR 1 is ignored
    assert deps[("dev", "lead")]["type"] == "approval"
    assert deps[("dev", "lead")]["weight"] == 1.0
    assert all(d["confirmed"] is False for d in result.dependencies)
    assert all(d["source"] and d["evidence"] for d in result.dependencies)
    ids = {p["id"] for p in result.people}
    assert ids == {"dev", "lead"}  # bots dropped
    assert "No CODEOWNERS file found." in result.notes


def test_unreviewed_merge_is_bypass_when_reviews_are_required():
    result = GitHubScanner(FakeClient(_routes(**REVIEW_RULE)), "acme/api").scan()
    dep = _deps(result)[("lead", "dev")]
    assert result.review_required is True
    assert dep["type"] == "bypass"
    assert dep["source"] == "merge-history"
    assert "#2" in dep["evidence"]
    assert "approved 1 of 2 merged PRs by dev" in dep["evidence"]


def test_invisible_protection_is_a_gap_not_a_bypass():
    routes = _routes(**{"repos/acme/api/branches/main": {"protected": True}})
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    assert result.review_required is None
    assert _deps(result)[("lead", "dev")]["type"] == "approval"
    assert any("protection settings are not visible" in g for g in result.gaps)
    assert any("not counted as bypasses" in g for g in result.gaps)
    assert result.coverage()["review_required"] == "unknown"


def test_unreviewed_merge_becomes_bypass_over_approval():
    routes = _routes(**REVIEW_RULE)
    routes["repos/acme/api/pulls/2"] = {"merged_by": {"login": "dev"}}
    routes["repos/acme/api/pulls"] = [_pr(1, "dev"), _pr(2, "dev")]
    routes["repos/acme/api/pulls/1/reviews"] = [_review("lead"), _review("qa")]
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    deps = _deps(result)
    assert deps[("dev", "lead")]["type"] == "bypass"
    assert deps[("dev", "lead")]["source"] == "merge-history"
    assert "#2" in deps[("dev", "lead")]["evidence"]
    assert deps[("dev", "qa")]["type"] == "bypass"
    dev = next(p for p in result.people if p["id"] == "dev")
    assert "can bypass review" in dev["evidence"]


def test_include_bots():
    result = GitHubScanner(FakeClient(_routes()), "acme/api", include_bots=True).scan()
    ids = {p["id"] for p in result.people}
    assert {"dependabot[bot]", "renovate[bot]"} <= ids


def test_codeowners_with_teams_and_files():
    routes = _routes(
        **{
            "repos/acme/api/contents/.github/CODEOWNERS": _codeowners(
                "* @lead\n/docs/ @acme/writers\n"
            ),
            "orgs/acme/teams/writers/members": [{"login": "ann"}, {"login": "dev"}],
            "repos/acme/api/pulls/2/reviews": [_review("ann")],
            "repos/acme/api/pulls/1/files": [{"filename": "docs/a.md"}],
            "repos/acme/api/pulls/2/files": [{"filename": "src/a.py"}],
            "repos/acme/api/pulls/3/files": [{"filename": "docs/b.md"}],
        }
    )
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    deps = _deps(result)
    # ann reviewed PR 2 and owns docs/ in PR 1; lead reviewed PR 1 and owns src/ in PR 2
    for approver in ("ann", "lead"):
        assert deps[(approver, "dev")]["type"] == "approval"
        assert deps[(approver, "dev")]["source"] == "codeowners+pr-reviews"
        assert deps[(approver, "dev")]["weight"] == 0.5
    assert deps[("ann", "lead")]["source"] == "codeowners"
    assert "CODEOWNERS read from .github/CODEOWNERS." in result.notes
    ann = next(p for p in result.people if p["id"] == "ann")
    assert ann["criticality"] == 0.67  # base + code owner + a third of approvals


def test_default_codeowners_rule_does_not_fetch_files():
    routes = _routes(**{"repos/acme/api/contents/CODEOWNERS": _codeowners("* @lead\n")})
    client = FakeClient(routes)
    GitHubScanner(client, "acme/api").scan()
    assert not any(path.endswith("/files") for path in client.requested)


def test_invisible_team_kept_as_handle():
    routes = _routes(**{"repos/acme/api/contents/CODEOWNERS": _codeowners("* @acme/core\n")})
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    assert ("@acme/core", "dev") in _deps(result)
    assert any("@acme/core" in n for n in result.gaps)


def test_ruleset_admin_bypass():
    routes = _routes(
        **{
            "repos/acme/api/rules/branches/main": [
                {
                    "type": "pull_request",
                    "ruleset_id": 7,
                    "parameters": {"required_approving_review_count": 1},
                }
            ],
            "repos/acme/api/rulesets/7": {
                "bypass_actors": [
                    {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"},
                    {"actor_id": 9, "actor_type": "Integration"},
                ]
            },
            "repos/acme/api/collaborators": [{"login": "boss"}],
        }
    )
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    deps = _deps(result)
    assert deps[("boss", "lead")]["type"] == "bypass"
    assert deps[("boss", "lead")]["source"] == "branch-rules"
    assert deps[("boss", "dev")]["type"] == "bypass"
    assert "Branch main requires approving reviews." in result.notes
    assert any("Integration" in n for n in result.notes)


def test_invisible_ruleset_and_classic_protection():
    routes = _routes(
        **{
            "repos/acme/api/rules/branches/main": [{"type": "pull_request", "ruleset_id": 3}],
            "repos/acme/api/branches/main/protection": {
                "required_pull_request_reviews": {
                    "required_approving_review_count": 2,
                    "require_code_owners_reviews": True,
                    "bypass_pull_request_allowances": {"users": [{"login": "ops"}]},
                },
                "enforce_admins": {"enabled": True},
            },
        }
    )
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    assert any("ruleset 3 are not visible" in n for n in result.gaps)
    assert _deps(result)[("ops", "dev")]["type"] == "bypass"


def test_repo_not_found_and_bad_name():
    with pytest.raises(GitHubError, match="not found"):
        GitHubScanner(FakeClient({}), "acme/api").scan()
    with pytest.raises(ValueError, match="OWNER/REPO"):
        GitHubScanner(FakeClient({}), "acme")


# Draft file


def test_draft_loads_and_merge_keeps_decisions(tmp_path):
    result = GitHubScanner(FakeClient(_routes()), "acme/api").scan()
    path = tmp_path / "org.yaml"
    path.write_text(draft_yaml(result), encoding="utf-8")
    text = path.read_text()
    assert text.startswith("# Draft generated by `hrg scan github acme/api`")
    data = load_organization(path)
    assert {p["id"] for p in data["people"]} == {"dev", "lead"}

    # A person confirms one link, edits criticality, and adds a link by hand.
    for dep in data["dependencies"]:
        if (dep["from"], dep["to"]) == ("lead", "dev"):
            dep["confirmed"] = True
    data["people"][0]["criticality"] = 0.95
    data["people"].append({"id": "cfo", "name": "CFO", "criticality": 0.9})
    data["dependencies"].append({"from": "cfo", "to": "lead", "type": "escalation"})
    edited = data["people"][0]["id"]

    again = GitHubScanner(FakeClient(_routes()), "acme/api").scan()
    notes = merge_with_existing(again, data)
    deps = _deps(again)
    assert deps[("lead", "dev")]["confirmed"] is True
    assert deps[("dev", "lead")]["confirmed"] is False
    assert ("cfo", "lead") in deps
    assert next(p for p in again.people if p["id"] == edited)["criticality"] == 0.95
    assert "cfo" in {p["id"] for p in again.people}
    assert len(notes) == 2


def _release(login, draft=False):
    return {"author": {"login": login}, "draft": draft}


def test_scan_drafts_functions():
    routes = _routes(
        **REVIEW_RULE,
        **{
            "repos/acme/api/releases": [_release("lead"), _release("lead"), _release("dev", True)],
            "repos/acme/api/collaborators": [{"login": "lead"}],
        },
    )
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    functions = {f["id"]: f for f in result.functions}

    merge = functions["merge"]
    assert (merge["requires"], merge["confirmed"]) == (2, False)
    assert merge["performers"] == ["dev", "lead"]
    assert merge["alone"] == ["lead"]  # merged dev's PR 2 without review
    assert "SLSA Source Level 4" in merge["evidence"]
    assert functions["release"]["performers"] == ["lead"]  # drafts are not releases
    assert "2 of the last 2 releases" in functions["release"]["evidence"]
    assert functions["admin"]["performers"] == ["lead"]

    hrg = HumanRiskGraph(result.people, result.dependencies, result.functions)
    assert hrg.calculate(model="hrg-3")["solo_functions"] == ["merge", "release", "admin"]


@pytest.mark.parametrize(
    "login, bot",
    [
        ("dependabot[bot]", True),
        ("prombot", True),
        ("jetstack-release-bot", True),
        ("k8s-ci-robot", True),
        ("my-bot-account", True),
        ("bottomline", False),
        ("ivanvc", False),
        ("roboto", False),
    ],
)
def test_bot_names(login, bot):
    from human_risk_graph.github_scan import _is_bot

    assert _is_bot(login) is bot


def test_releases_by_automation_are_a_gap():
    routes = _routes(
        **{"repos/acme/api/releases": [_release("github-actions[bot]"), _release("prombot")]}
    )
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    assert "release" not in {f["id"] for f in result.functions}
    assert any("published by automation" in g for g in result.gaps)


def test_rescan_keeps_function_decisions(tmp_path):
    routes = _routes(**{"repos/acme/api/releases": [_release("lead")]})
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    path = tmp_path / "org.yaml"
    path.write_text(draft_yaml(result), encoding="utf-8")
    data = load_organization(path)
    release = next(f for f in data["functions"] if f["id"] == "release")
    release.update(criticality=0.5, requires=2, separation="not-required", confirmed=True)
    data["functions"].append({"id": "restore-db", "performers": ["dev"], "criticality": 0.9})

    again = GitHubScanner(FakeClient(routes), "acme/api").scan()
    notes = merge_with_existing(again, data)
    functions = {f["id"]: f for f in again.functions}
    assert (functions["release"]["criticality"], functions["release"]["requires"]) == (0.5, 2)
    assert functions["release"]["confirmed"] is True
    assert functions["release"]["separation"] == "not-required"
    assert "restore-db" in functions
    assert "Kept 1 functions the scan does not draft." in notes


def test_merge_without_existing():
    result = GitHubScanner(FakeClient(_routes()), "acme/api").scan()
    assert merge_with_existing(result, None) == []


# CLI


@pytest.fixture
def fake_github(monkeypatch):
    def install(routes):
        def client(token, api="https://api.github.com"):
            fake = FakeClient(routes)
            install.apis.append(api)
            return fake

        monkeypatch.setattr(cli_module, "GitHubClient", client)
        monkeypatch.setattr(cli_module, "default_token", lambda api=None: None)

    install.apis = []
    return install


def test_cli_scan_then_analyze(tmp_path, fake_github, monkeypatch):
    fake_github(_routes(**{"repos/acme/api/branches/main": {"protected": True}}))
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "github", "acme/api"])
    assert result.exit_code == 0, result.output
    draft = tmp_path / "api-org.yaml"
    assert draft.exists()
    assert "hrg analyze api-org.yaml" in " ".join(result.output.split())
    assert "Gap:" in result.output
    coverage = yaml.safe_load(draft.read_text())["coverage"]
    assert coverage["review_required"] == "unknown"
    assert len(coverage["gaps"]) == 3

    analyzed = runner.invoke(
        cli, ["analyze", str(draft), "--format", "json", "--output", "out.json", "--no-visualize"]
    )
    assert analyzed.exit_code in (0, 3), analyzed.output
    output = " ".join(analyzed.output.split())
    assert "unconfirmed" in output
    assert "3 data gaps" in output

    report = json.loads((tmp_path / "out.json").read_text())
    total = report["metadata"]["dependencies_count"]
    assert report["metadata"]["unconfirmed_dependencies"] == total > 0
    assert report["metadata"]["coverage_gaps"] == coverage["gaps"]

    for fmt, name in (("html", "out.html"), ("markdown", "out.md")):
        runner.invoke(
            cli, ["analyze", str(draft), "--format", fmt, "--output", name, "--no-visualize"]
        )
        text = (tmp_path / name).read_text()
        assert f"{total} of {total} dependencies and 1 of 1 functions are unconfirmed" in text
        assert "protection settings are not visible" in text


def test_cli_scan_updates_existing_draft(tmp_path, fake_github):
    fake_github(_routes())
    out = tmp_path / "draft.yaml"
    runner = CliRunner()
    assert runner.invoke(cli, ["scan", "github", "acme/api", "-o", str(out)]).exit_code == 0
    data = yaml.safe_load(out.read_text())
    for dep in data["dependencies"]:
        dep["confirmed"] = True
    out.write_text(yaml.safe_dump(data))
    result = runner.invoke(cli, ["scan", "github", "acme/api", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "Kept confirmation" in result.output
    assert all(d["confirmed"] for d in yaml.safe_load(out.read_text())["dependencies"])


def test_cli_scan_errors(tmp_path, fake_github):
    fake_github({})
    result = CliRunner().invoke(cli, ["scan", "github", "acme/api", "-o", str(tmp_path / "x")])
    assert result.exit_code == 1
    assert "not found" in result.output
    result = CliRunner().invoke(cli, ["scan", "github", "nope", "-o", str(tmp_path / "x")])
    assert result.exit_code == 1


# Retries of transient GitHub errors


class _Response:
    def __init__(self, body):
        self.body, self.headers = body, {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.body).encode()


def _flaky(monkeypatch, outcomes):
    """urlopen that raises or returns the given outcomes in order; no real sleeping."""
    import urllib.error

    from human_risk_graph import github_scan

    calls = []

    def urlopen(request, timeout):
        calls.append(request.full_url)
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, int):
            raise urllib.error.HTTPError(request.full_url, outcome, "error", {}, None)
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)

    monkeypatch.setattr(github_scan.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(github_scan.time, "sleep", lambda s: None)
    return calls


def test_client_retries_server_errors(monkeypatch):
    calls = _flaky(monkeypatch, [503, 502, {"ok": True}])
    assert GitHubClient("t").get("repos/acme/api") == {"ok": True}
    assert len(calls) == 3


def test_client_retries_network_errors(monkeypatch):
    import urllib.error

    calls = _flaky(monkeypatch, [urllib.error.URLError("reset"), TimeoutError(), {"ok": 1}])
    assert GitHubClient("t").get("repos/acme/api") == {"ok": 1}
    assert len(calls) == 3


def test_client_gives_up_after_retries(monkeypatch):
    calls = _flaky(monkeypatch, [503])
    with pytest.raises(GitHubError, match="GitHub API error 503"):
        GitHubClient("t").get("repos/acme/api")
    assert len(calls) == 4  # first try and three retries


@pytest.mark.parametrize("code, calls_expected", [(404, 1), (400, 1)])
def test_client_does_not_retry_client_errors(monkeypatch, code, calls_expected):
    calls = _flaky(monkeypatch, [code])
    if code == 404:
        assert GitHubClient("t").get("repos/acme/api") is None
    else:
        with pytest.raises(GitHubError, match="400"):
            GitHubClient("t").get("repos/acme/api")
    assert len(calls) == calls_expected


def test_client_requires_https():
    with pytest.raises(ValueError, match="https"):
        GitHubClient("t", api="http://api.github.com")
    assert GitHubClient("t", api="https://ghe.example.com/api/v3/").api == (
        "https://ghe.example.com/api/v3"
    )


def test_client_keeps_the_token_inside_the_api(monkeypatch):
    # Pagination follows Link headers; one pointing elsewhere must not receive the token.
    calls = _flaky(monkeypatch, [{"ok": 1}])
    client = GitHubClient("t")
    for url in ("https://evil.example/x", "https://api.github.com.evil.example/x"):
        with pytest.raises(GitHubError, match="Refusing to request"):
            client._request(url)
    assert calls == []


# Deployment environments and activity


def _env(name, reviewers=None, self_review=True, admins_bypass=True, branch_policy=False):
    rules = []
    if reviewers is not None:
        rules.append(
            {
                "type": "required_reviewers",
                "prevent_self_review": not self_review,
                "reviewers": reviewers,
            }
        )
    if branch_policy:
        rules.append({"type": "branch_policy"})
    return {"name": name, "protection_rules": rules, "can_admins_bypass": admins_bypass}


def _user(login):
    return {"type": "User", "reviewer": {"login": login}}


def _deployment(login, when="2026-11-01T09:00:00Z"):
    return {"creator": {"login": login}, "created_at": when}


def _environments(*envs):
    return {"total_count": len(envs), "environments": list(envs)}


def _functions(result):
    return {f["id"]: f for f in result.functions}


def test_deploy_with_reviewers_who_can_approve_themselves():
    routes = _routes(
        **{
            "repos/acme/api/environments": _environments(
                _env(
                    "Production",
                    [_user("ops"), {"type": "Team", "reviewer": {"slug": "sre"}}],
                    branch_policy=True,
                ),
                _env("copilot"),  # no reviewers, not production-like: ignored
            ),
            "orgs/acme/teams/sre/members": [{"login": "sre1"}, {"login": "sre-bot"}],
            "repos/acme/api/deployments": [
                _deployment("dev"),
                _deployment("dev", "2026-11-05T00:00:00Z"),
                _deployment("github-actions[bot]"),
            ],
            "repos/acme/api/collaborators": [{"login": "root"}],
        }
    )
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()

    deploy = _functions(result)["deploy-production"]
    assert deploy["name"] == "Deploy to Production" and deploy["criticality"] == 0.9
    assert deploy["requires"] == 2
    assert deploy["performers"] == ["dev", "ops", "root", "sre1"]
    assert deploy["alone"] == ["ops", "root", "sre1"]  # self-approval and admin bypass
    assert deploy["evidence"] == (
        "one of the required reviewers approves each deployment: ops, sre1; "
        "reviewers can approve their own deployments; "
        "admins can bypass the environment's protection rules; "
        "recent deployments by dev (2); deployments are limited to selected branches"
    )
    assert "deploy-copilot" not in _functions(result)
    people = {p["id"]: p for p in result.people}
    assert "approves deployments to Production" in people["ops"]["role"]
    assert people["dev"]["last_active"] == "2026-11-05"
    HumanRiskGraph(result.people, result.dependencies, result.functions)  # a valid draft


def test_deploy_two_person_rule_without_admin_bypass():
    routes = _routes(
        **{
            "repos/acme/api/environments": _environments(
                _env("staging", [_user("ops")], self_review=False, admins_bypass=False)
            ),
            "repos/acme/api/collaborators": [{"login": "root"}],
        }
    )
    deploy = _functions(GitHubScanner(FakeClient(routes), "acme/api").scan())["deploy-staging"]
    assert deploy["criticality"] == 0.7  # protected, but not production-like
    assert (deploy["requires"], deploy["performers"], deploy["alone"]) == (2, ["ops"], [])
    assert "reviewers cannot approve their own deployments" in deploy["evidence"]


def test_production_environment_without_reviewers():
    routes = _routes(
        **{
            "repos/acme/api/environments": _environments(_env("pypi"), _env("release")),
            "repos/acme/api/deployments": lambda params: (
                [_deployment("lead")] if params.get("environment") == "pypi" else []
            ),
        }
    )
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    deploy = _functions(result)["deploy-pypi"]
    assert (deploy["requires"], deploy["performers"], deploy["alone"]) == (1, ["lead"], [])
    assert deploy["evidence"].startswith("no required reviewers: whoever can run")
    assert "deploy-release" not in _functions(result)
    assert any("Environment release has no required reviewers" in n for n in result.notes)


def test_invisible_environments_are_a_gap():
    routes = _routes()
    del routes["repos/acme/api/environments"]
    result = GitHubScanner(FakeClient(routes), "acme/api").scan()
    assert "Deployment environments are not visible" in " ".join(result.gaps)


def _activity_routes(commits):
    return _routes(
        **REVIEW_RULE,
        **{
            "repos/acme/api/collaborators": [{"login": "root"}, {"login": "lead"}],
            "repos/acme/api/commits": commits,
        },
    )


def test_last_active_of_people_with_authority():
    def commits(params):
        return {
            "root": [{"commit": {"committer": {"date": "2025-01-02T00:00:00Z"}}}],
            "dev": [],
            "lead": [{"commit": {"author": {"date": "2026-03-04T00:00:00Z"}}}],
        }.get(params["author"])

    client = FakeClient(_activity_routes(commits))
    result = GitHubScanner(client, "acme/api").scan()
    people = {p["id"]: p for p in result.people}
    # Pull requests from 2026-01-01 are older than RECENT_DAYS, so commits are looked up.
    assert people["root"]["last_active"] == "2025-01-02"  # admin seen only in commits
    assert people["lead"]["last_active"] == "2026-03-04"  # the later of PRs and commits
    assert people["dev"]["last_active"] == "2026-01-01"  # PRs; no commits
    assert list(people["lead"])[:5] == ["id", "name", "role", "criticality", "last_active"]


def test_no_activity_seen_and_not_visible():
    client = FakeClient(_activity_routes(lambda params: [] if params["author"] == "root" else None))
    people = {p["id"]: p for p in GitHubScanner(client, "acme/api").scan().people}
    assert people["root"]["last_active"] == "never"
    assert people["lead"]["last_active"] == "2026-01-01"  # commits not visible: PRs only


def test_activity_is_not_recorded_on_request():
    client = FakeClient(_activity_routes(lambda params: []))
    result = GitHubScanner(client, "acme/api", record_activity=False).scan()
    assert all("last_active" not in p for p in result.people)
    assert "repos/acme/api/commits" not in client.requested


def test_activity_lookups_are_bounded(monkeypatch):
    from human_risk_graph import github_scan

    monkeypatch.setattr(github_scan, "MAX_ACTIVITY_LOOKUPS", 1)
    client = FakeClient(_activity_routes(lambda params: []))
    result = GitHubScanner(client, "acme/api").scan()
    assert client.requested.count("repos/acme/api/commits") == 1
    assert any("Last activity was looked up for 1 of" in gap for gap in result.gaps)


def test_merges_keep_the_latest_activity():
    def scan(repo, criticality, last_active):
        result = _scan(repo, [("x", criticality)], [])
        result.people[0]["last_active"] = last_active
        return result

    merged = merge_scans("acme", [scan("acme/a", 0.9, "never"), scan("acme/b", 0.5, "2026-02-01")])
    assert merged.people[0]["last_active"] == "2026-02-01"  # from the less critical copy

    again = scan("acme/a", 0.3, "2026-01-01")
    merge_with_existing(again, {"people": [{"id": "x", "last_active": "2026-05-01"}]})
    assert again.people[0]["last_active"] == "2026-05-01"


def test_cli_scan_no_activity(tmp_path, fake_github):
    fake_github(_activity_routes(lambda params: []))
    output = tmp_path / "draft.yaml"
    result = CliRunner().invoke(
        cli, ["scan", "github", "acme/api", "-o", str(output), "--no-activity"]
    )
    assert result.exit_code == 0, result.output
    assert "last_active" not in output.read_text()


# Organization scan


def _repo(name, pushed, **flags):
    return {"full_name": f"acme/{name}", "pushed_at": pushed, **flags}


def _org_routes(**extra):
    routes = _routes(
        **{
            "orgs/acme/repos": [
                _repo("api", "2026-10-01"),
                _repo("web", "2026-11-01"),
                _repo("old", "2026-11-05", archived=True),
                _repo("forked", "2026-11-06", fork=True),
            ],
            "repos/acme/api/releases": [_release("lead")],
            "repos/acme/web": {"default_branch": "main"},
            "repos/acme/web/environments": {"total_count": 0, "environments": []},
            "repos/acme/web/pulls": [_pr(10, "dev")],
            "repos/acme/web/pulls/10/reviews": [_review("lead")],
            "repos/acme/web/releases": [_release("lead"), _release("lead")],
        }
    )
    routes.update(extra)
    return routes


def test_list_repositories_filters_and_sorts():
    client = FakeClient(_org_routes())
    names, skipped = list_repositories(client, "acme")
    assert names == ["acme/web", "acme/api"]  # most recently pushed first
    assert skipped == {"archived": 1, "forks": 1}
    names, skipped = list_repositories(client, "acme", include_archived=True, include_forks=True)
    assert names == ["acme/forked", "acme/old", "acme/web", "acme/api"] and not skipped


def test_list_repositories_falls_back_to_a_user_account():
    client = FakeClient({"users/solo/repos": [_repo("tool", "2026-01-01")]})
    assert list_repositories(client, "solo")[0] == ["acme/tool"]
    with pytest.raises(GitHubError, match="not found"):
        list_repositories(FakeClient({}), "nobody")


def test_scan_organization_merges_repositories():
    result = scan_organization(FakeClient(_org_routes()), "acme", max_prs=10)
    assert result.repositories == ["acme/web", "acme/api"]
    assert [p["id"] for p in result.people].count("lead") == 1
    lead = next(p for p in result.people if p["id"] == "lead")
    assert "(in 2 repositories)" in lead["role"]
    assert lead["evidence"].startswith("web: ") and "; api: " in lead["evidence"]

    dep = _deps(result)[("lead", "dev")]
    assert dep["type"] == "approval" and dep["weight"] == 1.0  # web: 1 of 1 PR approved
    assert (
        dep["evidence"].startswith("web: approved 1 of 1") and "; api: approved" in dep["evidence"]
    )

    functions = {f["id"]: f for f in result.functions}
    assert {"web/release", "api/release", "web/merge", "api/merge"} <= set(functions)
    assert functions["web/release"]["name"] == "Publish a release (web)"
    assert functions["web/release"]["performers"] == ["lead"]
    assert result.notes == [
        "Scanned 2 of 2 repositories of acme, most recently pushed first; "
        "skipped 1 archived, 1 forks."
    ]
    assert result.coverage()["repositories"] == ["acme/web", "acme/api"]

    v3 = HumanRiskGraph(result.people, result.dependencies, result.functions).calculate(
        model="hrg-3"
    )
    lead_v3 = next(p for p in v3["key_people"] if p["id"] == "lead")
    assert {"web/release", "api/release"} <= set(lead_v3["functions"])  # sole releaser of both


def test_scan_organization_limits_and_reports_unscanned_repositories():
    result = scan_organization(FakeClient(_org_routes()), "acme", max_repos=1)
    assert result.repositories == ["acme/web"]
    assert "1 less recently pushed repositories were not scanned" in result.notes[1]


def test_scan_organization_keeps_going_when_a_repository_fails():
    routes = _org_routes()
    routes["orgs/acme/repos"].append(_repo("gone", "2026-12-01"))
    result = scan_organization(FakeClient(routes), "acme")
    assert result.repositories == ["acme/web", "acme/api"]
    assert result.gaps[-1].startswith("Could not scan acme/gone: Repository acme/gone not found")
    with pytest.raises(GitHubError, match="No repository of acme could be scanned"):
        scan_organization(FakeClient({"orgs/acme/repos": [_repo("gone", "x")]}), "acme")
    with pytest.raises(ValueError, match="organization or user name"):
        scan_organization(FakeClient({}), "acme/api")


def test_scan_organization_stops_on_rate_limit():
    class Limited(FakeClient):
        def get(self, path, params=None, limit=0):
            if path.startswith("repos/"):
                raise GitHubError("GitHub API rate limit reached")
            return super().get(path, params, limit)

    with pytest.raises(GitHubError, match="rate limit"):
        scan_organization(Limited(_org_routes()), "acme")


def _scan(repo, people, deps, functions=(), gaps=(), review_required=True):
    return ScanResult(
        repo=repo, branch="main", pull_requests=3, api_calls=5, notes=[],
        people=[{"id": p, "name": p, "role": "dev", "criticality": c, "evidence": f"{p} in {repo}"}
                for p, c in people],
        dependencies=[{"from": a, "to": b, "type": t, "weight": w, "source": s,
                       "evidence": f"{t} in {repo}", "confirmed": False}
                      for a, b, t, w, s in deps],
        functions=list(functions), gaps=list(gaps), review_required=review_required,
    )  # fmt: skip


def test_merge_scans_strongest_dependency_wins():
    a = _scan("acme/a", [("x", 0.4), ("y", 0.3)], [("x", "y", "approval", 0.9, "pr-reviews")])
    b = _scan(
        "acme/b",
        [("x", 0.8), ("y", 0.3)],
        [("x", "y", "bypass", 0.5, "branch-rules"), ("y", "x", "approval", 0.2, "codeowners")],
        gaps=["Admins are not visible"],
        review_required=False,
    )
    merged = merge_scans("acme", [a, b])
    deps = _deps(merged)
    assert deps[("x", "y")]["type"] == "bypass" and deps[("x", "y")]["weight"] == 0.5
    assert deps[("x", "y")]["source"] == "branch-rules+pr-reviews"
    assert deps[("x", "y")]["evidence"] == "a: approval in acme/a; b: bypass in acme/b"
    assert deps[("y", "x")]["type"] == "approval"
    assert next(p for p in merged.people if p["id"] == "x")["criticality"] == 0.8
    assert merged.review_required is None  # required in one repository, not in the other
    assert merged.gaps == ["b: Admins are not visible"]
    assert (merged.pull_requests, merged.branch) == (6, "default branch of each repository")


def test_merge_scans_limits_evidence():
    scans = [_scan(f"acme/r{i}", [("x", 0.5), ("y", 0.5)], [("x", "y", "approval", 0.5, "s")])
             for i in range(7)]  # fmt: skip
    evidence = _deps(merge_scans("acme", scans))[("x", "y")]["evidence"]
    assert evidence.count("approval in") == 5 and evidence.endswith("; and 2 more")


def test_cli_scan_org(tmp_path, fake_github, monkeypatch):
    fake_github(_org_routes())
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "github", "--org", "acme", "--max-prs", "5"])
    assert result.exit_code == 0, result.output
    draft = tmp_path / "acme-org.yaml"
    text = draft.read_text()
    assert text.startswith("# Draft generated by `hrg scan github --org acme`")
    assert "into 2 repositories" in text
    data = load_organization(draft)
    assert data["coverage"]["repositories"] == ["acme/web", "acme/api"]

    data["functions"][0]["criticality"] = 0.3  # a human decision the next scan keeps
    draft.write_text(yaml.safe_dump(data))
    again = runner.invoke(cli, ["scan", "github", "--org", "acme"])
    assert again.exit_code == 0, again.output
    assert load_organization(draft)["functions"][0]["criticality"] == 0.3

    analyzed = runner.invoke(
        cli, ["analyze", str(draft), "--model", "hrg-3", "--format", "json", "--no-visualize", "-q"]
    )
    assert analyzed.exit_code in (0, 3), analyzed.output


@pytest.mark.parametrize(
    "args, message",
    [
        (["acme/api", "--org", "acme"], "either REPO"),
        ([], "either REPO"),
        (["--org", "acme", "--branch", "dev"], "--branch applies to one repository"),
    ],
)
def test_cli_scan_org_usage(args, message, fake_github):
    fake_github(_org_routes())
    result = CliRunner().invoke(cli, ["scan", "github", *args])
    assert result.exit_code == 2 and message in result.output


# GitHub Enterprise Server


def test_cli_scan_uses_the_api_url(tmp_path, fake_github, monkeypatch):
    fake_github(_routes())
    out = tmp_path / "draft.yaml"
    ghes = "https://github.example.com/api/v3"
    result = CliRunner().invoke(
        cli, ["scan", "github", "acme/api", "-o", str(out), "--api-url", ghes]
    )
    assert result.exit_code == 0, result.output
    # In GitHub Actions, GITHUB_API_URL points at the server the workflow runs on.
    monkeypatch.setenv("GITHUB_API_URL", ghes + "/")
    CliRunner().invoke(cli, ["scan", "github", "acme/api", "-o", str(out)])
    assert fake_github.apis == [ghes, ghes + "/"]


def test_cli_scan_rejects_a_plain_http_api(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, "default_token", lambda api=None: None)
    result = CliRunner().invoke(
        cli, ["scan", "github", "acme/api", "-o", str(tmp_path / "d.yaml"), "--api-url",
              "http://github.example.com/api/v3"],
    )  # fmt: skip
    assert result.exit_code == 2 and "must use https" in result.output


def test_default_token_asks_gh_for_the_enterprise_host(monkeypatch):
    from human_risk_graph import github_scan

    calls = []
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(github_scan.shutil, "which", lambda name: "/usr/bin/gh")

    def run(command, **kwargs):
        calls.append(command)
        return type("Done", (), {"stdout": "t0ken\n"})()

    monkeypatch.setattr(github_scan.subprocess, "run", run)
    assert github_scan.default_token() == "t0ken"
    assert github_scan.default_token("https://github.example.com/api/v3") == "t0ken"
    assert calls == [
        ["gh", "auth", "token"],
        ["gh", "auth", "token", "--hostname", "github.example.com"],
    ]


def test_client_keeps_the_token_inside_an_enterprise_api(monkeypatch):
    calls = _flaky(monkeypatch, [{"ok": 1}])
    client = GitHubClient("t", api="https://github.example.com/api/v3")
    assert client.get("repos/acme/api") == {"ok": 1}
    assert calls == ["https://github.example.com/api/v3/repos/acme/api"]
    with pytest.raises(GitHubError, match="Refusing"):
        client._request("https://github.example.com/api/graphql")
