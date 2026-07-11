"""
engine — deterministic trading engine for the quant app.

Pure-function spine (`02 §2`):

    Snapshot ─▶ indicators.compute ─▶ Features
    Features ─▶ signal.evaluate    ─▶ Signal
    Signal   ─▶ signal.decide      ─▶ Decision
    Decision ─▶ risk.apply_decision─▶ Decision'

NO LLM, no network, no clock reads inside indicators/signal/decision. Standard
library only for the core. See `engine/README.md`.
"""

from __future__ import annotations

from . import contracts, indicators, signal_engine, risk, sizing, costs, datasource, capture, backtest
from .config import Profile, get_profile, PROFILES

__all__ = [
    "contracts",
    "indicators",
    "signal_engine",
    "risk",
    "sizing",
    "costs",
    "datasource",
    "capture",
    "backtest",
    "Profile",
    "get_profile",
    "PROFILES",
]

__version__ = "1.0"
