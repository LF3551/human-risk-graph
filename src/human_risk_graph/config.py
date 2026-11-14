"""
Project configuration (``hrg.toml`` or ``[tool.hrg]`` in ``pyproject.toml``).

Example ``hrg.toml``::

    model = "hrg-2"
    min-score = 70
    fixes = 3
    critical-threshold = 0.7
    pseudonymize = true   # reports show keyed pseudonyms instead of people

    [weights]
    key-person = 0.4
    concentration = 0.3
    override = 0.3

    [[accept]]
    rule = "HRG003"
    target = "luca.rossi->carlos.garcia"
    reason = "Break-glass access, every use reviewed by the CISO"
    ticket = "SEC-123"
    expires = 2027-03-01

Command-line options take precedence over the file.
"""

import sys
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from .findings import RULES, Finding
from .model_v2 import MODELS

CONFIG_FILES = ("hrg.toml", ".hrg.toml")
TOP_LEVEL_KEYS = {
    "model",
    "min-score",
    "fail-above",
    "fixes",
    "critical-threshold",
    "inactive-days",
    "pseudonymize",
    "weights",
    "accept",
}
WEIGHT_KEYS = {"key-person": "alpha", "concentration": "beta", "override": "gamma"}
ACCEPT_KEYS = {"rule", "target", "reason", "ticket", "expires"}


@dataclass(frozen=True)
class Acceptance:
    """A documented decision to accept the risk of a finding, optionally until a date."""

    rule: str
    reason: str
    target: Optional[str] = None
    ticket: Optional[str] = None
    expires: Optional[date] = None

    def matches(self, finding: Finding) -> bool:
        if finding.rule_id != self.rule:
            return False
        return self.target is None or finding.key.split(":", 1)[1] == self.target

    def expired(self, today: date) -> bool:
        return self.expires is not None and self.expires < today

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "target": self.target,
            "reason": self.reason,
            "ticket": self.ticket,
            "expires": self.expires.isoformat() if self.expires else None,
        }


@dataclass
class Config:
    path: Optional[Path] = None
    model: Optional[str] = None
    min_score: Optional[int] = None
    fail_above: Optional[float] = None
    fixes: Optional[int] = None
    critical_threshold: Optional[float] = None
    inactive_days: Optional[int] = None
    pseudonymize: Optional[bool] = None
    weights: Dict[str, float] = field(default_factory=dict)
    accept: List[Acceptance] = field(default_factory=list)

    def calculate_kwargs(self) -> Dict[str, Any]:
        """Keyword arguments for ``HumanRiskGraph.calculate`` set by this config."""
        kwargs: Dict[str, Any] = dict(self.weights)
        if self.critical_threshold is not None:
            kwargs["critical_threshold"] = self.critical_threshold
        return kwargs


class ConfigError(ValueError):
    pass


def _number(value: Any, where: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ConfigError(f"{where} must be a number between {low} and {high}, got {value!r}")
    return value


def _unknown(keys, allowed, where: str) -> None:
    extra = sorted(set(keys) - set(allowed))
    if extra:
        raise ConfigError(f"{where}: unknown key(s) {', '.join(extra)}")


def _acceptance(raw: Any, index: int, source: Path) -> Acceptance:
    where = f"{source}: accept[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a table")
    _unknown(raw, ACCEPT_KEYS, where)
    rule = raw.get("rule")
    if rule not in RULES:
        raise ConfigError(f"{where}.rule must be one of {', '.join(RULES)}, got {rule!r}")
    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ConfigError(f"{where}.reason is required: say why the risk is accepted")
    for key in ("target", "ticket"):
        if key in raw and not isinstance(raw[key], str):
            raise ConfigError(f"{where}.{key} must be a string")
    expires = raw.get("expires")
    if expires is not None and not (isinstance(expires, date) and not hasattr(expires, "hour")):
        raise ConfigError(f"{where}.expires must be a date such as 2027-03-01 (unquoted)")
    return Acceptance(
        rule=rule,
        reason=reason.strip(),
        target=raw.get("target"),
        ticket=raw.get("ticket"),
        expires=expires,
    )


