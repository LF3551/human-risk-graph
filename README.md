<p align="center">
  <img src="logo.png" alt="Human Risk Graph" width="600">
</p>

<p align="center">
  <a href="https://doi.org/10.5281/zenodo.18288056">
    <img src="https://img.shields.io/badge/DOI-10.5281%2Fzenodo.18288056-blue" alt="DOI">
  </a>
  <a href="https://github.com/LF3551/human-risk-graph/releases">
    <img src="https://img.shields.io/github/v/release/LF3551/human-risk-graph" alt="Latest Release">
  </a>
  <a href="https://github.com/LF3551/human-risk-graph/actions/workflows/ci.yml">
    <img src="https://github.com/LF3551/human-risk-graph/actions/workflows/ci.yml/badge.svg" alt="CI/CD Pipeline">
  </a>
  <a href="https://codecov.io/gh/LF3551/human-risk-graph">
    <img src="https://codecov.io/gh/LF3551/human-risk-graph/branch/main/graph/badge.svg" alt="Coverage">
  </a>
  <a href="https://github.com/LF3551/human-risk-graph/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License">
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python 3.8+">
  </a>
  <a href="https://github.com/psf/black">
    <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
  </a>
  <a href="https://github.com/LF3551/human-risk-graph/releases">
    <img src="https://img.shields.io/github/downloads/LF3551/human-risk-graph/total.svg" alt="Downloads">
  </a>
</p>

# Human Risk Graph (HRG)

Human Risk Graph (HRG) is a quantitative model for measuring organizational
security risk caused by human dependencies, decision concentration,
and bus-factor effects.

Unlike traditional security models that focus only on technical assets,
HRG treats people as part of the attack surface and models how organizational
decisions and emergency processes introduce systemic risk.

## Core Idea

Organizations often depend on a small number of individuals for:
- critical decisions,
- emergency bypasses,
- access approvals.

HRG represents these dependencies as a directed graph and computes
risk metrics that highlight human single points of failure.

## What HRG Measures

- **Bus Factor Risk** — how fragile the organization is to the loss of key people
- **Decision Concentration** — how much authority is centralized
- **Bypass Risk** — how often normal controls are overridden by humans

## Repository Structure

- `src/` — core implementation (HRG class, metrics, graph algorithms)
- `tests/` — comprehensive unit tests
- `experiments/` — synthetic data generation and benchmarking
- `examples/` — usage demonstrations
- `paper/` — LaTeX source for academic paper (arXiv-ready)
- `docs/` — formal model with mathematical definitions
- `data/` — example organization datasets

## Quick Start

### Installation

```bash
# Install from source
git clone https://github.com/LF3551/human-risk-graph.git
cd human-risk-graph
pip install -e .

# Or install specific extras
pip install -e ".[dev]"  # Development tools
```

### Data Format

Create a JSON file describing your organization structure:

```json
{
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

### CLI Usage

The easiest way to use HRG is through the command-line interface:

```bash
# Analyze an organization (generates JSON, Markdown, and HTML reports)
hrg analyze data/example_organization.json

# Generate only HTML report
hrg analyze data/example_organization.json --format html

# Specify output file
hrg analyze data/example_organization.json --format html --output my_report.html

# Generate interactive graph visualization only
hrg visualize data/example_organization.json
```

### Example Output

```
🔍 Analyzing: data/example_organization.json
⚙️  Running Human Risk Graph analysis...
✅ Generated: example_organization_report.json
✅ Generated: example_organization_graph.html

============================================================
📊 ANALYSIS SUMMARY
============================================================
Composite HRG Score: 0.090
  • Bus Factor Score: 0.225
  • Decision Concentration: 0.000
  • Bypass Risk Score: 0.000

⚠️  Critical People (Articulation Points): 1
   - A

✅ Analysis complete! Generated 2 file(s).
```

**Generated files:**
- JSON report with detailed metrics
- Interactive HTML graph visualization
- Optional Markdown and HTML reports

### Python API Usage

```python
from src.hrg import HumanRiskGraph

# Load your organization data
people = [...]
dependencies = [...]

# Create and analyze
hrg = HumanRiskGraph(people, dependencies)
results = hrg.calculate()

print(f"Composite Risk Score: {results['composite_score']:.3f}")
print(f"Critical People: {results['critical_people']}")
```

## Development

```bash
# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=src --cov-report=html

# Code formatting
black src/ tests/ --line-length 100

# Linting
flake8 src/ tests/

# Run experiments
python experiments/generate_data.py
python experiments/run_experiments.py
python experiments/visualize.py
```

## Key Features

- **Graph-based analysis** using NetworkX
- **Three core metrics**: Bus Factor, Decision Concentration, Bypass Risk
- **Polynomial-time algorithms** with proven complexity bounds
- **Comprehensive test coverage**
- **Research paper** ready for arXiv submission
- **CISSP portfolio** demonstration project

## Use Cases

- Security architecture analysis
- Business continuity planning
- Insider threat assessment
- Organizational risk modeling

## Status

This repository provides a **reference implementation** of the HRG model.
It is intended for research, architecture analysis, and discussion —
not as a production-ready security tool.

## Citation

If you use this software in your research or work, please cite:

```bibtex
@software{aleinikov_2026_hrg,
  author       = {Aleinikov, Aleksei},
  title        = {Human Risk Graph: A Quantitative Model for Organizational Security Risk},
  year         = 2026,
  publisher    = {Zenodo},
  version      = {v0.1.1},
  doi          = {10.5281/zenodo.18288056},
  url          = {https://doi.org/10.5281/zenodo.18288056}
}
```

Or use this text citation:

> Aleinikov, A. (2026). Human Risk Graph: A Quantitative Model for Organizational Security Risk (v0.1.1). Zenodo. https://doi.org/10.5281/zenodo.18288056

## License

Licensed under the Apache License, Version 2.0.
See the LICENSE file for details.
