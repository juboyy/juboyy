"""strategies/btc_momentum.py — BTC 5m momentum strategy (engine wrapper).

This is the first concrete :class:`~strategies.base.Strategy`. It does **not**
reimplement any logic: it WRAPS the existing deterministic engine read-only.

Per tick it:
  1. computes :class:`Features` via ``engine.indicators.compute`` (unless the
     supervisor already supplied a precomputed ``ctx.features``), then
  2. runs ``engine.signal_engine.evaluate_and_decide`` to get a ``(Signal, Decision)``.

It returns ``[Decision]`` for an actionable ``enter``/``exit``/``hedge`` and ``[]``
for ``skip``/``hold``. The engine modules are imported read-only and never mutated.
"""

from __future__ import annotations

from typing import List

from engine import indicators
from engine import signal_engine
from engine.contracts import Decision

from .base import Strategy, StrategyContext

# Engine actions that represent an actionable order to route. ``skip`` and
# ``hold`` are non-actions ⇒ the strategy proposes nothing.
_ACTIONABLE = {"enter", "exit", "hedge"}


class BtcMomentumStrategy(Strategy):
    """Wrap the BTC-5m engine spine as a runtime strategy.

    cadence ~5s (matches the engine's ``poll_sec``); ``mode`` defaults to
    ``"paper"``. Declares the snapshot + history data needs (history feeds the
    realized-vol indicator).
    """

    name = "btc_momentum"
    cadence_sec = 5.0

    def __init__(self, *, name: str = "btc_momentum", mode: str = "paper") -> None:
        self.name = name
        self.mode = mode

    def data_needs(self):
        return {"snapshot", "history"}

    def propose(self, ctx: StrategyContext) -> List[Decision]:
        # Reuse a precomputed Features if the supervisor shared one; else compute.
        features = ctx.features
        if features is None:
            features = indicators.compute(
                ctx.snapshot, history=ctx.history, profile=ctx.profile
            )

        _signal, decision = signal_engine.evaluate_and_decide(
            features,
            ctx.snapshot,
            ctx.profile,
            risk_allows=True,  # portfolio-level risk is applied by the supervisor
            open_position=ctx.open_position,
            kill_flag=ctx.kill_flag,
        )

        if decision.action in _ACTIONABLE:
            return [decision]
        return []
