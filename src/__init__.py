"""
Human Risk Graph (HRG) - A quantitative model for organizational security risk.

This package provides tools for modeling and analyzing security risks
arising from human dependencies in organizations.
"""

from .hrg import HumanRiskGraph
from .metrics import (
    bus_factor_score,
    decision_concentration_score,
    bypass_risk_score,
    composite_hrg_score,
    interpret_risk_level,
)

__version__ = "0.1.3"
__author__ = "Aleksei Aleinikov"

__all__ = [
    "HumanRiskGraph",
    "bus_factor_score",
    "decision_concentration_score",
    "bypass_risk_score",
    "composite_hrg_score",
    "interpret_risk_level",
]
