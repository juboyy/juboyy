"""portfolio — capital allocation + portfolio-level risk for the runtime.

Two pieces:
  * :class:`~portfolio.allocator.CapitalAllocator` splits a bankroll across
    strategies by weight (bounded by per-strategy caps).
  * :class:`~portfolio.risk_portfolio.PortfolioRisk` is the global veto layer:
    a daily-loss cap, per-strategy daily-loss caps, a max concurrent exposure
    cap, and a global kill flag.

Both compose the spirit of ``engine/risk.py`` and ``engine/sizing.py`` without
duplicating their internals.
"""

from __future__ import annotations

from .allocator import CapitalAllocator
from .risk_portfolio import PortfolioRisk, PortfolioState

__all__ = ["CapitalAllocator", "PortfolioRisk", "PortfolioState"]
