"""Model hrg-3: critical functions and the two-person rule."""

import random
from pathlib import Path

import pytest

from human_risk_graph import HumanRiskGraph
from human_risk_graph.findings import collect_findings
from human_risk_graph.loader import load_organization
from human_risk_graph.model_v3 import describe

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "functions.yaml"


def calc(people, functions, **kwargs):
    return HumanRiskGraph(people, [], functions).calculate(model="hrg-3", **kwargs)


def people(*ids):
    return [{"id": i} for i in ids]


def fn(fid="f", criticality=0.9, requires=1, performers=(), alone=()):
    return {
        "id": fid,
        "criticality": criticality,
        "requires": requires,
        "performers": list(performers),
        "alone": list(alone),
    }


# Reference scenarios with known answers


def test_one_person_does_it_alone():
    r = calc(people("a"), [fn(performers=["a"])])
    assert (r["bus_factor"], r["decision_concentration"], r["bypass_risk"]) == (1, 1, 1)
    assert (r["score"], r["grade"], r["bus_factor_people"]) == (0, "F", 1)
    assert r["key_people"][0]["functions"] == ["f"]


def test_two_performers_without_two_person_rule():
    r = calc(people("a", "b"), [fn(performers=["a", "b"])])
    assert r["bus_factor"] == 0  # either can stand in
    assert r["decision_concentration"] == pytest.approx(0.5)
    assert r["bypass_risk"] == 1  # but each can act alone
    assert r["functions"][0]["margin"] == 2


def test_two_person_rule_with_exactly_two_people():
    r = calc(people("a", "b"), [fn(requires=2, performers=["a", "b"])])
    assert r["bus_factor"] == 1  # losing either stops it
    assert r["bypass_risk"] == 0
    assert r["functions"][0]["single_points"] == ["a", "b"]


def test_two_person_rule_with_spare_people():
    r = calc(people("a", "b", "c"), [fn(requires=2, performers=["a", "b", "c"])])
    assert (r["bus_factor"], r["bypass_risk"]) == (0, 0)
    assert r["decision_concentration"] == pytest.approx(1 / 3)
    # Only concentration is left: R = 0.3 * (1/3) / (1 - 0.6 * 0.7 * 0.7)
    assert r["score"] == round(100 * (1 - 0.1 / (1 - 0.6 * 0.7 * 0.7)))


def test_someone_can_bypass_the_two_person_rule():
    r = calc(people("a", "b", "c"), [fn(requires=2, performers=["a", "b", "c"], alone=["a"])])
    assert r["bypass_risk"] == 1
    assert r["solo_functions"] == ["f"]
    assert r["functions"][0]["alone"] == ["a"]


def test_alone_keeps_a_function_possible():
    # A sole maintainer who can bypass review: the function works, but only through them.
    r = calc(people("a"), [fn(requires=2, performers=["a"], alone=["a"])])
    f = r["functions"][0]
    assert (f["margin"], f["single_points"]) == (1, ["a"])
    assert r["uncovered_functions"] == []


def test_function_that_cannot_be_performed():
    r = calc(people("a", "b"), [fn("x", 0.5, 2, ["a"]), fn("y", 0.5, 1, ["a", "b"])])
    assert r["uncovered_functions"] == ["x"]
    assert r["bus_factor"] == pytest.approx(0.5)  # x is lost for everyone
    assert r["key_people"] == []


def test_non_critical_functions_do_not_count_for_solo_control():
    r = calc(people("a", "b"), [fn(criticality=0.3, performers=["a", "b"])])
    assert r["bypass_risk"] == 0
    assert r["critical_approvals"] == 0


def test_sub_scores():
    r = calc(people("a", "b"), [fn(performers=["a", "b"])])
    assert r["scores"]["integrity"] == 0
    assert r["scores"]["availability"] > r["score"]


# Separation policy: routine single-person operations are not solo control


def by_policy(f):
    return {**f, "separation": "not-required"}


def test_routine_single_person_operation_is_not_solo_control():
    restore = by_policy(fn("restore", performers=["a", "b"]))
    r = calc(people("a", "b"), [restore])
    assert r["bypass_risk"] == 0 and r["solo_functions"] == []
    assert r["scores"]["integrity"] == 100
    assert r["functions"][0]["separation"] == "not-required"
    assert r["functions"][0]["alone"] == ["a", "b"]  # still reported, just not a risk


def test_policy_does_not_hide_availability_risk():
    hrg = HumanRiskGraph(people("a"), [], [by_policy(fn("restore", performers=["a"]))])
    r = hrg.calculate(model="hrg-3")
    assert r["bus_factor"] == 1  # one person can still stop it
    assert [f.key for f in collect_findings(hrg, r)] == ["HRG005:restore"]
    assert all(p["action"] == "backup" for p in hrg.fix_plan(model="hrg-3"))


def test_policy_functions_neither_dilute_nor_raise_solo_control():
    merge = fn("merge", 0.8, 2, ["a", "b", "c"], alone=["a"])
    base = calc(people("a", "b", "c"), [merge])
    mixed = calc(people("a", "b", "c"), [merge, by_policy(fn("restore", performers=["b"]))])
    assert base["bypass_risk"] == mixed["bypass_risk"] == 1
    assert mixed["solo_functions"] == ["merge"]


def test_policy_does_not_excuse_a_bypass_of_a_required_two_person_rule():
    r = calc(people("a", "b"), [fn(requires=2, performers=["a", "b"], alone=["a"])])
    assert r["bypass_risk"] == 1


