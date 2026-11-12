# Findings and related compliance controls

`hrg analyze` turns the metrics into findings. Each finding has a rule ID, a level
(`error` or `warning`) and a list of related controls in ISO/IEC 27001:2022,
SOC 2 and DORA. The findings appear in the JSON, Markdown, HTML, SARIF and JUnit reports.

> The control references are informative. They tell an auditor or a GRC team which
> requirements a finding is relevant to. They are not an assessment of compliance,
> and a clean HRG run does not show that a control is effective.

## Rules

| Rule | Raised when | Level |
|------|-------------|-------|
| `HRG001` single-point-of-failure | A person is an articulation point: removing them disconnects the dependency graph. | `error` if the person is critical (criticality ≥ 0.7), otherwise `warning` |
| `HRG002` approval-concentration | Decision concentration (Gini coefficient of approval weight) is 0.3 or higher. Reported against the person with the largest share. | `error` at 0.7 or higher, otherwise `warning` |
| `HRG003` critical-bypass | A `bypass` dependency starts or ends at a critical person. | `warning` |
| `HRG004` risk-above-threshold | The composite score is above `--fail-above`. | `error` |

## Related controls

| Rule | ISO/IEC 27001:2022 | SOC 2 (2017 TSC) | DORA (EU 2022/2554) |
|------|--------------------|------------------|---------------------|
| `HRG001` | A.5.29 Information security during disruption; A.5.30 ICT readiness for business continuity | CC1.4 Competent individuals, including succession planning; CC9.1 Mitigation of business disruption risk | Art. 10(1) Identification of material single points of failure; Art. 11(2)(a) Continuity of critical or important functions |
| `HRG002` | A.5.2 Information security roles and responsibilities; A.5.3 Segregation of duties | CC1.3 Structures, reporting lines, authorities and responsibilities; CC5.1 Control activities, including segregation of duties | Art. 5(2)(c) Clear roles and responsibilities for ICT functions; Art. 6(4) Segregation of ICT risk management, control and audit functions |
| `HRG003` | A.5.3 Segregation of duties; A.8.2 Privileged access rights; A.8.32 Change management | CC5.1 Control activities, including segregation of duties; CC6.3 Role-based access, least privilege and segregation of duties; CC8.1 Authorization of changes | Art. 9(4)(c) Access limited to approved functions; Art. 9(4)(e) Controlled approval of ICT changes |
| `HRG004` | 6.1.2 Information security risk assessment | CC3.2 Risk identification and analysis | Art. 6(8)(b) ICT risk tolerance level |

Control titles are short paraphrases. Read the standard or regulation for the exact text.

## Using HRG as audit evidence

- **Point-in-time evidence:** keep the HTML or JSON report of each run. Both include the
  analysis date, the scores and every finding with its related controls.
- **Periodic review:** run `hrg diff` between two snapshots (for example, quarterly) to
  show which single points of failure were resolved or introduced, and how the scores changed.
- **Risk tolerance:** `--fail-above` makes the agreed tolerance explicit and enforces it in CI.
  The HRG004 finding records every breach.
- **Code scanning:** upload the SARIF report to GitHub code scanning to track findings as
  alerts, with history and dismissal reasons.
