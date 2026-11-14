# Changelog

All notable changes to Human Risk Graph will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### ✨ Added

- Under hrg-1 and hrg-2, `hrg analyze` prints a note when people in the file have no activity seen for over `inactive-days` (`last_active`), pointing to `--model hrg-3` and HRG007 when the file has functions; HRG007 itself stays a hrg-3 rule.
- **GitHub Enterprise Server:** `hrg scan github --api-url https://HOST/api/v3` (also `HRG_GITHUB_API_URL`, and `GITHUB_API_URL` as GitHub Actions sets it); the GitHub CLI token for that host is used. Action input `api-url`, by default the API of the GitHub the workflow runs on.

### ⚡ Performance

- Key-person impacts (hrg-1/hrg-2) come from one depth-first search (Tarjan's low-link) instead of a search per articulation point: the fix plan for 3,000 people takes under a second instead of about five minutes. Results are identical (checked against the previous implementation on random graphs and on the example reports).
- The HTML report draws the dependency map for up to 400 people and says so above that; `hrg analyze` with every report for 3,000 people takes seconds instead of minutes. `hrg visualize` still draws everyone.

### 🔬 Research

- Protocol of a second study, [docs/study-two-person.md](docs/study-two-person.md): two-person control and dormant authority over publishing in the 1,000 most downloaded PyPI packages, with its collection and analysis code (`benchmark/two_person.py`) and tests, fixed before any data in the sample was collected and registered on OSF ([doi:10.17605/OSF.IO/J8ZFG](https://doi.org/10.17605/OSF.IO/J8ZFG)).
- Helpers for the steps after collection (`benchmark/two_person_review.py`): a checklist for the manual measurement check with the evidence of each project (publishing workflow lines, environment settings, provenance of every file), its scoring into an aggregate agreement, and private-notification drafts with each project's channel (GitHub private vulnerability reporting, else its security policy, else none). They read the collection cache with the registered functions and never change the data.

### 📝 Documentation

- The validation study is described as a retrospective study with the protocol committed before data collection, not as pre-registered: the protocol was committed to this repository, not to an independent registry, and the outcome data already existed (README, `CITATION.cff`, `.zenodo.json`, the 0.14.1 entry below).

## [0.16.0] - 2026-11-14

### ✨ Added

- **Deploy functions from GitHub Environments** (model hrg-3): `hrg scan github` drafts `deploy-<environment>` for every deployment environment with required reviewers, as a two-person rule (`requires: 2`): one person starts the deployment, a reviewer approves it. Performers are the reviewers (teams expanded when visible) and the people who created the last 30 deployments; `alone` holds the reviewers unless *Prevent self-review* is on, and the admins when they can bypass the environment's rules. Environments without reviewers are drafted when their name looks like a production or publishing target (`production`, `pypi`, `release`, ...), as a function anyone who deploys completes alone. Deployments by bots are not counted.
- **Inactive people with authority** (`HRG007`, model hrg-3): people can carry `last_active` (a date, or `never`), and performers inactive for more than `inactive-days` (default 90; `--inactive-days`, `inactive-days` in `hrg.toml`, action input `inactive-days`) are reported with how the function's margin drops without them. A critical function active people cannot perform, or that an inactive account can still complete alone, is an error. The score does not change. Mapped to ISO/IEC 27001 A.5.18, A.8.2, A.5.30; SOC 2 CC6.2, CC6.3, CC9.1; DORA Art. 9(4)(c), 11(2)(a).
- The scan records `last_active` for people who can perform a function: the latest pull request, approval, release or deployment it read, or their last commit on the branch (at most 30 lookups per repository). `--no-activity` records nothing. Organization scans and re-scans keep the latest date.
- GitHub Action inputs `model` and `inactive-days`.

### 📝 Documentation

- [docs/model-hrg3.md](docs/model-hrg3.md): deploy functions, last activity and HRG007; [docs/compliance.md](docs/compliance.md): HRG007 and access reviews; [docs/privacy.md](docs/privacy.md): the activity date that is processed, why, and how to turn it off; schema: `people.last_active`.

## [0.15.3] - 2026-11-14

### 🐛 Fixed

- hrg-1 reports listed the critical people (articulation points) in a different order on every run, so JSON, Markdown and pseudonymized reports of the same input differed; they are now sorted.
- Tooltips of the interactive graph (`*_graph.html`) showed raw `<b>` and `<br>` tags: vis-network displays titles as plain text. They are now plain text with line breaks.
- The graph visualization computed betweenness centrality and articulation points once per person; they are computed once (`HumanRiskGraph.analyze_nodes()`), and the file is read and written as UTF-8 on every platform.

### 🔒 Security

- `GitHubClient` requires an `https` API URL and refuses to send the token to a URL outside the API, for example through a `Link` pagination header.
- `bandit` findings were reviewed and justified inline (`bandit -c pyproject.toml -r src/` is clean); `pip-audit` is in the hashed dev lock.

### 🔧 Changed

- black, flake8 (with the complexity limit) and mypy (now with `check_untyped_defs`) report no findings.
- CI: black, flake8 and mypy run in a separate job with the versions pinned in `requirements.txt` and fail the build; before, they were advisory. `bandit` and `pip-audit` (on the hashed lock) fail the build too; the previous `safety check` step needed an account and its failures were ignored. The test matrix no longer installs the linters.
- Refactored the 15 functions above the complexity limit (`hrg analyze`, `hrg scan github`, the GitHub scanner, report generation, configuration and input validation) into smaller functions, and fixed all type errors. Apart from the fixes above, reports and drafts are unchanged: compared byte for byte on the examples and on every GitHub scan scenario of the test suite.

## [0.15.2] - 2026-11-13

### 🗑️ Removed

- `scipy` and `matplotlib` are no longer installed with the package: nothing in it imports scipy, and matplotlib was used only by `visualization.generate_static_visualization`, an unused PNG fallback that is removed too. Installs are smaller and pull in fewer dependencies (matplotlib brought pillow). The paper experiments need `pip install "human-risk-graph[experiments]"`, which now includes matplotlib.
- Unreferenced legacy files: two old logos, an early diagram and `docs/example.md` (#59).

## [0.15.1] - 2026-11-13

### 📝 Documentation

- README: the key points cover the organization scan, pseudonymized reports and the validation study; links to the privacy and validation pages; three live examples, not two; the repository layout lists `benchmark/`.
- Live demo site: organization scan and `--pseudonymize` in "Try it", links to the validation study and the privacy page, and "not for judging people".
- `docs/model-hrg3.md` explains the per-repository functions of an organization scan.
- Example reports in `data/` regenerated with the current version (they were from 0.7.0).
- Package keywords: `gdpr`, `segregation-of-duties`, `github`.

## [0.15.0] - 2026-11-13

### ✨ Added

- **Pseudonymized reports** for GDPR and works-council requirements: `--pseudonymize` on `analyze`, `diff` and `visualize`, or `pseudonymize = true` in `hrg.toml`. People become keyed pseudonyms (`P-` + HMAC-SHA256 of the id with the key in `HRG_PSEUDONYM_KEY` or `--pseudonym-key-file`), stable across runs with the same key. Only allow-listed fields are kept: names, roles, e-mail addresses and evidence are dropped, and known ids and names are replaced in coverage gaps, the input file name and risk acceptance reasons. Risk acceptances keep matching; SARIF results still point at the right line.
- `hrg pseudonyms FILE`: the pseudonym, id and name of everyone, for re-identification by the key holder.
- [docs/privacy.md](docs/privacy.md): what HRG processes, what it is not for, pseudonymization, re-identification, and a deployment checklist (purpose and legal basis, works council, DPIA, retention).
- **Organization scan**: `hrg scan github --org ORG` scans the most recently pushed repositories (`--max-repos`, default 30; archived repositories and forks skipped unless `--include-archived` / `--include-forks`) and merges them into one draft. People appear once; dependencies between the same people are merged (a bypass outranks approvals, the highest weight wins); the `merge`, `release` and `admin` functions stay per repository (`REPO/release`), so hrg-3 shows everything one person's absence stops. Repositories that cannot be read become coverage gaps; a rate limit stops the scan. Re-scans keep human decisions.
- GitHub Action inputs `scan-org`, `max-repos` and `pseudonymize`. With `pseudonymize: true` the draft with real logins is not uploaded with the artifact, and report file names are pseudonymized too; a self-test checks that no login reaches the reports or their names.

### 🔧 Changed

- `--max-prs` of `hrg scan github` (and the action) defaults to 30 per repository with `--org`, 100 otherwise.

## [0.14.2] - 2026-11-13

### 🐛 Fixed

- `hrg scan github` (and the action's `scan` input) retries GitHub server errors (500, 502, 503, 504) and network failures up to three times, after 1, 2 and 4 seconds, instead of failing the whole scan on one transient error.

## [0.14.1] - 2026-11-13

### 🔬 Validation

- [Retrospective predictive study](docs/validation-hrg3.md) of the hrg-3 release function on 284 popular PyPI projects: a single releaser before 2024-11-01 went with a 4.8 times higher rate of no release in the following year (95% CI 1.5–15.3; commit truck factor: 1.9, 0.9–4.3). Adjusted for release activity: 2.7 (0.8–9.2). Protocol committed before data collection; data and code in `benchmark/validation/` and `benchmark/validate.py`.

### 🔒 Security

- Dev lock `requirements.txt` compiled with Python 3.11 so pillow is at 13.0.0; releases attach the build provenance attestation (`human-risk-graph.intoto.jsonl`). Code of conduct, issue forms and a PR template.

## [0.14.0] - 2026-11-13

### ✨ Added

- hrg-3: functions take `separation: required | not-required` (default `required`). With `not-required`, completing the function alone is the intended policy, for example a database restore by the on-call engineer: the function is left out of solo control S (numerator and denominator) and HRG006, and reports mark its solo performers "(by policy)". It still counts for function loss and HRG005. Re-scans keep the setting.
- Scenario tests for solo control: routine single-person operations, low criticality, policy functions next to a bypassed two-person rule, and the property that adding a policy function never changes S.

### 🔧 Changed

- `examples/functions.yaml`: the database restore is solo by policy, so the example's solo control is 2 of 3 critical functions instead of 3 of 4.

### 📝 Documentation

- [docs/compliance.md](docs/compliance.md) and the README list HRG005 and HRG006 with their ISO/IEC 27001, SOC 2 and DORA controls, and which rules each model raises. A test keeps the document in step with the rules.
- README workflow examples use `@v0.14.0`.

## [0.13.0] - 2026-11-13

### ✨ Added

- HTML map: moving dots on every edge show the direction of approvals, escalations and bypasses.
- Selecting a person shows what happens if they are unavailable: who is cut off (they pulse red on the map), who has no approver left, which functions stop, and for `hrg-3` the score without them.
- Clicking a fix highlights the people it is about on the map.
- Hovering an edge explains it ("Anna approves Luca · weight 0.80").
- Zoom buttons and drag to pan.

### 🔧 Changed

- Map layout spreads crowded nodes apart and places labels where they do not overlap other labels, nodes or edges.
- Map colours: red is a critical single point of failure, amber a single point of failure, an amber ring a critical person who is not one.
- Animations respect `prefers-reduced-motion`.

## [0.12.0] - 2026-11-13

### ✨ Added

- Model `hrg-3` (experimental, `--model hrg-3`): critical functions and the two-person rule. See [docs/model-hrg3.md](docs/model-hrg3.md).
  - Each function in a new `functions` section has a criticality, the people it `requires`, its `performers`, and who can complete it `alone`.
  - Metrics: function loss (what stops when one person is unavailable), authority concentration (HHI of function weight) and solo control (critical functions one person can complete alone, the SLSA Source Level 4 two-party question).
  - Availability and integrity sub-scores; a fix plan of backups and two-person rules.
  - Findings HRG005 (function depends on too few people) and HRG006 (critical function one person can complete alone), mapped to ISO/IEC 27001, SOC 2 and DORA.
  - A table of functions in every report; `examples/functions.yaml`; a third example on the live demo.
- `hrg scan github` drafts the `merge`, `release` and `admin` functions of a repository, with `source`, `evidence` and `confirmed: false`. Re-scans keep their criticality, `requires` and confirmation, and keep hand-written functions.
- Benchmark: release authors against declared maintainers (86% of 7).

### 🔧 Changed

- Reports count unconfirmed functions together with unconfirmed dependencies, and the score on confirmed data leaves out both.
- JUnit reports one test case per rule of the model used (HRG001-HRG004 for hrg-1 and hrg-2, HRG002, HRG004-HRG006 for hrg-3).

### 🐛 Fixed

- `hrg scan github` counted machine users named like bots (`prombot`, `jetstack-release-bot`, `k8s-ci-robot`) as people. Found by the benchmark: release-author agreement went from 60% to 86%, and flux2 approver recall from 30% to 60%.

## [0.11.0] - 2026-11-13

### ✨ Added

- GitHub Action (`uses: LF3551/human-risk-graph@v0.11.0`):
  - analyzes an organization file (`file`) or drafts one from a repository first (`scan`);
  - uploads findings to code scanning, writes a job summary (score, metrics, findings, top fixes, unconfirmed data and gaps), and uploads the HTML, Markdown, JSON and SARIF reports as an artifact;
  - fails on `min-score` or `fail-above` after the reports are published, honouring accepted risks;
  - outputs `score`, `grade`, `risk-level`, `errors`, `warnings`, `report-dir` and `sarif-file`;
  - runs in its own virtual environment, with inputs passed through environment variables, and is tested on Linux, macOS and Windows in this repository.
- `python -m human_risk_graph.gha summary|outputs REPORT.json`: the job summary and step outputs used by the action.

### 🐛 Fixed

- The CLI crashed with `UnicodeEncodeError` on consoles that are not UTF-8, such as cp1252 on Windows or redirected output; characters the console cannot show are now replaced.

## [0.10.0] - 2026-11-13

### ✨ Added

- Benchmark of `hrg scan github` against the approvers 8 public CNCF projects declare in MAINTAINERS or OWNERS (files the scanner does not read): [docs/benchmark.md](docs/benchmark.md), reproducible with `python benchmark/run.py`.
  - 82% of approving reviews come from declared approvers, and the most active approver is declared in every repository.
  - Person-level precision is 52% and recall 49%: anyone can approve on GitHub, and declared lists include inactive people.
  - Limitations: Prow `/approve` comments are not counted, and bypass discovery is not measured.
- `ScanResult.approvals_given` and `ScanResult.code_owners`: per-person approving reviews and the code owners seen, before dependencies are merged.

## [0.9.0] - 2026-11-13

### ✨ Added

- Score on confirmed data: when some dependencies are `confirmed: false`, every report also gives the score on confirmed dependencies only (`confirmed_only` in JSON metadata), so it is visible how much the result rests on unverified data.
- Break-glass bypasses: `review: after` on a bypass whose every use is reviewed afterwards. It still counts as an override, at half weight in override exposure, and is labelled in the metrics and in HRG003 findings (`break_glass_approvals` in the results). `hrg diff` lists changes to `review`.
- README: *What HRG is not*. HRG models authority, not code knowledge; for that, tools that mine Git history such as CodeScene or Busfactor are the better fit.

### 📝 Documentation

- docs/model.md:
  - when approval concentration is a deliberate control and how to record it;
  - the noisy-OR is a modelling choice, not a claim that the risks are independent;
  - the fix plan shows structural improvements, not that they are feasible;
  - the break-glass factor in B.

## [0.8.1] - 2026-11-13

### 🐛 Fixed

- hrg-2: bypass dependencies no longer count as connections for key-person risk and the bus factor. A new bypass could make a key person look less critical and raise the score. Now adding a bypass never improves the score (property-tested). Scores of organizations with bypasses can go down; the bundled example goes from 61 to 52 and reports more single points of failure.
- Fix plan: a second-person check on a bypass removes the bypass instead of turning it into an escalation, which could add a connection that did not exist.
- `hrg scan github`: a pull request merged without an approving review counts as a bypass only when the branch visibly requires reviews. Without that requirement there is no control to bypass, and when the requirement is not visible it is reported as a data gap.
- HTML report: the main-driver sentence was missing a full stop between the headline and the detail.

### ✨ Added

- Drafts from `hrg scan` have a `coverage` section: source, branch, number of pull requests, whether reviews are required (`true`, `false` or `unknown`) and `gaps`, the data the token could not see (protection settings, ruleset bypass actors, team members, admins). Every report shows the gaps, because what the scan could not see is not evidence that it does not exist. JSON metadata has `coverage_gaps`.

### 📝 Documentation

- docs/model.md: the support graph without bypasses; the weights 0.4 / 0.3 / 0.3 are model parameters, not calibrated values.

## [0.8.0] - 2026-11-13

### ✨ Added

- `hrg scan github OWNER/REPO`: drafts an organization file from a GitHub repository. Approving reviews and CODEOWNERS of changed files become `approval` dependencies; pull requests merged without an approving review, ruleset bypass actors and branch protection allowances become `bypass` dependencies. Teams are expanded when their members are visible. Bots are skipped unless `--include-bots`. Options: `--output`, `--branch`, `--max-prs`, `--token` (default `GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`).
- Every scanned dependency has `source`, `evidence` and `confirmed: false`; re-running the scan on an existing draft keeps confirmations, criticality, names, roles and hand-written dependencies.
- Reports show how many dependencies are unconfirmed (terminal, HTML, Markdown; `unconfirmed_dependencies` in JSON metadata).
- The schema documents `source`, `evidence` and `confirmed`.
- docs/model.md: what the score means and what it does not.

## [0.7.0] - 2026-11-13

### ✨ Added

- Project configuration in `hrg.toml`, `.hrg.toml` or `[tool.hrg]` in `pyproject.toml` (or `--config FILE`): `model`, `min-score`, `fail-above`, `fixes`, `critical-threshold` and `[weights]`. Options on the command line take precedence. Unknown keys and invalid values are errors. Used by `hrg analyze` and `hrg diff`.
- Risk acceptance: `[[accept]]` entries with `rule`, optional `target`, a required `reason`, optional `ticket` and `expires`. Accepted findings are listed under *Accepted risks* in the reports, marked as suppressed with the justification in SARIF, passed in JUnit (with the acceptance in `system-out`) and do not fail CI. Accepting `HRG004` lets a pipeline pass below `--min-score` until the acceptance expires. Expired acceptances stop suppressing and are reported; acceptances that match nothing are reported as removable.
- `examples/hrg.toml`.
- Findings in JSON include `accepted` and `acceptance`; report metadata includes `config_file`.

### 🔧 Changed

- New dependency on Python 3.10: tomli.

## [0.6.0] - 2026-11-13

### ✨ Added

- Redesigned HTML report: a single self-contained file (no external resources, works offline, light and dark mode, "Save as PDF").
  - Score ring, grade and a one-line verdict naming the main risk driver.
  - Metric cards in plain language: bus factor, effective approvers, overridable approvals.
  - Fix plan with the projected score after each step.
  - Interactive dependency map: single points of failure, critical people and bypasses at a glance; select a person to see what depends on them.
  - Sortable people table with criticality, impact, people cut off and approval share.
  - Findings grouped by rule with remediation and ISO/IEC 27001, SOC 2 and DORA controls.
  - Methodology with the exact formula and values, and an audit trail (input SHA-256, tool and model version, weights, threshold).
- Report metadata includes `input_name`, `input_sha256` and `tool_version`.

### 🔧 Changed

- Default criticality in report metadata is 0.5, as in the model (was 0.0).
- Reports record the input path as given instead of the absolute path, so shared reports do not reveal local directory names.
- Example reports in `data/` regenerated with the current version.
- README rewritten around the product (banner, quick start, why, report screenshot); Python badge shows the supported 3.10-3.14 instead of a stale cached list. PyPI status is Beta.

## [0.5.0] - 2026-11-13

### ⚠️ Breaking

- New default scoring model **hrg-2** ([docs/model.md](docs/model.md#3-model-hrg-2)). Scores change for every organization; `--model hrg-1` (or `calculate(model="hrg-1")`) reproduces the original model and the paper's results. Every result records its `model`.
  - Key-person risk replaces the bus factor score: the largest criticality × impact over all people, where impact is the share of connections between the others that depend on that person. It no longer shrinks with organization size (a star with a critical centre scored 0.004 in hrg-1).
  - Approval concentration uses the Herfindahl-Hirschman index (effective number of approvers). A single approver for everyone scored 0 in hrg-1; it is now 1.
  - Override exposure replaces bypass path enumeration: the weighted share of critical approvals that someone can override through a bypass. Linear time instead of exponential on dense graphs.
  - Composite risk combines the metrics as a normalised noisy-OR, so one severe weakness is not averaged away.
- `--fail-above` compares against the hrg-2 composite risk, so thresholds tuned for hrg-1 need review. `--min-score` is usually simpler.

### ✨ Added

- Score from 0 to 100 and grade A-F in every result, report and the CLI.
- Fix plan: `hrg analyze` simulates deputies for key people and second-person checks on bypasses, and lists the three that improve the score most, with the score after each step (`--fixes N`, `HumanRiskGraph.fix_plan()`).
- New terminal summary: score bar, plain-language metrics (bus factor, effective approvers, overridable approvals), top fixes, findings. `--quiet` prints only errors.
- `--min-score N` exits with code 3 when the score is below N; `--model` for `analyze` and `diff`.
- Results include `key_people` (impact and people cut off), `bus_factor_people`, `approval_shares`, `effective_approvers`, `critical_approvals`, `overridable_approvals`, `weights` and `critical_threshold`.
- `hrg diff` shows the score and grade change.
- Property-based tests for the model (bounds, monotonicity, invariance, reference structures).

### 🔧 Changed

- HRG001 and HRG003 messages say how many people a single point of failure cuts off and whose controls a bypass overrides. HRG002 uses effective approvers with hrg-2.
- `simulate_node_removal` computes both scores with the same model (it mixed models before).
- New dependency: rich.

## [0.4.0] - 2026-11-12

### ✨ Added

- Findings with rule IDs (`HRG001` single point of failure, `HRG002` concentrated approval authority, `HRG003` bypass involving a critical person, `HRG004` score above threshold), each mapped to related ISO/IEC 27001:2022, SOC 2 and DORA controls. They appear in all reports and in the CLI summary. See [docs/compliance.md](docs/compliance.md).
- `hrg analyze --format sarif` (SARIF 2.1.0, for GitHub code scanning) and `--format junit` (JUnit XML). `--format` can be repeated.
- `hrg analyze --fail-above SCORE` exits with code 3 when the composite score is above the threshold.
- `hrg diff OLD NEW` compares two snapshots: metric changes, added, removed and changed people and dependencies, introduced and resolved single points of failure. Text, Markdown or JSON output; `--fail-on-increase` exits with code 3 when the composite score went up.
- YAML input (`.yaml`, `.yml`) and a JSON Schema for organization files, published in the repository and printed by `hrg schema`.

### 🔧 Changed

- Person IDs must be non-empty strings. In YAML, quote IDs that look like numbers or booleans.
- `hrg analyze` exits with code 1 when a requested report cannot be written (previously a warning).
- New dependency: PyYAML.

### 🐛 Fixed

- The HTML report escapes names, roles and dependency types from the input file.
- README Python API example used a result key that does not exist.

## [0.3.1] - 2026-11-12

### 🐛 Fixed

- Invalid input is rejected with a clear error instead of silently producing a risk score of 0: duplicate or unknown person IDs, malformed entries, and `criticality` or `weight` outside [0, 1]. `HumanRiskGraph` raises `ValueError`; `hrg analyze` and `hrg visualize` exit with status 1.
- `hrg --version` reported 0.2.5; it now shows the installed package version.

### 📝 Documentation

- README example output matches the current example dataset.

## [0.3.0] - 2026-11-12

### ⚠️ Breaking

- The package is now importable as `human_risk_graph` (`from human_risk_graph import HumanRiskGraph`). Previous wheels installed generic top-level `src` and `tests` packages into `site-packages`; `from src.hrg import ...` no longer works.
- Dropped Python 3.8 and 3.9 (end of life, no longer available on GitHub-hosted runners); Python 3.10+ is required.

### 🔧 Changed

- Packaging moved from `setup.py` to `pyproject.toml`; the version is read from `human_risk_graph.__version__`.
- CI test matrix no longer stops on the first failing Python version.
- Release workflow builds the distributions once and publishes, attests and signs the same files; PyPI upload uses Trusted Publishing instead of an API token.
- CI and the release workflow check that the package, `CITATION.cff`, `.zenodo.json` and the release tag use the same version.
- README and `CITATION.cff` cite the Zenodo concept DOI `10.5281/zenodo.18288055`, which always resolves to the latest version (previously the v0.1.8 DOI).
- README, `CITATION.cff` and Zenodo metadata link the paper ([10.5281/zenodo.20260930](https://doi.org/10.5281/zenodo.20260930)).

### 🐛 Fixed

- `hrg analyze` / `hrg visualize` no longer create a `lib/` folder in the current directory; the HTML graph is self-contained.
## [0.2.5] - 2026-04-24

### ✨ Added

- Added Python 3.12, 3.13, 3.14 support (classifiers, CI matrix, black target-version)
- Added `tests/test_compatibility.py` — 15 cross-version compatibility tests

## [0.2.4] - 2026-02-26

### 📚 Documentation

- Added CII Best Practices passing badge (project ID 12048) to README
- Added `CONTRIBUTING.md` with contribution guidelines and code style requirements

## [0.2.3] - 2026-02-26

### 🔒 Security

- Added SLSA Level 3 build provenance attestations via `actions/attest-build-provenance@v4.0.0`
- Added CodeQL SAST workflow for Python (security-extended queries)
- Added pip dependency hashing (`requirements.txt` with SHA256 hashes via `pip-compile --generate-hashes`)

## [0.2.2] - 2026-02-26

### 🔒 Security

- Fixed OpenSSF Scorecard workflow: replaced tag SHA with commit SHA for `ossf/scorecard-action@v2.4.3`
- Fixed Token-Permissions: added `permissions: read-all` at workflow level in all CI workflows
- Fixed GPG commit signing: added `aleksei.aleinikov.gr@gmail.com` UID to signing key
- Added Dependabot for automated dependency updates (pip + github-actions)
- Added `SECURITY.md` with vulnerability disclosure policy
- Added Sigstore artifact signing to release workflow

## [0.2.1] - 2026-02-26

### 🔧 Infrastructure

- Minor version bump to validate full release pipeline

## [0.1.10] - 2026-02-26

### 🔧 Infrastructure

- Added ORCID (0009-0003-8866-3131) to author metadata in .zenodo.json and CITATION.cff

## [0.1.9] - 2026-02-26

### 🔧 Infrastructure

- Updated Zenodo DOI reference to 10.5281/zenodo.18783118 across all documentation
- Verified clean release pipeline: single CI run, single Zenodo record per release

## [0.1.8] - 2026-02-26

### 🔧 Infrastructure

- Fixed duplicate CI runs: removed `tags: ['v*']` trigger from ci.yml
- Fixed duplicate Zenodo records: removed custom Zenodo job from release.yml, relying on native Zenodo GitHub integration
- Moved PyPI publish to release.yml (triggered on GitHub Release published)

## [0.1.7] - 2026-02-26

### 🔧 Infrastructure

- Fixed Zenodo automation: new releases now create a new version of existing record (10.5281/zenodo.18783118) instead of creating duplicate records

## [0.1.6] - 2026-02-26

### 🔧 Infrastructure

- Fixed release.yml Zenodo job: rewrote as Python script to avoid bash variable interpolation issues
- Fixed tag-workflow SHA mismatch: tag now always points to latest HEAD with fixed CI scripts
- Zenodo deposit metadata now correctly wrapped in required API format

## [0.1.5] - 2026-02-26

### 🔧 Infrastructure

- Added automated PyPI publish job to CI on version tag push
- Added `release.yml` workflow: auto-archive to Software Heritage and Zenodo on GitHub Release publish
- GitHub environment `pypi` configured with `PYPI_TOKEN` secret for trusted publishing

## [0.1.4] - 2026-02-25

### ✨ Improved

- Enhanced report readability with additional explanatory sections:
  - "Why This Score" (weighted metric contribution breakdown)
  - "How To Read Metrics" (plain-language interpretation)
  - richer key findings and dependency profile context
- Improved graph visualization UX:
  - edge-type-aware styling (approval, escalation, bypass)
  - richer node/edge tooltips and in-graph guidance legend
  - clearer network summary for non-technical readers
- Upgraded example dataset to a larger European-style organization sample
  with richer dependencies that better exercise all metrics.

### ✅ Testing

- Expanded automated tests and increased coverage to 98%.
- Added additional tests for graph analysis branches, entropy metric logic,
  and HRG object behaviors.

## [0.1.0] - 2026-01-18

### 🎉 Initial Release

This is the first public release of Human Risk Graph (HRG), a quantitative model for measuring organizational security risk from human dependencies.

### ✨ Features

#### Core Functionality
- **Graph-based Risk Analysis**: Models organizational dependencies as directed graphs
- **Three Risk Metrics**:
  - **Bus Factor Score** (40% weight): Measures fragility from key person dependencies using articulation points
  - **Decision Concentration Score** (35% weight): Quantifies authority centralization using Gini coefficient
  - **Bypass Risk Score** (25% weight): Evaluates control override risks through critical path analysis
- **Composite HRG Score**: Weighted combination of all metrics for overall risk assessment

#### Command-Line Interface
- `hrg analyze` command for comprehensive organizational analysis
- `hrg visualize` command for interactive graph generation
- Multiple output formats: JSON, Markdown, HTML
- Beautiful terminal output with emoji indicators and formatted metrics
- Automatic report and visualization generation

#### Visualization
- **Interactive HTML graphs** using pyvis
- Risk-based node coloring (cyan → teal → yellow → orange → red)
- Hover tooltips with detailed node information
- Real-time graph manipulation (zoom, pan, drag)
- Embedded metrics legend
- Static PNG fallback using matplotlib

#### Reports
- **JSON reports**: Machine-readable analysis results
- **Markdown reports**: Human-readable documentation with recommendations
- **HTML reports**: Professional styled reports with dark theme
- Automatic risk level interpretation (Low/Moderate/High/Critical)
- Actionable security recommendations based on findings

#### Development & Quality
- Comprehensive test suite (25 tests, 100% passing)
- Code formatting with Black (100 char line length)
- Linting with flake8
- Type checking with mypy
- Security scanning with bandit
- GitHub Actions CI/CD pipeline
- Multi-version Python support (3.8, 3.9, 3.10, 3.11, 3.12)

#### Documentation
- Professional logo and branding
- Academic paper (LaTeX, arXiv-ready)
- Formal mathematical model with theorems and proofs
- API documentation
- Usage examples
- README with badges (CI, coverage, license, Python version, code style)

### 📊 Experimental Framework
- Synthetic data generation for 4 organizational topologies:
  - Hierarchical (traditional corporate)
  - Flat (modern startup)
  - Star (centralized authority)
  - Random (ad-hoc structure)
- Benchmark suite for algorithm validation
- Publication-quality visualization (300 DPI)

### 🔬 Algorithms
- **Tarjan's Algorithm** for articulation point detection (O(V+E))
- **Critical Path Analysis** for bypass risk assessment
- **Betweenness Centrality** for influence measurement
- **Gini Coefficient** for concentration measurement
- **Shannon Entropy** alternative for diversity metrics

### 📦 Package Structure
```
human-risk-graph/
├── src/              # Core implementation
│   ├── hrg.py        # Main HumanRiskGraph class
│   ├── metrics.py    # Risk scoring algorithms
│   ├── graph_analysis.py  # Graph algorithms
│   ├── cli.py        # Command-line interface
│   ├── reports.py    # Report generation
│   └── visualization.py   # Graph visualization
├── tests/            # Test suite (25 tests)
├── experiments/      # Synthetic data & benchmarks
├── paper/            # LaTeX academic paper
├── docs/             # Documentation
├── data/             # Example datasets
└── examples/         # Usage examples
```

### 🛠️ Technical Specifications
- **Language**: Python 3.8+
- **Core Dependencies**: NetworkX 3.0+, NumPy 1.24+, SciPy 1.10+
- **CLI Framework**: Click 8.1+
- **Visualization**: pyvis 0.3.2+, matplotlib 3.7+
- **Testing**: pytest 7.4+
- **License**: Apache 2.0

### 📚 Research Foundation
Based on academic research in:
- Graph Theory (Tarjan, 1972)
- Organizational Risk Management
- Human Factors in Security
- Social Network Analysis
- Information Security Economics

### 🎯 Use Cases
- CISSP portfolio demonstration
- Security risk assessment for organizations
- Academic research in human-centric security
- Organizational design optimization
- Business continuity planning
- Succession planning analysis

### 🔗 Links
- **Repository**: https://github.com/LF3551/human-risk-graph
- **Documentation**: [README.md](README.md)
- **Paper**: [paper/main.tex](paper/main.tex)
- **Examples**: [examples/](examples/)

### 👤 Author
Aleksei Aleinikov

### 📄 License
Apache License 2.0 - See [LICENSE](LICENSE) for details

---

## Future Roadmap

### Planned for v0.2.0
- [ ] Web interface (Flask/FastAPI)
- [ ] Real-time monitoring dashboard
- [ ] Integration with HR systems (LDAP, Active Directory)
- [ ] Machine learning for risk prediction
- [ ] Historical trend analysis
- [ ] Custom metric weights configuration
- [ ] Export to security frameworks (NIST, ISO 27001)

### Planned for v0.3.0
- [ ] Multi-organization comparison
- [ ] Simulation of organizational changes
- [ ] What-if scenario analysis
- [ ] Automated mitigation recommendations
- [ ] Integration with SIEM systems
- [ ] API for third-party integration

---

**Note**: This project is under active development. Contributions are welcome!

[0.1.0]: https://github.com/LF3551/human-risk-graph/releases/tag/v0.1.0
