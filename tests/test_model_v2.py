"""Model hrg-2: reference structures and properties that must hold for any organization."""

import json
import random
from pathlib import Path

import pytest

from human_risk_graph import HumanRiskGraph
from human_risk_graph.fixes import _with_controlled_bypass, _with_deputy
from human_risk_graph.model_v2 import composite_risk, score_and_grade

EXAMPLE = Path(__file__).resolve().parent.parent / "data" / "example_organization.json"
WEIGHTS = (0.4, 0.3, 0.3)


def calc(people, deps, **kwargs):
    return HumanRiskGraph(people, deps).calculate(**kwargs)


def star(n, hub_criticality=0.9, edge_type="escalation"):
    people = [{"id": "hub", "criticality": hub_criticality}] + [
        {"id": f"p{i}", "criticality": 0.3} for i in range(1, n)
    ]
    deps = [{"from": "hub", "to": f"p{i}", "type": edge_type, "weight": 1.0} for i in range(1, n)]
    return people, deps


def random_org(rng, n=12, m=22):
    people = [{"id": f"p{i}", "criticality": round(rng.random(), 2)} for i in range(n)]
    edges = set()
    while len(edges) < m:
        a, b = rng.sample(range(n), 2)
        edges.add((a, b))
    deps = [
        {
            "from": f"p{a}",
            "to": f"p{b}",
            "type": rng.choice(["approval", "approval", "escalation", "bypass"]),
            "weight": round(rng.uniform(0.1, 1.0), 2),
        }
        for a, b in sorted(edges)
    ]
    return people, deps


ORGS = [random_org(random.Random(seed)) for seed in range(40)]


# Reference structures


def test_example_organization():
    data = json.loads(EXAMPLE.read_text())
    r = calc(data["people"], data["dependencies"])

    assert r["model"] == "hrg-2"
    assert (round(r["bus_factor"], 3), round(r["decision_concentration"], 3)) == (0.425, 0.287)
    assert round(r["bypass_risk"], 3) == 0.416
    assert (r["score"], r["grade"], r["risk_level"]) == (52, "D", "Moderate")
    assert r["bus_factor_people"] == 1
    assert r["key_people"][0]["id"] == "anna.mueller"
    assert r["key_people"][0]["cut_off"] == 3
    assert (len(r["overridable_approvals"]), r["critical_approvals"]) == (4, 7)


def test_original_model_is_reproducible():
    data = json.loads(EXAMPLE.read_text())
    r = calc(data["people"], data["dependencies"], model="hrg-1")
    assert r["model"] == "hrg-1"
    assert round(r["composite_score"], 3) == 0.269


@pytest.mark.parametrize("n", [5, 10, 100])
def test_star_risk_does_not_shrink_with_size(n):
    r = calc(*star(n))
    assert r["bus_factor"] == pytest.approx(0.9)
    assert r["key_people"][0]["impact"] == pytest.approx(1.0)
    assert r["key_people"][0]["cut_off"] == n - 2
    assert r["bus_factor_people"] == 1


def test_single_approver_is_maximal_concentration():
    r = calc(*star(10, edge_type="approval"))
    assert r["decision_concentration"] == pytest.approx(1.0)
    assert r["effective_approvers"] == pytest.approx(1.0)
    assert r["grade"] == "F"


@pytest.mark.parametrize("approvers", [2, 4, 8])
def test_equal_approvers(approvers):
    people = [{"id": f"a{i}"} for i in range(approvers)] + [{"id": "t"}]
    deps = [
        {"from": f"a{i}", "to": "t", "type": "approval", "weight": 0.5} for i in range(approvers)
    ]
    r = calc(people, deps)
    assert r["decision_concentration"] == pytest.approx(1 / approvers)
    assert r["effective_approvers"] == pytest.approx(approvers)


def test_complete_team_has_no_key_person():
    people = [{"id": f"p{i}", "criticality": 0.9} for i in range(6)]
    deps = [
        {"from": f"p{a}", "to": f"p{b}", "type": "escalation"}
        for a in range(6)
        for b in range(a + 1, 6)
    ]
    r = calc(people, deps)
    assert r["bus_factor"] == 0
    assert r["key_people"] == []
    assert r["bus_factor_people"] == 5


def test_chain_middle_person_holds_everything():
    people = [{"id": x, "criticality": 1.0} for x in "abc"]
    deps = [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]
    r = calc(people, deps)
    assert [(p["id"], p["impact"], p["cut_off"]) for p in r["key_people"]] == [("b", 1.0, 1)]


def test_override_exposure():
    people = [{"id": "boss", "criticality": 0.9}, {"id": "dev"}, {"id": "ops"}]
    approval = [{"from": "boss", "to": "dev", "type": "approval", "weight": 1.0}]

    assert calc(people, approval)["bypass_risk"] == 0
    overrides_boss = approval + [{"from": "ops", "to": "boss", "type": "bypass"}]
    assert calc(people, overrides_boss)["bypass_risk"] == pytest.approx(1.0)
    overrides_dev = approval + [{"from": "ops", "to": "dev", "type": "bypass"}]
    assert calc(people, overrides_dev)["bypass_risk"] == 0


