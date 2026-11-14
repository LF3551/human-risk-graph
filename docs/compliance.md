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
| `HRG002` approval-concentration | Fewer than 4 effective approvers (Herfindahl-Hirschman index of approval weight ≥ 0.25; model hrg-1: Gini coefficient ≥ 0.3). Reported against the person with the largest share. | `error` below 2 effective approvers (hrg-1: Gini ≥ 0.7), otherwise `warning` |
| `HRG003` critical-bypass | A `bypass` dependency starts or ends at a critical person. | `warning` |
| `HRG004` risk-above-threshold | The score is below `--min-score`, or the composite risk is above `--fail-above`. | `error` |
| `HRG005` function-single-point-of-failure | Model hrg-3: a function cannot be performed, or stops when one of its performers is unavailable. | `error` if the function is critical (criticality ≥ 0.7), otherwise `warning` |
| `HRG006` solo-critical-function | Model hrg-3: one person can complete a critical function alone, because it requires one person or someone in `alone` can bypass the second person ([SLSA Source Level 4](https://slsa.dev/spec/v1.2/source-requirements) two-party review). Functions marked `separation: not-required` are exempt. | `warning` |
| `HRG007` inactive-performer | Model hrg-3: a person who can perform a function has a `last_active` date older than `inactive-days` (default 90), or `never`. The message says how the function's margin drops without them. | `error` for a critical function that active people cannot perform, or that an inactive person can still complete alone; otherwise `warning` |

Models hrg-1 and hrg-2 raise HRG001-HRG004. Model hrg-3 raises HRG002 (for authority
over functions: Herfindahl-Hirschman index of function weight ≥ 0.25, `error` from 0.5),
HRG004, HRG005, HRG006 and HRG007. The JUnit report has one test case per rule of the model used.

## Related controls

| Rule | ISO/IEC 27001:2022 | SOC 2 (2017 TSC) | DORA (EU 2022/2554) |
|------|--------------------|------------------|---------------------|
| `HRG001` | A.5.29 Information security during disruption; A.5.30 ICT readiness for business continuity | CC1.4 Competent individuals, including succession planning; CC9.1 Mitigation of business disruption risk | Art. 10(1) Identification of material single points of failure; Art. 11(2)(a) Continuity of critical or important functions |
| `HRG002` | A.5.2 Information security roles and responsibilities; A.5.3 Segregation of duties | CC1.3 Structures, reporting lines, authorities and responsibilities; CC5.1 Control activities, including segregation of duties | Art. 5(2)(c) Clear roles and responsibilities for ICT functions; Art. 6(4) Segregation of ICT risk management, control and audit functions |
| `HRG003` | A.5.3 Segregation of duties; A.8.2 Privileged access rights; A.8.32 Change management | CC5.1 Control activities, including segregation of duties; CC6.3 Role-based access, least privilege and segregation of duties; CC8.1 Authorization of changes | Art. 9(4)(c) Access limited to approved functions; Art. 9(4)(e) Controlled approval of ICT changes |
| `HRG004` | 6.1.2 Information security risk assessment | CC3.2 Risk identification and analysis | Art. 6(8)(b) ICT risk tolerance level |
| `HRG005` | A.5.29 Information security during disruption; A.5.30 ICT readiness for business continuity | CC1.4 Competent individuals, including succession planning; CC9.1 Mitigation of business disruption risk | Art. 10(1) Identification of material single points of failure; Art. 11(2)(a) Continuity of critical or important functions |
| `HRG006` | A.5.3 Segregation of duties; A.8.2 Privileged access rights; A.8.32 Change management | CC5.1 Control activities, including segregation of duties; CC6.3 Role-based access, least privilege and segregation of duties; CC8.1 Authorization of changes | Art. 9(4)(c) Access limited to approved functions; Art. 9(4)(e) Controlled approval of ICT changes |
| `HRG007` | A.5.18 Access rights; A.8.2 Privileged access rights; A.5.30 ICT readiness for business continuity | CC6.2 Removal of access that is no longer authorized; CC6.3 Role-based access, least privilege and segregation of duties; CC9.1 Mitigation of business disruption risk | Art. 9(4)(c) Access limited to approved functions; Art. 11(2)(a) Continuity of critical or important functions |

Control titles are short paraphrases. Read the standard or regulation for the exact text.

## Using HRG as audit evidence

- **Point-in-time evidence:** keep the HTML or JSON report of each run. Both include the
  analysis date, the scores and every finding with its related controls.
- **Periodic review:** run `hrg diff` between two snapshots (for example, quarterly) to
  show which single points of failure were resolved or introduced, and how the scores changed.
- **Risk tolerance:** `--min-score` (or `--fail-above`) makes the agreed tolerance explicit
  and enforces it in CI. The HRG004 finding records every breach.
- **Risk acceptance:** `[[accept]]` entries in `hrg.toml` record who accepted which finding,
  why, under which ticket and until when. They live in version control, so the history of
  every decision is reviewable, and expired acceptances surface the finding again.
- **Access reviews:** HRG007 lists people who still hold authority over a function but have
  not been active for `inactive-days`, a starting point for the periodic review of access
  rights (ISO/IEC 27001 A.5.18, SOC 2 CC6.2).
- **Code scanning:** upload the SARIF report to GitHub code scanning to track findings as
  alerts, with history and dismissal reasons.
