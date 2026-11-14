"""Tests for benchmark/two_person_review.py: measurement checklist, scoring and disclosure."""

import base64
import csv
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BENCHMARK = Path(__file__).resolve().parent.parent / "benchmark"
sys.path.insert(0, str(BENCHMARK))
SPEC = importlib.util.spec_from_file_location(
    "two_person_review", BENCHMARK / "two_person_review.py"
)
rv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rv)
tp = rv.tp

T0 = datetime.combine(rv.T0, datetime.min.time(), tzinfo=timezone.utc)


def _iso(days_before: int) -> str:
    return (T0 - timedelta(days=days_before)).isoformat().replace("+00:00", "Z")


def _b64(text: str) -> dict:
    return {"content": base64.b64encode(text.encode()).decode()}


class FakeClient:
    def __init__(self, routes):
        self.routes, self.calls, self.requested = routes, 0, []

    def get(self, path, params=None, limit=0):
        self.calls += 1
        self.requested.append(path)
        value = self.routes.get(path)
        return value(params or {}) if callable(value) else value


WORKFLOW = """name: release
on: {release: {types: [published]}}
jobs:
  publish:
    environment: pypi
    steps:
      - uses: pypa/gh-action-pypi-publish@release/v1
"""


def _routes(**extra):
    reviewers = [{"type": "User", "reviewer": {"login": u}} for u in ("old", "lead")]
    routes = {
        "repos/acme/lib": {"full_name": "acme/lib", "default_branch": "main",
                           "owner": {"type": "Organization"}},
        "repos/acme/lib/environments": {"environments": [
            {"name": "pypi", "can_admins_bypass": True, "protection_rules": [
                {"type": "required_reviewers", "prevent_self_review": False,
                 "reviewers": reviewers}]}]},
        "repos/acme/lib/deployments": [{"creator": {"login": "lead"}, "created_at": _iso(3)}],
        "repos/acme/lib/releases": [{"author": {"login": "lead"}, "published_at": _iso(3)}],
        "repos/acme/lib/rules/branches/main": [],
        "repos/acme/lib/pulls": [{"number": 1, "merged_at": _iso(5), "user": {"login": "dev"}}],
        "repos/acme/lib/pulls/1/reviews": [
            {"user": {"login": "lead"}, "state": "APPROVED", "submitted_at": _iso(5)}],
        "repos/acme/lib/commits": lambda params: (
            [{"commit": {"committer": {"date": _iso(120)}}}] if params["author"] == "old" else []
        ),
        "repos/acme/lib/contents/.github/workflows": [
            {"name": "release.yml"}, {"name": "tests.yml"}, {"name": "README.md"}],
        "repos/acme/lib/contents/.github/workflows/release.yml": _b64(WORKFLOW),
        "repos/acme/lib/contents/.github/workflows/tests.yml": _b64("jobs:\n  t:\n    environment: ci\n"),
    }  # fmt: skip
    routes.update(extra)
    return routes


