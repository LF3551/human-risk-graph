# Git Quick Start Guide

## Initial Commit

```bash
# Make sure you're in the project directory
cd /Users/alekseialeinikov/Documents/SCRIPTS/human-risk-graph

# Check status (venv should be ignored)
git status

# Add all files
git add .

# Commit
git commit -m "Initial commit: Human Risk Graph v0.1.0

- Core implementation (src/) with graph-based risk metrics
- Comprehensive test suite (25 tests, 100% passing)
- Synthetic data generation and experiments
- Publication-quality visualizations (4 plots)
- LaTeX research paper structure
- Complete documentation and examples"

# Push to remote
git push origin main
```

## What's Tracked

✅ **Source code** (`src/`, `tests/`, `examples/`, `experiments/`)
✅ **Documentation** (`docs/`, `README.md`, `PROJECT_SUMMARY.md`)
✅ **Paper** (`paper/` - LaTeX source)
✅ **Data** (example_organization.json, synthetic datasets)
✅ **Results** (experiment_results.csv)
✅ **Visualizations** (all PNG plots)
✅ **Configuration** (requirements.txt, setup.py)

## What's Ignored

❌ **Virtual environment** (`venv/`)
❌ **Python cache** (`__pycache__/`, `*.pyc`)
❌ **IDE files** (`.vscode/`, `.idea/`)
❌ **Test artifacts** (`.pytest_cache/`, `.coverage`)
❌ **LaTeX build files** (`*.aux`, `*.log`, compiled PDFs)
❌ **OS files** (`.DS_Store`)

## Repository Size

Without venv: **~1.5 MB** ✓ (GitHub friendly)
- Source code: 68 KB
- Tests: 68 KB  
- Paper: 48 KB
- Experiments: 916 KB (includes 4 PNG plots)
- Docs: 396 KB

## Tag for Release

```bash
git tag -a v0.1.0 -m "Version 0.1.0 - Initial Release

Features:
- Human Risk Graph model implementation
- Three core metrics (Bus Factor, Decision Concentration, Bypass Risk)
- Complete test suite
- Experimental validation
- Research paper draft"

git push origin v0.1.0
```

## Update Remote

```bash
# If you created repo on GitHub
git remote add origin https://github.com/yourusername/human-risk-graph.git
git branch -M main
git push -u origin main
```

## Branches for Development

```bash
# Create feature branch
git checkout -b feature/new-metric

# Work on feature
# ...

# Merge back
git checkout main
git merge feature/new-metric
git push
```

## Notes

- All experimental results and plots are tracked for reproducibility
- LaTeX source is tracked, but compiled PDFs are ignored
- Run `pytest` before committing to ensure tests pass
- Update `PROJECT_SUMMARY.md` for major changes
