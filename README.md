<p align="center">
  <img src="https://raw.githubusercontent.com/LF3551/human-risk-graph/main/docs/figures/banner.jpg" alt="Human Risk Graph: find the people your security depends on" width="880">
</p>

<p align="center">
  <a href="https://pypi.org/project/human-risk-graph/"><img src="https://img.shields.io/pypi/v/human-risk-graph?cacheSeconds=3600" alt="PyPI"></a>
  <a href="https://pypi.org/project/human-risk-graph/"><img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue" alt="Python 3.10-3.14"></a>
  <a href="https://pypistats.org/packages/human-risk-graph"><img src="https://img.shields.io/pypi/dm/human-risk-graph?cacheSeconds=3600" alt="Downloads"></a>
  <a href="https://github.com/LF3551/human-risk-graph/actions/workflows/ci.yml"><img src="https://github.com/LF3551/human-risk-graph/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/LF3551/human-risk-graph"><img src="https://codecov.io/gh/LF3551/human-risk-graph/branch/main/graph/badge.svg" alt="Coverage"></a>
  <br>
  <a href="https://scorecard.dev/viewer/?uri=github.com/LF3551/human-risk-graph"><img src="https://api.scorecard.dev/projects/github.com/LF3551/human-risk-graph/badge" alt="OpenSSF Scorecard"></a>
  <a href="https://www.bestpractices.dev/projects/12048"><img src="https://www.bestpractices.dev/projects/12048/badge" alt="OpenSSF Best Practices"></a>
  <a href="https://doi.org/10.5281/zenodo.18288055"><img src="https://img.shields.io/badge/DOI-10.5281%2Fzenodo.18288055-blue" alt="DOI"></a>
  <a href="https://github.com/LF3551/human-risk-graph/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#html-report">HTML report</a> ·
  <a href="#ci-integration">CI integration</a> ·
  <a href="docs/compliance.md">ISO 27001 · SOC 2 · DORA</a> ·
  <a href="docs/model.md">Model</a> ·
  <a href="https://doi.org/10.5281/zenodo.20260930">Paper</a>
</p>

# Human Risk Graph

**Your controls are only as strong as the people behind them.** Human Risk Graph maps who
approves, escalates to and can bypass whom, finds the people your organization cannot
afford to lose, and tells you **which three changes raise your score the most**.

- **One score, 0-100 and A-F**, from three metrics you can explain to a board: bus factor,
  effective number of approvers, and how many critical approvals can be bypassed.
- **A fix plan, not just a diagnosis**: deputies and second-person checks simulated on your
  data and ranked by score gain.
- **Built for pipelines and audits**: SARIF for GitHub code scanning, JUnit, a `--min-score`
  gate, `hrg diff` between snapshots, findings mapped to ISO/IEC 27001, SOC 2 and DORA.
- **A report you can hand over**: one offline HTML file with an interactive dependency map,
  readable on a phone and printable as PDF.

## Why

Simple ratios hide the worst cases. HRG is designed so that they cannot:

| Situation | Naive metric | Human Risk Graph |
|---|---|---|
| One person approves everything | "inequality 0" (nothing to compare) | 1.0 effective approvers, grade F |
| 99 people depend on one critical lead | 0.009 (diluted by headcount) | bus factor 1, same risk at any size |
| A critical approver can be bypassed | averaged away by good metrics | counted as an independent way to fail |

The model, its properties and its tests are in [docs/model.md](docs/model.md).

## Quick start

