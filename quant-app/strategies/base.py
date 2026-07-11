"""strategies/base.py — the Strategy contract + per-tick context.

A :class:`Strategy` is the unit the :mod:`supervisor` schedules. It is a proposer:
it converts market state into a list of engine :class:`~engine.contracts.Decision`
objects. It does **not** size against the portfolio, run risk caps, or route to an
adapter — those are the supervisor's job. This keeps strategies pure-ish and
trivially testable.

Invariants:
  * No LLM, no network, no key material anywhere in this path.
  * ``mode`` defaults to ``"paper"`` (the runtime's word for dry-run); ``"live"`` is
    only meaningful once the supervisor's adapter is live+armed (still gated).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import List, Optional, Set

from engine.config import Profile
from engine.contracts import Decision, Features, MarketSnapshot, Position, TradeResult


@dataclass
class StrategyContext:
    """Everything a strategy needs for one ``propose`` call.

    Carries the latest :class:`MarketSnapshot`, recent ``history`` (oldest→newest,
    as the engine indicators expect), an optional precomputed :class:`Features`
    (so the supervisor can share one computation across strategies with the same
    data needs), the active :class:`Profile`, a per-strategy USD ``budget``, the
    strategy ``mode`` ("paper"|"live"), and any currently ``open_position`` plus a
    ``kill_flag`` so overlay logic (exit/kill) can run. ``btc_spot`` is an optional
    out-of-band spot price for strategies that declare the ``"btc_spot"`` data need.
    """

    snapshot: MarketSnapshot
    profile: Profile
    budget_usd: float
    mode: str = "paper"
    history: List[MarketSnapshot] = field(default_factory=list)
    features: Optional[Features] = None
    open_position: Optional[Position] = None
    kill_flag: bool = False
    btc_spot: Optional[float] = None


class Strategy(abc.ABC):
    """Abstract base for a runtime strategy.

    Subclasses set :attr:`name`, may override :attr:`mode` / :attr:`cadence_sec`,
    declare :meth:`data_needs`, and implement :meth:`propose`. :meth:`on_fill` is
    an optional hook the supervisor calls after a routed order produces a
    :class:`TradeResult`.
    """

    #: Unique, stable strategy name (used for budgets, caps, and log keys).
    name: str = "strategy"
    #: "paper" (dry-run) by default; "live" only honored by a live+armed adapter.
    mode: str = "paper"
    #: Minimum seconds between proposals; the supervisor honors this cadence.
    cadence_sec: float = 5.0

    def data_needs(self) -> Set[str]:
        """Declare what market data this strategy consumes.

        Recognized tokens: ``"snapshot"``, ``"history"``, ``"btc_spot"``. The
        supervisor uses this to decide what to populate on the context. Default:
        just the latest snapshot.
        """
        return {"snapshot"}

    @abc.abstractmethod
    def propose(self, ctx: StrategyContext) -> List[Decision]:
        """Return zero or more :class:`Decision` objects for this tick.

        Return ``[]`` for skip/hold (no actionable order). Must be deterministic
        given ``ctx`` and must not perform I/O.
        """
        raise NotImplementedError

    def on_fill(self, result: TradeResult) -> None:  # pragma: no cover - optional hook
        """Optional: react to a fill the supervisor routed for this strategy."""
        return None
