"""Tests for hrg scan github, using a fake API instead of the network."""

import base64
import json

import pytest
import yaml
from click.testing import CliRunner

from human_risk_graph import cli as cli_module
from human_risk_graph.cli import cli
from human_risk_graph.github_scan import (
    GitHubError,
    GitHubScanner,
    draft_yaml,
    merge_with_existing,
    owners_for,
    parse_codeowners,
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
        return self.routes.get(path)


def _codeowners(text):
    return {"content": base64.b64encode(text.encode()).decode()}


def _pr(number, author):
    return {"number": number, "user": {"login": author}, "merged_at": "2026-01-01T00:00:00Z"}


def _review(login, state="APPROVED"):
    return {"user": {"login": login}, "state": state}


def _routes(**extra):
    routes = {
        "repos/acme/api": {"default_branch": "main"},
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
    assert result.gaps == []
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


def test_merge_without_existing():
    result = GitHubScanner(FakeClient(_routes()), "acme/api").scan()
    assert merge_with_existing(result, None) == []


# CLI


@pytest.fixture
def fake_github(monkeypatch):
    def install(routes):
        monkeypatch.setattr(cli_module, "GitHubClient", lambda token: FakeClient(routes))
        monkeypatch.setattr(cli_module, "default_token", lambda: None)

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
    assert len(coverage["gaps"]) == 2

    analyzed = runner.invoke(
        cli, ["analyze", str(draft), "--format", "json", "--output", "out.json", "--no-visualize"]
    )
    assert analyzed.exit_code in (0, 3), analyzed.output
    output = " ".join(analyzed.output.split())
    assert "unconfirmed" in output
    assert "2 data gaps" in output

    report = json.loads((tmp_path / "out.json").read_text())
    total = report["metadata"]["dependencies_count"]
    assert report["metadata"]["unconfirmed_dependencies"] == total > 0
    assert report["metadata"]["coverage_gaps"] == coverage["gaps"]

    for fmt, name in (("html", "out.html"), ("markdown", "out.md")):
        runner.invoke(
            cli, ["analyze", str(draft), "--format", fmt, "--output", name, "--no-visualize"]
        )
        text = (tmp_path / name).read_text()
        assert f"{total} dependencies are unconfirmed" in text
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
