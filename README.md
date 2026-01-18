<p align="center">
  <img src="logo.png" alt="Human Risk Graph" width="600">
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

```bash
# Install dependencies
pip install -r requirements.txt

# Run example analysis
python examples/run_example.py

# Run tests
pytest tests/ -v

# Generate synthetic data and run experiments
python experiments/generate_data.py
python experiments/run_experiments.py
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

## License

Licensed under the Apache License, Version 2.0.
See the LICENSE file for details.
