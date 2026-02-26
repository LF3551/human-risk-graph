# Changelog

All notable changes to Human Risk Graph will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.8] - 2026-02-26

### 🔧 Infrastructure

- Fixed duplicate CI runs: removed `tags: ['v*']` trigger from ci.yml
- Fixed duplicate Zenodo records: removed custom Zenodo job from release.yml, relying on native Zenodo GitHub integration
- Moved PyPI publish to release.yml (triggered on GitHub Release published)

## [0.1.7] - 2026-02-26

### 🔧 Infrastructure

- Fixed Zenodo automation: new releases now create a new version of existing record (10.5281/zenodo.18316882) instead of creating duplicate records

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
