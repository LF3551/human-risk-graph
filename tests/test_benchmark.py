"""Tests for the governance parsers and metrics used by benchmark/run.py."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "benchmark_run", Path(__file__).resolve().parent.parent / "benchmark" / "run.py"
)
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


@pytest.mark.parametrize(
    "line, expected",
    [
        ("* Bryan Boreham (bjboreham@gmail.com / @bboreham)", {"bboreham"}),
        ("| Jim | [@JimBugwadia](https://github.com/JimBugwadia) | CLI |", {"jimbugwadia"}),
        ("Hidde Beydals <hidde@hhh.computer> (github: @hiddeco, slack: hidde)", {"hiddeco"}),
        ("- `@grafana/docs-logs`, see https://github.com/argoproj/argoproj/blob/x", set()),
        ("| Anders | @anderseknert | anders@eknert.com |", {"anderseknert"}),
    ],
)
def test_handles(line, expected):
    assert bench.handles(line) == expected


def test_handles_stop_at_emeritus():
    text = "# Maintainers\n@alice\n\n## Emeritus\n@bob\n"
    assert bench.handles(text) == {"alice"}
    assert bench.handles("@carol\nRetired maintainers:\n@dave\n") == {"carol"}


def test_owners_with_aliases():
    owners = "approvers:\n  - core  # alias\n  - Solo\nreviewers:\n  - rev\n"
    aliases = "aliases:\n  core:\n    - Ann\n    - bob\n  empty: []\n"
    assert bench.owners(owners, aliases, ["approvers"]) == {"ann", "bob", "solo"}
    assert bench.owners("approvers:\n  - empty\n", aliases, ["approvers"]) == set()
    assert bench.owners("maintainers:\n  - X\n", None, ["maintainers"]) == {"x"}


def test_evaluate():
    m = bench.evaluate({"ann", "bob", "cid"}, {"Ann": 6, "bob": 1, "eve": 3})
    assert (m["approvers"], m["matched"]) == (3, 2)
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["approvals_by_declared"] == pytest.approx(0.7)
    assert m["top_approver_declared"] is True
    assert m["undeclared_approvers"] == [["eve", 3]]
    assert m["inactive_declared"] == ["cid"]

    empty = bench.evaluate({"ann"}, {})
    assert (empty["precision"], empty["recall"], empty["top_approver_declared"]) == (None, 0, None)


def test_evaluate_releases():
    functions = [{"id": "release", "performers": ["Ann", "bot-free", "eve"]}]
    assert bench.evaluate_releases({"ann", "eve"}, functions) == {
        "release_authors": 3,
        "release_authors_declared": pytest.approx(2 / 3),
    }
    assert bench.evaluate_releases({"ann"}, []) == {
        "release_authors": 0,
        "release_authors_declared": None,
    }


def test_totals_and_markdown():
    repos = [
        {
            "repo": "a/b",
            "pull_requests": 10,
            "review_required": "yes",
            "approvals_given": {"ann": 6, "eve": 4},
            "metrics": bench.evaluate({"ann", "bob"}, {"ann": 6, "eve": 4}),
        },
        {"repo": "c/d", "error": "c/d:OWNERS not found"},
    ]
    totals = bench.totals(repos)
    assert totals["precision"] == pytest.approx(0.5)
    assert totals["approvals_by_declared"] == pytest.approx(0.6)
    run = {"date": "2026-11-13", "tool_version": "x", "max_prs": 10, "repos": repos}
    text = bench.markdown({**run, "totals": totals})
    assert "| a/b | 10 | 2 | 2 | 50% | 50% | 60% | yes | n/a | yes |" in text
    assert "1 approvers not declared (4 approvals); 1 declared approvers" in text
    assert "c/d**: error" in text