def test_break_glass_bypass_counts_half():
    people = [{"id": "boss", "criticality": 0.9}, {"id": "dev"}, {"id": "ops"}, {"id": "sre"}]
    approval = [{"from": "boss", "to": "dev", "type": "approval", "weight": 1.0}]
    glass = {"from": "ops", "to": "boss", "type": "bypass", "review": "after"}

    r = calc(people, approval + [glass])
    assert r["bypass_risk"] == pytest.approx(0.5)
    assert r["break_glass_approvals"] == [["boss", "dev"]]
    # One unreviewed way around the approver is enough for a full override.
    r = calc(people, approval + [glass, {"from": "sre", "to": "boss", "type": "bypass"}])
    assert r["bypass_risk"] == pytest.approx(1.0)
    assert r["break_glass_approvals"] == []


def test_review_value_is_validated():
    with pytest.raises(ValueError, match="review must be one of none, after"):
        calc([{"id": "a"}, {"id": "b"}], [{"from": "a", "to": "b", "review": "later"}])


def test_empty_and_edgeless_organizations():
    r = calc([{"id": "solo"}], [])
    assert (r["score"], r["grade"], r["bus_factor_people"]) == (100, "A", None)


def test_unknown_model_is_rejected():
    with pytest.raises(ValueError, match="Unknown model"):
        calc([{"id": "a"}], [], model="hrg-9")


# Composite


def test_composite_bounds_and_dominance():
    assert composite_risk((0, 0, 0), WEIGHTS) == 0
    assert composite_risk((1, 1, 1), WEIGHTS) == pytest.approx(1)
    # One maxed-out metric weighs more than its linear share.
    assert composite_risk((1, 0, 0), WEIGHTS) > 0.4
    assert composite_risk((0, 1, 0), WEIGHTS) > 0.3


def test_composite_is_monotone_in_every_metric():
    grid = [i / 10 for i in range(11)]
    for i in range(3):
        for base in ((0.2, 0.5, 0.1), (0.9, 0.0, 0.4)):
            values = []
            for x in grid:
                metrics = list(base)
                metrics[i] = x
                values.append(composite_risk(tuple(metrics), WEIGHTS))
            assert values == sorted(values)


@pytest.mark.parametrize(
    "score, grade", [(100, "A"), (90, "A"), (89, "B"), (80, "B"), (70, "C"), (50, "D"), (49, "F")]
)
def test_grades(score, grade):
    assert score_and_grade(1 - score / 100)[1] == grade


# Properties over random organizations


@pytest.mark.parametrize("people, deps", ORGS)
def test_metrics_in_unit_interval(people, deps):
    r = calc(people, deps)
    for key in ("bus_factor", "decision_concentration", "bypass_risk", "composite_score"):
        assert 0 <= r[key] <= 1 + 1e-12
    assert 0 <= r["score"] <= 100


@pytest.mark.parametrize("people, deps", ORGS)
def test_key_person_risk_grows_with_criticality(people, deps):
    before = calc(people, deps)["bus_factor"]
    raised = [{**p, "criticality": min(1.0, p["criticality"] + 0.3)} for p in people]
    assert calc(raised, deps)["bus_factor"] >= before - 1e-12


@pytest.mark.parametrize("people, deps", ORGS)
def test_new_bypass_never_lowers_override_exposure(people, deps):
    before = calc(people, deps)["bypass_risk"]
    linked = {(d["from"], d["to"]) for d in deps}
    ids = [p["id"] for p in people]
    extra = next((a, b) for a in ids for b in ids if a != b and (a, b) not in linked)
    after = calc(people, deps + [{"from": extra[0], "to": extra[1], "type": "bypass"}])
    assert after["bypass_risk"] >= before - 1e-12


@pytest.mark.parametrize("people, deps", ORGS)
def test_new_bypass_never_improves_the_score(people, deps):
    # Adversarial: an override must not make the organization look less dependent on anyone.
    before = calc(people, deps)
    linked = {(d["from"], d["to"]) for d in deps}
    ids = [p["id"] for p in people]
    for a, b in [(a, b) for a in ids for b in ids if a != b and (a, b) not in linked][:15]:
        after = calc(people, deps + [{"from": a, "to": b, "type": "bypass", "weight": 1.0}])
        assert after["composite_score"] >= before["composite_score"] - 1e-12
        assert after["bus_factor"] == pytest.approx(before["bus_factor"])
        assert after["bus_factor_people"] == before["bus_factor_people"]


@pytest.mark.parametrize("people, deps", ORGS)
def test_reviewing_a_bypass_never_raises_risk(people, deps):
    risk = calc(people, deps)["composite_score"]
    for dep in deps:
        if dep["type"] == "bypass":
            reviewed = [{**d, "review": "after"} if d is dep else d for d in deps]
            assert calc(people, reviewed)["composite_score"] <= risk + 1e-12


