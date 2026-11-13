"""Tests for the statistics and parsing in benchmark/validate.py (reference values: SciPy)."""

import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "benchmark_validate", Path(__file__).resolve().parent.parent / "benchmark" / "validate.py"
)
val = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(val)


@pytest.mark.parametrize(
    "info, expected",
    [
        ({"project_urls": {"Source": "https://github.com/psf/requests"}}, "psf/requests"),
        ({"project_urls": {"Homepage": "https://github.com/a/b.git", "Source": "https://github.com/c/d"}}, "c/d"),
        ({"project_urls": {"Funding": "https://github.com/sponsors/x", "Code": "https://gitlab.com/y/z"}}, None),
        ({"project_urls": None, "home_page": "http://github.com/Owner/Repo/tree/main"}, "Owner/Repo"),
        ({"project_urls": {"Changelog": "https://github.com/o/r/blob/main/CHANGES.md"}}, "o/r"),
    ],
)  # fmt: skip
def test_github_repo(info, expected):
    assert val.github_repo(info) == expected


def release(author, days_before_t0, draft=False):
    return {"author": author, "draft": draft, "published": val.T0 - timedelta(days=days_before_t0)}


def test_release_margin_uses_the_last_30_human_releases_in_the_window():
    releases = [release("old-maintainer", 400 + i) for i in range(5)]
    releases += [release("alice", 10 + i) for i in range(30)]
    releases += [release("bob", -5), release("carol", 1, draft=True), release("dependabot[bot]", 2)]
    # bob is after T0; old-maintainer is not in the last 30; the bot release is one of them
    assert val.release_margin(releases) == (1, 29, 1)


def test_release_margin_ignores_people_who_released_before_the_window():
    releases = [release("alice", 10), release("alice", 20), release("gone", 800)]
    assert val.release_margin(releases) == (1, 2, 0)


def test_truck_factor():
    assert val.truck_factor(["a"] * 6 + ["b"] * 4) == 1
    assert val.truck_factor(["a"] * 5 + ["b"] * 5) == 2  # exactly half is not more than half
    assert val.truck_factor(["a", "b", "c", "renovate[bot]", None]) == 2
    assert val.truck_factor([None, "github-actions[bot]"]) is None


def test_outcomes():
    t0 = val.T0
    assert val.outcomes([t0 - timedelta(days=1)]) == {
        "first_release_after_t0": "",
        "stall": True,
        "long_gap": True,
    }
    late = val.outcomes([t0 + timedelta(days=200), t0 + timedelta(days=400)])
    assert (late["stall"], late["long_gap"]) == (False, True)
    soon = val.outcomes([t0, t0 + timedelta(days=500)])
    assert (soon["stall"], soon["long_gap"], soon["first_release_after_t0"]) == (
        False,
        False,
        t0.date().isoformat(),
    )


def test_risk_ratio_matches_scipy():
    r = val.risk_ratio(12, 50, 9, 150)
    assert r["rr"] == pytest.approx(4.0)
    assert (r["low"], r["high"]) == (pytest.approx(1.79226, 1e-4), pytest.approx(8.92726, 1e-4))


def test_risk_ratio_zero_cell_and_empty_group():
    assert val.risk_ratio(0, 10, 5, 10)["rr"] == pytest.approx((0.5 / 11) / (5.5 / 11))
    assert val.risk_ratio(1, 0, 1, 5)["rr"] is None


@pytest.mark.parametrize(
    "table, p",
    [((3, 1, 1, 3), 0.485714), ((12, 38, 9, 141), 0.000885451), ((0, 10, 5, 5), 0.0325077)],
)
def test_fisher_exact_matches_scipy(table, p):
    assert val.fisher_exact(*table) == pytest.approx(p, rel=1e-4)


def test_mantel_haenszel():
    crude = val.risk_ratio(12, 50, 9, 150)["rr"]
    assert val.mantel_haenszel([(12, 50, 9, 150)])["rr"] == pytest.approx(crude)
    assert val.mantel_haenszel([(6, 25, 3, 75), (6, 25, 6, 75)])["rr"] == pytest.approx(
        (6 * 75 / 100 + 6 * 75 / 100) / (3 * 25 / 100 + 6 * 25 / 100)
    )
    pooled = val.mantel_haenszel([(10, 20, 5, 40), (4, 10, 2, 30)])
    assert pooled["rr"] == pytest.approx(4.4615, rel=1e-4)
    assert pooled["low"] < pooled["rr"] < pooled["high"]
    assert val.mantel_haenszel([(0, 5, 0, 5)])["rr"] is None


def test_terciles():
    assert val.terciles([1, 2, 3, 4, 5, 6]) == [0, 0, 1, 1, 2, 2]
    assert val.terciles([5, 5, 5]) == [2, 2, 2]


def test_analyze():
    def row(margin, tf, releases, stall):
        return {
            "status": "included",
            "release_margin": margin,
            "truck_factor": tf,
            "releases_in_window": releases,
            "stall": stall,
            "long_gap": stall,
        }

    rows = [row(1, 1, 3, True), row(1, 2, 4, True), row(1, 2, 20, False), row(2, 3, 5, False)]
    rows += [row(3, 2, 30, False), row(2, None, 6, True), {"status": "excluded: duplicate"}]
    out = val.analyze(rows)
    h1 = out["stall"]["h1_single_releaser"]
    assert out["n"] == 6
    assert (h1["exposed"], h1["unexposed"]) == ({"n": 3, "events": 2}, {"n": 3, "events": 1})
    assert h1["rr"] == pytest.approx(2.0)
    assert out["stall"]["baseline_truck_factor_1"]["exposed"] == {"n": 1, "events": 1}
    added = out["stall"]["single_releaser_when_truck_factor_2_plus"]
    assert (added["exposed"]["n"], added["unexposed"]["n"]) == (2, 2)
    assert len(out["long_gap"]["h2_stratified_by_release_count"]["strata"]) == 3