Try it on the example organization, nothing to set up (needs [uv](https://docs.astral.sh/uv/)):

```bash
curl -sO https://raw.githubusercontent.com/LF3551/human-risk-graph/main/examples/organization.yaml
uvx --from human-risk-graph hrg analyze organization.yaml
open organization_report.html   # xdg-open on Linux
```

Or install it:

```bash
pip install human-risk-graph
hrg analyze my-org.yaml
```

```
Human Risk Graph 0.8.0 · organization.yaml · 5 people · 5 dependencies

  Score  25/100  ██░░░░░░░░  F · Critical risk  model hrg-2

  Key people  bus factor 1 · losing Alice cuts off 2 people (67% of connections)
  Approvals   1.5 effective approvers of 2 · Alice holds 77%
  Overrides   2 of 3 critical approvals can be overridden

  Top fixes
  1  Require a second person for Bob's bypass of Alice  25 → 45  +20
  2  Add a deputy for Alice                             45 → 71  +26
  3  Add a deputy for Bob                               71 → 76   +5

  Findings  3 errors · 2 warnings
   ▲ HRG001 Alice (alice) is a single point of failure (criticality 0.90): losing them cuts off 2 people
            and 67% of the connections between the others.
   ▲ HRG002 Approval authority is concentrated (1.5 effective approvers of 2); Alice (alice) holds 77%
            of the approval weight.
   △ HRG003 Bob (bob) can bypass Alice (alice) and override the controls they enforce; one of them is
            critical.
   ...
```

## Scan a GitHub repository

No YAML to write by hand: draft the organization from who actually reviews and merges code.

```bash
hrg scan github my-org/payments-api        # uses GITHUB_TOKEN, GH_TOKEN or `gh auth token`
hrg analyze payments-api-org.yaml
```

The scan reads the most recent merged pull requests (`--max-prs`, default 100) and turns
evidence into dependencies:

| Evidence | Dependency |
|---|---|
| Approving reviews by someone other than the author | `approval` reviewer → author |
| CODEOWNERS of the files a pull request changed (teams expanded when visible) | `approval` owner → author |
| A pull request merged without an approving review | `bypass` merger → approvers |
| Ruleset bypass actors and branch protection allowances (when the token can see them) | `bypass` actor → approvers |

Permissions and history do not prove real authority, so the draft is for a person to
review: every dependency carries `source`, `evidence` and `confirmed: false`, and reports
show how many are still unconfirmed. Set `confirmed: true` as you check them and adjust
`criticality`; running the scan again keeps your confirmations, criticality and the
dependencies you added by hand (approvals in Slack, escalations, on-call).

```yaml
- from: lead
  to: dev
  type: bypass
  weight: 1.0
  source: merge-history+pr-reviews
  evidence: merged 3 PR(s) without an approving review (#812, #815, #820); also approved 4 of 9 merged PRs by dev
  confirmed: false
```

## HTML report

One self-contained file that works offline, in light and dark mode, on a phone and as a PDF:
score and verdict, fix plan, interactive dependency map, people, findings with related
controls, the exact formula, and an audit trail with the input file's SHA-256.

<p align="center">
  <img src="https://raw.githubusercontent.com/LF3551/human-risk-graph/main/docs/figures/html-report.png" alt="Human Risk Graph HTML report" width="800">
</p>

## What HRG measures

The score is built from three metrics (model `hrg-2`, see [docs/model.md](docs/model.md)):

- **Key-person risk** — how much of the organization depends on one person: losing them
  cuts off N people and X% of the connections between the others. Also reported as the
  classic **bus factor**.
- **Approval concentration** — the **effective number of approvers** (Herfindahl-Hirschman
  index): one person approving everything is as concentrated as it gets.
- **Override exposure** — the share of critical approvals someone can override through a
  bypass.

On top of the score, HRG simulates remediations (a deputy for a key person, a second-person
check on a bypass) and lists the three that raise the score most.

The original model from the paper is still available as `--model hrg-1`.

## Usage

### Installation

```bash
# Install from PyPI (recommended)
pip install human-risk-graph

# Or install from source
git clone https://github.com/LF3551/human-risk-graph.git
cd human-risk-graph
pip install -e .

# With development tools
pip install -e ".[dev]"
```

### Data Format

Describe your organization in a JSON or YAML file:

```json
{
  "$schema": "https://raw.githubusercontent.com/LF3551/human-risk-graph/main/src/human_risk_graph/organization.schema.json",
  "people": [
    { "id": "A", "role": "SRE", "criticality": 0.9 },
    { "id": "B", "role": "Security Engineer", "criticality": 0.8 },
    { "id": "C", "role": "Manager", "criticality": 0.7 },
    { "id": "D", "role": "Developer", "criticality": 0.4 }
  ],
  "dependencies": [
    { "from": "A", "to": "B", "type": "approval", "weight": 0.8 },
    { "from": "C", "to": "A", "type": "bypass", "weight": 0.9 }
  ]
}
```

**Fields:**
- `people.id` — unique identifier
- `people.role` — job title (optional)
- `people.criticality` — importance level (0.0-1.0)
- `dependencies.from/to` — person IDs
- `dependencies.type` — relationship type (approval, bypass, etc.)
- `dependencies.weight` — dependency strength (0.0-1.0)

Invalid input (duplicate or unknown IDs, values outside 0.0-1.0) is rejected with an error
that points to the offending entry.

**YAML and editor support:** files ending in `.yaml` or `.yml` are read as YAML
(see [examples/organization.yaml](examples/organization.yaml)). The
[JSON Schema](src/human_risk_graph/organization.schema.json) gives completion and
validation in editors: reference it with `"$schema"` in JSON, or with
`# yaml-language-server: $schema=<url>` at the top of a YAML file.
`hrg schema` prints the schema.

### CLI Usage

The easiest way to use HRG is through the command-line interface:

```bash
# Analyze an organization (generates JSON, Markdown, and HTML reports)
hrg analyze data/example_organization.json

# Generate only HTML report
hrg analyze data/example_organization.json --format html

# Specify output file
hrg analyze data/example_organization.json --format html --output my_report.html

# CI: SARIF and JUnit reports, fail if the score is below 70
hrg analyze examples/organization.yaml --format sarif --format junit --no-visualize --min-score 70

# Compare two snapshots (text, markdown or json)
hrg diff org-q1.yaml org-q2.yaml --format markdown

# Original model from the paper, no fix plan, only errors
hrg analyze data/example_organization.json --model hrg-1 --fixes 0 --quiet

# Generate interactive graph visualization only
hrg visualize data/example_organization.json
```

Exit codes: `0` success, `1` invalid input or error, `2` usage error,
`3` score below `--min-score`, composite risk above `--fail-above`, or risk increased with
`hrg diff --fail-on-increase`.

Each run writes the reports next to the input file: JSON (all results, findings and the fix
plan), Markdown, the HTML report, and with `--visualize` (default) a standalone interactive
graph.

### Configuration and risk acceptance

Put the settings your team agreed on in `hrg.toml` (or `[tool.hrg]` in `pyproject.toml`)
next to where you run `hrg`; options on the command line win. When a finding is a
conscious decision, record it as an **accepted risk** with a reason, a ticket and an
expiry date instead of lowering the bar for everyone:

```toml
min-score = 70

[weights]            # optional, must add up to 1
key-person = 0.4
concentration = 0.3
override = 0.3

[[accept]]
rule = "HRG003"
target = "bob->alice"          # a person ID, "from->to" for bypasses, or omit for the whole rule
reason = "Break-glass access for incidents; every use is reviewed by the CISO"
ticket = "SEC-123"
expires = 2027-06-30
```

Accepted findings stay visible but do not fail CI: they are listed under *Accepted risks*
in the reports, marked as suppressed (with the justification) in SARIF, and reported as
passed in JUnit. When `expires` passes, the finding counts again and `hrg` says so. An
acceptance that no longer matches anything is reported as safe to remove. See
[examples/hrg.toml](examples/hrg.toml).

### Findings and Compliance Mapping

Every finding has a rule ID (`HRG001` single point of failure, `HRG002` concentrated
approval authority, `HRG003` bypass involving a critical person, `HRG004` score above
threshold) and related controls in ISO/IEC 27001:2022, SOC 2 and DORA. The mapping is
informative, not a compliance assessment. See [docs/compliance.md](docs/compliance.md).

### CI integration

GitHub Actions example: findings appear as code scanning alerts on the organization file,
and the job fails when the score drops below 70.

```yaml
name: Human risk
on:
  pull_request:
    paths: [org/organization.yaml]
permissions:
  contents: read
  security-events: write
jobs:
  hrg:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - run: pip install human-risk-graph
      - run: >
          hrg analyze org/organization.yaml
          --format sarif --format junit --no-visualize --min-score 70
      - uses: github/codeql-action/upload-sarif@v4
        if: always()
        with:
          sarif_file: org/organization_report.sarif
```

The JUnit report (`org/organization_report.junit.xml`) has one test case per rule and
works with any CI system that shows test results. To show what a change does to the
scores, compare against the base branch:

```bash
git show origin/main:org/organization.yaml > /tmp/base.yaml
hrg diff /tmp/base.yaml org/organization.yaml --format markdown >> "$GITHUB_STEP_SUMMARY"
```

### Python API Usage

```python
from human_risk_graph import HumanRiskGraph

# Load your organization data
people = [...]
dependencies = [...]

# Create and analyze
hrg = HumanRiskGraph(people, dependencies)
results = hrg.calculate()  # model="hrg-1" for the original model

print(f"Score: {results['score']}/100 ({results['grade']}, {results['risk_level']} risk)")
print(f"Bus factor: {results['bus_factor_people']}")
print(f"Effective approvers: {results['effective_approvers']:.1f}")

for fix in hrg.fix_plan():
    print(f"{fix['title']}: {fix['score_before']} -> {fix['score_after']}")
```

## Development

- `src/human_risk_graph/` — the package (model, CLI, reports)
- `tests/` — unit, property and CLI tests
- `docs/` — formal model, compliance mapping, figures
- `examples/`, `data/` — example organizations and generated reports
- `experiments/` — synthetic data and benchmarks from the paper
- `paper/` — LaTeX source of the [paper](https://doi.org/10.5281/zenodo.20260930)

```bash
# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=human_risk_graph --cov-report=html

# Code formatting
black src/ tests/ --line-length 100

# Linting
flake8 src/ tests/

# Run experiments
python experiments/generate_data.py
python experiments/run_experiments.py
python experiments/visualize.py
```

## Use Cases

**Best suited for:** Organizations with 50+ employees, formal security processes, or compliance requirements.

- Security architecture analysis
- Business continuity planning (SOC2, ISO27001 audits)
- Insider threat assessment
- M&A due diligence (key person risk)
- Organizational risk modeling

**Note:** For small teams (<20 people), managers typically have direct visibility into dependencies. 
HRG provides the most value when organizational complexity exceeds intuitive understanding.

## Status

HRG is in beta (0.x): the metrics and the input format may still change between minor
releases. Scores support risk discussions and audits; they do not replace a full
risk assessment.

## Citation

If you use this software in your research or work, please cite:

```bibtex
@software{aleinikov_2026_hrg,
  author       = {Aleinikov, Aleksei},
  title        = {Human Risk Graph: A Quantitative Model for Organizational Security Risk},
  year         = 2026,
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.18288055},
  url          = {https://doi.org/10.5281/zenodo.18288055}
}
```

Or use this text citation:

> Aleinikov, A. (2026). Human Risk Graph: A Quantitative Model for Organizational Security Risk. Zenodo. https://doi.org/10.5281/zenodo.18288055

The DOI above always resolves to the latest release; each release also gets its own version DOI on [Zenodo](https://doi.org/10.5281/zenodo.18288055).

To cite the model itself, use the paper:

```bibtex
@article{aleinikov_2026_hrg_paper,
  author       = {Aleinikov, Aleksei},
  title        = {Human Risk Graph: A Quantitative Model for Organizational Security Risk},
  year         = 2026,
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.20260930},
  url          = {https://doi.org/10.5281/zenodo.20260930}
}
```

## License

Licensed under the Apache License, Version 2.0.
See the LICENSE file for details.
