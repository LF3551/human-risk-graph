"""
Findings derived from an HRG analysis, with related compliance controls.

The control references are informative: they point auditors to the requirements a
finding is relevant to. They are not an assessment of compliance.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .hrg import HumanRiskGraph

FRAMEWORKS = {
    "iso27001": "ISO/IEC 27001:2022",
    "soc2": "SOC 2 (2017 Trust Services Criteria)",
    "dora": "DORA (Regulation (EU) 2022/2554)",
}

# Metric levels used by the reports: >= 0.7 high, >= 0.3 moderate.
HIGH_LEVEL = 0.7
MODERATE_LEVEL = 0.3


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    title: str
    description: str
    remediation: str
    controls: Dict[str, Tuple[Tuple[str, str], ...]]  # framework -> ((ref, title), ...)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    level: str  # SARIF levels: "error", "warning", "note"
    message: str
    person: Optional[str] = None
    dependency: Optional[Tuple[str, str]] = None

    @property
    def rule(self) -> Rule:
        return RULES[self.rule_id]

    @property
    def key(self) -> str:
        """Stable identifier of the finding across runs."""
        if self.dependency:
            return f"{self.rule_id}:{self.dependency[0]}->{self.dependency[1]}"
        return f"{self.rule_id}:{self.person or ''}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule": self.rule.name,
            "level": self.level,
            "message": self.message,
            "person": self.person,
            "dependency": (
                {"from": self.dependency[0], "to": self.dependency[1]} if self.dependency else None
            ),
            "remediation": self.rule.remediation,
            "controls": {
                fw: [{"id": ref, "title": title} for ref, title in refs]
                for fw, refs in self.rule.controls.items()
            },
        }


RULES: Dict[str, Rule] = {
    rule.id: rule
    for rule in (
        Rule(
            id="HRG001",
            name="single-point-of-failure",
            title="Single point of failure",
            description=(
                "Removing this person disconnects the dependency graph: approvals, "
                "escalations or bypasses that pass through them have no alternative path."
            ),
            remediation=(
                "Name a deputy, cross-train them, and document the approvals and emergency "
                "procedures this person handles."
            ),
            controls={
                "iso27001": (
                    ("A.5.29", "Information security during disruption"),
                    ("A.5.30", "ICT readiness for business continuity"),
                ),
                "soc2": (
                    ("CC1.4", "Competent individuals, including succession planning"),
                    ("CC9.1", "Mitigation of business disruption risk"),
                ),
                "dora": (
                    ("Art. 10(1)", "Identification of material single points of failure"),
                    ("Art. 11(2)(a)", "Continuity of critical or important functions"),
                ),
            },
        ),
        Rule(
            id="HRG002",
            name="approval-concentration",
            title="Concentrated approval authority",
            description=(
                "Approval authority is unevenly distributed: a few people hold most of the "
                "approval weight (Gini coefficient of approval weights)."
            ),
            remediation=(
                "Add secondary approvers for sensitive workflows and spread ownership of "
                "high-impact decisions."
            ),
            controls={
                "iso27001": (
                    ("A.5.2", "Information security roles and responsibilities"),
                    ("A.5.3", "Segregation of duties"),
                ),
                "soc2": (
                    ("CC1.3", "Structures, reporting lines, authorities and responsibilities"),
                    ("CC5.1", "Control activities, including segregation of duties"),
                ),
                "dora": (
                    ("Art. 5(2)(c)", "Clear roles and responsibilities for ICT functions"),
                    (
                        "Art. 6(4)",
                        "Segregation of ICT risk management, control and audit functions",
                    ),
                ),
            },
        ),
        Rule(
            id="HRG003",
            name="critical-bypass",
            title="Bypass involving a critical person",
            description=(
                "A bypass dependency lets a person skip or override the normal control, and "
                "at least one side of it is a critical person."
            ),
            remediation=(
                "Require a second person for the bypass, log every use, and review each use "
                "after the fact."
            ),
            controls={
                "iso27001": (
                    ("A.5.3", "Segregation of duties"),
                    ("A.8.2", "Privileged access rights"),
                    ("A.8.32", "Change management"),
                ),
                "soc2": (
                    ("CC5.1", "Control activities, including segregation of duties"),
                    ("CC6.3", "Role-based access, least privilege and segregation of duties"),
                    ("CC8.1", "Authorization of changes"),
                ),
                "dora": (
                    ("Art. 9(4)(c)", "Access limited to approved functions"),
                    ("Art. 9(4)(e)", "Controlled approval of ICT changes"),
                ),
            },
        ),
        Rule(
            id="HRG004",
            name="risk-above-threshold",
            title="Composite risk above threshold",
            description="The composite HRG score is above the threshold set with --fail-above.",
            remediation=(
                "Address the other findings, or record a risk acceptance if the threshold is "
                "deliberately exceeded."
            ),
            controls={
                "iso27001": (("6.1.2", "Information security risk assessment"),),
                "soc2": (("CC3.2", "Risk identification and analysis"),),
                "dora": (("Art. 6(8)(b)", "ICT risk tolerance level"),),
            },
        ),
    )
}


def _label(hrg: HumanRiskGraph, person_id: str) -> str:
    person = next((p for p in hrg.people if p["id"] == person_id), {})
    name = person.get("name")
    return f"{name} ({person_id})" if name and name != person_id else person_id


def _approval_shares(hrg: HumanRiskGraph) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for edge, edge_type in hrg.edge_types.items():
        if edge_type == "approval":
            weights[edge[0]] = weights.get(edge[0], 0.0) + hrg.weights.get(edge, 0.0)
    total = sum(weights.values())
    return {person: w / total for person, w in weights.items()} if total else {}


def collect_findings(
    hrg: HumanRiskGraph, results: Dict[str, Any], fail_above: Optional[float] = None
) -> List[Finding]:
    """
    Turn analysis results into findings.

    Args:
        hrg: The analysed graph.
        results: Output of ``hrg.calculate()``.
        fail_above: Optional composite score threshold; exceeding it adds an HRG004 finding.

    Returns:
        Findings ordered by rule, then by person.
    """
    findings: List[Finding] = []
    critical = set(results.get("critical_nodes", []))

    for person in sorted(results.get("articulation_points", [])):
        crit = hrg.criticality.get(person, 0.5)
        findings.append(
            Finding(
                rule_id="HRG001",
                level="error" if person in critical else "warning",
                message=(
                    f"{_label(hrg, person)} is a single point of failure "
                    f"(criticality {crit:.2f}): removing them disconnects the dependency graph."
                ),
                person=person,
            )
        )

    dc = results.get("decision_concentration", 0.0)
    shares = _approval_shares(hrg)
    if dc >= MODERATE_LEVEL and shares:
        top = max(sorted(shares), key=shares.get)
        findings.append(
            Finding(
                rule_id="HRG002",
                level="error" if dc >= HIGH_LEVEL else "warning",
                message=(
                    f"Approval authority is concentrated (Gini {dc:.2f}); "
                    f"{_label(hrg, top)} holds {shares[top]:.0%} of the approval weight."
                ),
                person=top,
            )
        )

    for (source, target), edge_type in sorted(hrg.edge_types.items()):
        if edge_type == "bypass" and (source in critical or target in critical):
            findings.append(
                Finding(
                    rule_id="HRG003",
                    level="warning",
                    message=(
                        f"Bypass from {_label(hrg, source)} to {_label(hrg, target)} "
                        "involves a critical person."
                    ),
                    person=source,
                    dependency=(source, target),
                )
            )

    score = results["composite_score"]
    if fail_above is not None and score > fail_above:
        findings.append(
            Finding(
                rule_id="HRG004",
                level="error",
                message=f"Composite HRG score {score:.3f} is above the threshold {fail_above:.3f}.",
            )
        )

    return findings
