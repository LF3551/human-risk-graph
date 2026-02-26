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
- Lint with `flake8`: `flake8 src/ tests/`
- Type hints encouraged; check with `mypy`: `mypy src/`

### Tests
- All new features must include unit tests in `tests/`
- Existing tests must not be broken
- Run: `pytest tests/ --cov=src`

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

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