@pytest.fixture
def collected(tmp_path, monkeypatch):
    """The cache and private rows as the collection leaves them, for one project."""
    publisher = {"kind": "GitHub", "repository": "acme/lib", "workflow": "release.yml",
                 "environment": "pypi"}  # fmt: skip

    def get_json(url, accept="application/json"):
        if url.endswith("/acme-lib/json"):
            return {
                "releases": {
                    "1.0": [{"filename": "acme_lib-1.0.tar.gz", "upload_time_iso_8601": _iso(3)}]
                }
            }
        if "/integrity/acme-lib/1.0/acme_lib-1.0.tar.gz/" in url:
            return {"attestation_bundles": [{"publisher": publisher}]}
        return None  # fmt: skip

    monkeypatch.setattr(tp, "_get_json", get_json)
    cache = tp.Cache(tmp_path / "cache")
    row = tp.collect_repo(FakeClient(_routes()), cache, "acme/lib", T0, "acme-lib")
    private = tmp_path / "private"
    private.mkdir()
    with open(private / "two-person-rows.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, tp.COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerow({"rank": 7, "package": "acme-lib", **row})
        writer.writerow(
            {"rank": 9, "package": "gone", "repo": "x/y", "status": "excluded: archived"}
        )
    (private / "measurement-check.txt").write_text("acme/lib\n")
    return cache, private, row


def test_publish_lines():
    assert rv.publish_lines(WORKFLOW) == [
        (5, "environment: pypi"),
        (7, "- uses: pypa/gh-action-pypi-publish@release/v1"),
    ]
    assert rv.publish_lines("jobs:\n  t:\n    environment: ci\n") == []  # no publishing step
    block = "    environment:\n      name: pypi\n      url: x\n    steps:\n      - run: twine upload dist/*\n"
    assert rv.publish_lines(block) == [
        (1, "environment:"),
        (2, "name: pypi"),
        (5, "- run: twine upload dist/*"),
    ]
    assert rv.publish_lines("run: uv publish --trusted-publishing always") == [
        (1, "run: uv publish --trusted-publishing always")
    ]


def test_measurement_checklist(collected):
    cache, private, row = collected
    assert row["dormant_solo_90"]  # the fixture project is one with dormant solo authority
    client = FakeClient(_routes())
    out = rv.measurement(client, cache, private)
    text = out.read_text()
    assert "## acme/lib (package acme-lib, rank 7)" in text
    assert "path **V1**" in text and "configured gate **G1**" in text
    assert "`pypi`: publishing True, gated True, 2 user + 0 team reviewer(s)" in text
    assert "`.github/workflows/release.yml`" in text and "tests.yml" not in text
    assert "line 7: `- uses: pypa/gh-action-pypi-publish@release/v1`" in text
    assert "`acme_lib-1.0.tar.gz`: GitHub acme/lib release.yml environment `pypi`" in text
    assert text.count("- [ ] ") == 3
    # Collection data come from the cache: only the workflow files are fetched.
    assert all("workflows" in path for path in client.requested)


def test_score():
    filled = (
        "## a/b (package b, rank 1)\n- [x] path: V1\n- [x] gate: G1\n- [-] reviewers: 1\n"
        "## c/d (package d, rank 2)\n- [x] path: U\n- [x] gate: NE\n- [x] reviewers: 0\n"
    )
    result = rv.score(filled)
    assert result["projects"] == 2
    assert (result["path"]["k"], result["reviewers"]["k"], result["all_three"]["k"]) == (2, 1, 1)
    with pytest.raises(ValueError, match="not marked yet: c/d gate"):
        rv.score(filled.replace("- [x] gate: NE", "- [ ] gate: NE"))


def test_dormant_solo_details_from_the_cache(collected):
    cache, _, _ = collected
    client = FakeClient({})  # everything must come from the cache
    details = rv.dormant_solo_details(client, cache, "acme/lib")
    assert details == [{"environment": "pypi", "reviewer": "old", "last_seen": _iso(120)[:10]}]
    assert client.calls == 0


@pytest.mark.parametrize(
    "routes, kind, target",
    [
        ({"repos/acme/lib/private-vulnerability-reporting": {"enabled": True}},
         "private vulnerability reporting", "https://github.com/acme/lib/security/advisories/new"),
        ({"repos/acme/lib/private-vulnerability-reporting": {"enabled": False},
          "repos/acme/lib/contents/SECURITY.md": _b64("Mail security@acme.dev or security@acme.dev.")},
         "security policy", "security@acme.dev"),
        ({"repos/acme/.github/contents/SECURITY.md": _b64("Report at https://acme.dev/security.")},
         "security policy", "https://acme.dev/security"),
        ({}, "none", ""),
    ],
)  # fmt: skip
def test_channel(tmp_path, routes, kind, target):
    found = rv.channel(FakeClient(routes), tp.Cache(tmp_path), "acme/lib")
    assert (found["kind"], found["target"]) == (kind, target)


def test_disclosure(collected, tmp_path):
    cache, private, _ = collected
    routes = {"repos/acme/lib/private-vulnerability-reporting": {"enabled": True}}
    out = rv.disclosure(FakeClient(routes), cache, private, "2026-12-20", "Aleksei Aleinikov")
    text = out.read_text()
    assert "1 projects with dormant solo authority" in text
    assert "Subject: A dormant reviewer can approve releases of acme/lib alone" in text
    assert "environment `pypi`" in text and "@old had no activity" in text
    assert "no earlier than 2026-12-20" in text and "@lead" not in text
    log = list(csv.DictReader(open(private / "disclosure-log.csv")))
    assert log == [{"repo": "acme/lib", "package": "acme-lib",
                    "channel": "private vulnerability reporting",
                    "target": "https://github.com/acme/lib/security/advisories/new",
                    "sent_on": ""}]  # fmt: skip


def test_projects_without_a_private_channel_are_not_contacted(collected):
    cache, private, _ = collected
    text = rv.disclosure(FakeClient({}), cache, private, "2026-12-20", "A").read_text()
    assert "Not contacted: no private channel" in text and "Subject:" not in text


def test_security_contacts():
    text = "Write to a@b.org (or a@b.org) and see https://x.org/sec. Also https://x.org/sec"
    assert rv.security_contacts(text) == ["a@b.org", "https://x.org/sec"]
