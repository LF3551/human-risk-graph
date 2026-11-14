# Contributing to Human Risk Graph

Thank you for your interest in contributing! This document explains how to contribute to the project.

## How to Contribute

All contributions are made via **pull requests** on GitHub:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run the tests: `pytest tests/`
5. Submit a pull request to the `main` branch

All pull requests must pass the CI pipeline (tests, linting, security checks) before merging.

## Reporting Bugs and Enhancements

- **Bug reports**: Open a [GitHub Issue](https://github.com/LF3551/human-risk-graph/issues) with a clear description and steps to reproduce.
- **Feature requests**: Open a [GitHub Issue](https://github.com/LF3551/human-risk-graph/issues) describing the use case.
- **Security vulnerabilities**: Follow the process in [SECURITY.md](SECURITY.md) — do not open a public issue.

## Requirements for Acceptable Contributions

### Code Style
- Python code must follow [PEP 8](https://peps.python.org/pep-0008/)
- Format with `black`: `black src/ tests/`
- Lint with `flake8`: `flake8 src/ tests/` (includes a cyclomatic complexity limit of 10)
- Type hints encouraged; check with `mypy` (settings in `pyproject.toml`)
- Security checks: `bandit -c pyproject.toml -r src/` and
  `pip-audit -r requirements.txt --require-hashes --disable-pip`

CI runs all of these with the tool versions pinned in `requirements.txt` (compiled for
Python 3.11) and fails on any finding. To use the same versions locally:

```bash
pip install --require-hashes -r requirements.txt   # Python 3.11
pip install --no-deps -e .
```

### Tests
- All new features must include unit tests in `tests/`
- Existing tests must not be broken
- Run: `pytest tests/ --cov=human_risk_graph`

### Commits
- Use clear, descriptive commit messages
- Follow [Conventional Commits](https://www.conventionalcommits.org/) format where possible:
  - `feat:` new feature
  - `fix:` bug fix
  - `ci:` CI/CD changes
  - `docs:` documentation only
  - `chore:` maintenance

### Documentation
- Update `docs/` and `README.md` if your change affects public-facing behavior
- Update `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/) format

## Development Setup

```bash
git clone https://github.com/LF3551/human-risk-graph.git
cd human-risk-graph
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pip install -r requirements.in
```

## Releasing (maintainers)

1. In a pull request, bump the version in `src/human_risk_graph/__init__.py`, `CITATION.cff` (`version`, `date-released`, `preferred-citation.version`) and `.zenodo.json`, and add a `CHANGELOG.md` entry. CI fails if these versions differ.
2. After merging, publish a GitHub Release with tag `vX.Y.Z`.
3. The release workflow then runs automatically:
   - checks that the tag matches the project version;
   - builds the sdist and wheel once;
   - publishes them to PyPI via Trusted Publishing (no API token);
   - attests build provenance and attaches the files with Sigstore signatures to the release;
   - requests a Software Heritage archive.
4. Zenodo mints a new version DOI from the release via its GitHub integration. The concept DOI [10.5281/zenodo.18288055](https://doi.org/10.5281/zenodo.18288055) always points to the latest version.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