def test_bypass_does_not_relieve_a_key_person():
    people = [{"id": i, "criticality": c} for i, c in [("lead", 0.9), ("a", 0.8), ("b", 0.8)]]
    deps = [{"from": "lead", "to": t, "type": "approval"} for t in "ab"]
    bypass = deps + [{"from": "a", "to": "b", "type": "bypass", "weight": 1.0}]
    assert calc(people, bypass)["score"] == calc(people, deps)["score"]
    assert calc(people, bypass)["key_people"][0]["id"] == "lead"


@pytest.mark.parametrize("people, deps", ORGS)
def test_deputy_reduces_the_persons_impact(people, deps):
    # Not "never raises risk": a deputy is one more person behind other bottlenecks.
    # The deputy does not inherit the person's own bypasses, which may keep them a bottleneck.
    for key in calc(people, deps)["key_people"]:
        new_people, new_deps = _with_deputy(people, deps, key["id"])
        after = {p["id"]: p["impact"] for p in calc(new_people, new_deps)["key_people"]}
        assert after.get(key["id"], 0.0) <= key["impact"] + 1e-12
        own_bypass = any(d["from"] == key["id"] and d["type"] == "bypass" for d in deps)
        if not own_bypass:
            assert key["id"] not in after


@pytest.mark.parametrize("people, deps", ORGS)
def test_bypass_controls_never_raise_risk(people, deps):
    risk = calc(people, deps)["composite_score"]
    for dep in deps:
        if dep["type"] == "bypass":
            controlled = _with_controlled_bypass(deps, (dep["from"], dep["to"]))
            assert calc(people, controlled)["composite_score"] <= risk + 1e-9


@pytest.mark.parametrize("people, deps", ORGS[:10])
def test_relabelling_people_does_not_change_the_score(people, deps):
    rename = {p["id"]: f"x{len(people) - i}" for i, p in enumerate(people)}
    renamed_people = [{**p, "id": rename[p["id"]]} for p in people]
    renamed_deps = [{**d, "from": rename[d["from"]], "to": rename[d["to"]]} for d in deps]
    assert calc(renamed_people, renamed_deps)["composite_score"] == pytest.approx(
        calc(people, deps)["composite_score"]
    )


# Fix plan


def test_example_fix_plan():
    data = json.loads(EXAMPLE.read_text())
    plan = HumanRiskGraph(data["people"], data["dependencies"]).fix_plan()

    assert [f["action"] for f in plan] == ["control-bypass", "deputy", "deputy"]
    assert plan[0]["target"] == ["elena.popescu", "anna.mueller"]
    assert plan[0]["score_before"] == 52
    for before, after in zip(plan, plan[1:]):
        assert after["score_before"] == before["score_after"]
    assert all(f["score_after"] > f["score_before"] for f in plan)


@pytest.mark.parametrize("people, deps", ORGS[:15])
def test_fix_plan_only_improves(people, deps):
    plan = HumanRiskGraph(people, deps).fix_plan(steps=3)
    risks = [plan[0]["risk_before"]] + [f["risk_after"] for f in plan] if plan else []
    assert risks == sorted(risks, reverse=True)
    assert len({(f["action"], str(f["target"])) for f in plan}) == len(plan)


def test_fix_plan_on_clean_organization_is_empty():
    assert HumanRiskGraph([{"id": "a"}, {"id": "b"}], [{"from": "a", "to": "b"}]).fix_plan() == []


# Separations in one DFS (Tarjan) must match one search per articulation point.


def _reference_separations(graph):
    import networkx as nx

    component = {node: comp for comp in nx.connected_components(graph) for node in comp}
    return {
        v: sorted(
            (len(c) for c in nx.connected_components(graph.subgraph(component[v] - {v}))),
            reverse=True,
        )
        for v in nx.articulation_points(graph)
    }


def test_separations_match_the_reference_on_random_graphs():
    import random

    import networkx as nx

    from human_risk_graph.model_v2 import separations

    rnd = random.Random(0)
    for _ in range(1000):
        n = rnd.randint(1, 30)
        graph = nx.Graph()
        graph.add_nodes_from(range(n))
        graph.add_edges_from(
            (rnd.randrange(n), rnd.randrange(n)) for _ in range(rnd.randint(0, 2 * n))
        )  # includes self-loops, isolated people and several components
        assert separations(graph) == _reference_separations(graph)


def test_separations_on_known_shapes():
    import networkx as nx

    from human_risk_graph.model_v2 import separations

    assert separations(nx.path_graph(5)) == {1: [3, 1], 2: [2, 2], 3: [3, 1]}
    assert separations(nx.star_graph(3)) == {0: [1, 1, 1]}
    assert separations(nx.cycle_graph(5)) == {}
    deep = nx.path_graph(5000)  # no recursion limit: the search is iterative
    assert separations(deep)[2500] == [2500, 2499]
