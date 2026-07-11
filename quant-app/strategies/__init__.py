"""strategies — pluggable trading strategies for the multi-strategy runtime.

Each strategy is a pure-ish proposer: given a :class:`~strategies.base.StrategyContext`
(latest snapshot, recent history, profile, per-strategy USD budget, mode) it returns
a list of engine :class:`~engine.contracts.Decision` objects. Strategies never route
orders themselves and never touch keys — the :mod:`supervisor` owns execution.

PHASE 0 ships the base contract plus :class:`~strategies.btc_momentum.BtcMomentumStrategy`,
which wraps the existing deterministic engine read-only.
"""

from __future__ import annotations

from .base import Strategy, StrategyContext

__all__ = ["Strategy", "StrategyContext"]
