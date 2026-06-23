"""supervisor — the multi-strategy runtime loop.

The :class:`~supervisor.runner.Supervisor` holds the enabled strategies, the
:class:`~portfolio.risk_portfolio.PortfolioRisk` veto layer, the
:class:`~portfolio.allocator.CapitalAllocator`, and a single execution adapter
from :func:`crypto.factory.get_adapter` (Paper by default). It schedules each
strategy on its cadence, runs proposed decisions through portfolio risk + budget,
routes the approved ones to the adapter, and appends events to the unified
runtime log.
"""

from __future__ import annotations

from .runner import Supervisor, TickReport

__all__ = ["Supervisor", "TickReport"]