# Numeric settings: TOML key -> (Config attribute, type, lowest, highest)
NUMERIC_SETTINGS = {
    "min-score": ("min_score", int, 0, 100),
    "fail-above": ("fail_above", float, 0, 1),
    "fixes": ("fixes", int, 0, 10),
    "critical-threshold": ("critical_threshold", float, 0, 1),
    "inactive-days": ("inactive_days", int, 1, 3650),
}


def parse_config(raw: Dict[str, Any], source: Path) -> Config:
    """Validate a parsed TOML table."""
    _unknown(raw, TOP_LEVEL_KEYS, str(source))
    config = Config(path=source)
    _parse_settings(raw, source, config)
    config.weights = _parse_weights(raw.get("weights", {}), source)

    accept = raw.get("accept", [])
    if not isinstance(accept, list):
        raise ConfigError(f"{source}: accept must be an array of tables ([[accept]])")
    config.accept = [_acceptance(a, i, source) for i, a in enumerate(accept)]
    return config


def _parse_settings(raw: Dict[str, Any], source: Path, config: Config) -> None:
    if "model" in raw:
        if raw["model"] not in MODELS:
            raise ConfigError(f"{source}: model must be one of {', '.join(MODELS)}")
        config.model = raw["model"]
    for key, (attribute, kind, low, high) in NUMERIC_SETTINGS.items():
        if key in raw:
            setattr(config, attribute, kind(_number(raw[key], f"{source}: {key}", low, high)))
    if "pseudonymize" in raw:
        if not isinstance(raw["pseudonymize"], bool):
            raise ConfigError(f"{source}: pseudonymize must be true or false")
        config.pseudonymize = raw["pseudonymize"]


def _parse_weights(weights: Any, source: Path) -> Dict[str, float]:
    """The [weights] table as ``calculate`` keyword arguments; empty when not set."""
    if not isinstance(weights, dict):
        raise ConfigError(f"{source}: [weights] must be a table")
    _unknown(weights, WEIGHT_KEYS, f"{source}: [weights]")
    if not weights:
        return {}
    if set(weights) != set(WEIGHT_KEYS):
        raise ConfigError(f"{source}: [weights] needs all of {', '.join(WEIGHT_KEYS)}")
    parsed = {
        WEIGHT_KEYS[k]: float(_number(v, f"{source}: weights.{k}", 0, 1))
        for k, v in weights.items()
    }
    if abs(sum(parsed.values()) - 1.0) > 1e-6:
        raise ConfigError(f"{source}: [weights] must add up to 1")
    return parsed


def load_config(path: Optional[Path] = None, directory: Optional[Path] = None) -> Config:
    """
    Load the configuration.

    With ``path``, read that file. Otherwise look in ``directory`` (default: current
    directory) for ``hrg.toml``, ``.hrg.toml``, then ``[tool.hrg]`` in ``pyproject.toml``.
    Returns an empty Config when nothing is found.
    """
    if path is None:
        directory = directory or Path.cwd()
        for name in CONFIG_FILES:
            if (directory / name).is_file():
                path = directory / name
                break
        else:
            pyproject = directory / "pyproject.toml"
            if pyproject.is_file():
                raw = _read(pyproject).get("tool", {}).get("hrg")
                if raw is not None:
                    return parse_config(raw, pyproject)
            return Config()

    raw = _read(path)
    if path.name == "pyproject.toml":
        raw = raw.get("tool", {}).get("hrg", {})
    return parse_config(raw, path)


def _read(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e


def apply_acceptances(
    findings: List[Finding], accept: List[Acceptance], today: Optional[date] = None
) -> Tuple[List[Finding], List[Acceptance]]:
    """
    Attach matching acceptances to findings.

    Expired acceptances are attached too but do not suppress the finding.

    Returns:
        The findings (with ``acceptance`` set where one matched) and the acceptances that
        matched no finding, which usually means the risk is gone and the entry can be removed.
    """
    today = today or date.today()
    used = set()
    result = []
    for finding in findings:
        match = next((a for a in accept if a.matches(finding)), None)
        if match is None:
            result.append(finding)
            continue
        used.add(match)
        result.append(replace(finding, acceptance=match, acceptance_expired=match.expired(today)))
    return result, [a for a in accept if a not in used]
