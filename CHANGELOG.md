# Changelog

All notable changes to Human Risk Graph will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