def test_low_criticality_single_person_operation_is_not_solo_control():
    r = calc(people("a"), [fn(criticality=0.4, performers=["a"])])
    assert r["bypass_risk"] == 0


def test_all_critical_functions_solo_by_policy():
    r = calc(people("a"), [by_policy(fn(performers=["a"]))])
    assert r["bypass_risk"] == 0
    assert describe(r, str)[2][0] == "Solo by policy"


def test_example_file():
    data = load_organization(EXAMPLE)
    hrg = HumanRiskGraph(data["people"], data["dependencies"], data["functions"])
    r = hrg.calculate(model="hrg-3")
    assert r["solo_functions"] == ["merge", "release"]  # restore-db is solo by policy
    assert r["key_people"][0]["id"] == "bob"
    keys = [f.key for f in collect_findings(hrg, r)]
    assert keys == [
        "HRG005:restore-db",
        "HRG005:rotate-keys",
        "HRG002:bob",
        "HRG006:merge",
        "HRG006:release",
        "HRG007:merge",  # dan: last_active never
    ]
    plan = hrg.fix_plan(model="hrg-3")
    assert [p["action"] for p in plan] == ["two-person", "backup", "backup"]
    assert all(p["score_after"] > p["score_before"] for p in plan)


# Validation


@pytest.mark.parametrize(
    "functions, message",
    [
        ([{"id": "f", "performers": ["zed"]}], "unknown person id 'zed'"),
        ([{"id": "f"}, {"id": "f"}], "duplicate function id"),
        ([{"id": "f", "requires": 0}], "requires must be a whole number"),
        ([{"id": "f", "requires": True}], "requires must be a whole number"),
        ([{"id": "f", "criticality": 2}], "criticality must be a number between 0 and 1"),
        ([{"id": "f", "separation": "optional"}], "separation must be one of"),
        ([{"performers": ["a"]}], "non-empty string 'id'"),
        ({"id": "f"}, "'functions' must be a list"),
    ],
)
def test_validation(functions, message):
    with pytest.raises(ValueError, match=message):
        HumanRiskGraph(people("a"), [], functions)


def test_hrg3_needs_functions():
    with pytest.raises(ValueError, match="needs a 'functions' section"):
        HumanRiskGraph(people("a"), []).calculate(model="hrg-3")


# Properties over random organizations


def random_case(seed):
    rng = random.Random(seed)
    ids = [f"p{i}" for i in range(rng.randint(2, 7))]
    functions = []
    for j in range(rng.randint(1, 5)):
        performers = rng.sample(ids, rng.randint(0, len(ids)))
        functions.append(
            fn(
                f"f{j}",
                round(rng.uniform(0.1, 1.0), 2),
                rng.randint(1, 3),
                performers,
                rng.sample(performers, rng.randint(0, min(1, len(performers)))),
            )
        )
    return people(*ids), functions


CASES = [random_case(seed) for seed in range(40)]


@pytest.mark.parametrize("ppl, functions", CASES)
def test_metrics_in_unit_interval(ppl, functions):
    r = calc(ppl, functions)
    for key in ("bus_factor", "decision_concentration", "bypass_risk", "composite_score"):
        assert 0 <= r[key] <= 1 + 1e-12
    assert 0 <= r["score"] <= 100


@pytest.mark.parametrize("ppl, functions", CASES)
def test_more_performers_never_raise_function_loss(ppl, functions):
    before = calc(ppl, functions)["bus_factor"]
    extra = ppl + [{"id": "new"}]
    grown = [{**f, "performers": f["performers"] + ["new"]} for f in functions]
    assert calc(extra, grown)["bus_factor"] <= before + 1e-12


@pytest.mark.parametrize("ppl, functions", CASES)
def test_closing_solo_paths_never_raises_solo_control(ppl, functions):
    before = calc(ppl, functions)["bypass_risk"]
    closed = [{**f, "alone": []} for f in functions]
    assert calc(ppl, closed)["bypass_risk"] <= before + 1e-12


@pytest.mark.parametrize("ppl, functions", CASES)
def test_stricter_requirement_never_lowers_function_loss(ppl, functions):
    before = calc(ppl, functions)["bus_factor"]
    stricter = [{**f, "requires": f["requires"] + 1} for f in functions]
    assert calc(ppl, stricter)["bus_factor"] >= before - 1e-12


@pytest.mark.parametrize("ppl, functions", CASES[:15])
def test_fix_plan_only_improves(ppl, functions):
    plan = HumanRiskGraph(ppl, [], functions).fix_plan(model="hrg-3")
    risks = [plan[0]["risk_before"]] + [p["risk_after"] for p in plan] if plan else []
    assert risks == sorted(risks, reverse=True)


@pytest.mark.parametrize("ppl, functions", CASES[:10])
def test_relabelling_people_does_not_change_the_score(ppl, functions):
    rename = {p["id"]: f"x{i}" for i, p in enumerate(reversed(ppl))}
    renamed = [
        {
            **f,
            "performers": [rename[p] for p in f["performers"]],
            "alone": [rename[p] for p in f["alone"]],
        }
        for f in functions
    ]
    assert (
        calc([{"id": rename[p["id"]]} for p in ppl], renamed)["score"]
        == calc(ppl, functions)["score"]
    )


@pytest.mark.parametrize("ppl, functions", CASES[:20])
def test_adding_a_policy_function_never_changes_solo_control(ppl, functions):
    extra = by_policy(fn("routine", 0.95, 1, [ppl[0]["id"]]))
    assert calc(ppl, functions + [extra])["bypass_risk"] == pytest.approx(
        calc(ppl, functions)["bypass_risk"]
    )
