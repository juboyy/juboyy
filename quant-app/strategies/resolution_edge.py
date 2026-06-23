"""strategies/resolution_edge.py — convex resolution-edge strategy (human-gated).

This strategy is the runtime consumer of the OFFLINE scanner's output. The
scanner (``scanner.scan``) writes a ``watchlist.jsonl`` of gate-passing convex
``WatchlistItem`` records (cheap longshots whose resolution criteria look
misread-able with positive edge net of costs). This strategy reads that file and,
in :meth:`propose`, emits an ``enter`` :class:`~engine.contracts.Decision` for the
top flagged outcome, sized to its per-strategy USD budget.

Human gating (the core safety property):
  * The proposal is marked ``approval_required`` whenever the strategy runs in a
    mode other than ``"paper"`` (i.e. a live/armed adapter would route it). The
    supervisor/owner must explicitly confirm before such a Decision routes to a
    live adapter.
  * In ``"paper"`` (dry-run, the default) ``approval_required`` is False so the
    proposal auto-routes in simulation.

The ``approval_required`` flag is attached as an attribute on the returned
Decision (the canonical :class:`Decision` dataclass is shared/normative, so we do
not add a field to it) AND reflected in ``risk_verdict``/``reason`` so it is
visible in the logged record.

Invariants:
  * No LLM, no network here. The watchlist was produced offline/advisory; this
    path only reads a local JSONL file (injectable for tests).
  * No key material. Slow cadence (default 300s) — resolution edges are not
    high-frequency.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List, Optional

from engine.contracts import Decision

from .base import Strategy, StrategyContext

DEFAULT_WATCHLIST_NAME = "watchlist.jsonl"
DEFAULT_CADENCE_SEC = 300.0


class ResolutionEdgeStrategy(Strategy):
    """Propose an ``enter`` on the top flagged convex outcome from the watchlist.

    Construction:
      * ``watchlist_path`` — explicit path to the scanner's ``watchlist.jsonl``
        (injected in tests). If omitted, ``<runtime_dir>/watchlist.jsonl``.
      * ``runtime_dir`` — directory holding the watchlist (default ``"runtime"``).
      * ``mode`` — ``"paper"`` (default) auto-routes; anything else marks the
        proposal ``approval_required`` (human-gated).
      * ``min_convex_score`` — a floor below which nothing is proposed even if the
        scanner flagged it (defence-in-depth; the scanner already gates).
    """

    name = "resolution_edge"
    cadence_sec = DEFAULT_CADENCE_SEC

    def __init__(
        self,
        *,
        name: str = "resolution_edge",
        mode: str = "paper",
        watchlist_path: Optional[str] = None,
        runtime_dir: str = "runtime",
        min_convex_score: float = 0.0,
        max_proposals: int = 1,
    ) -> None:
        self.name = name
        self.mode = mode
        self.min_convex_score = float(min_convex_score)
        self.max_proposals = int(max_proposals)
        if watchlist_path is not None:
            self._watchlist_path = Path(watchlist_path)
        else:
            self._watchlist_path = Path(runtime_dir) / DEFAULT_WATCHLIST_NAME

    def data_needs(self):
        # This strategy is driven by the watchlist file, not the live snapshot.
        return set()

    # -- watchlist loading (the only I/O; reads a local JSONL) -------------
    def _load_watchlist(self) -> List[dict]:
        path = self._watchlist_path
        if not path.exists():
            return []
        items: List[dict] = []
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue  # skip malformed lines, never crash the runtime
                if isinstance(obj, dict) and "candidate" in obj and "signal" in obj:
                    items.append(obj)
        return items

    @staticmethod
    def _shares_for_budget(budget_usd: float, price: float) -> int:
        if price <= 0:
            return 0
        return int(math.floor(budget_usd / price))

    def propose(self, ctx: StrategyContext) -> List[Decision]:
        items = self._load_watchlist()
        if not items:
            return []

        # The scanner already ranks by convex_score desc; keep only true
        # gate-passers above our floor, preserving the file's order.
        flagged = [
            it
            for it in items
            if it.get("signal", {}).get("pass_gates")
            and float(it.get("signal", {}).get("convex_score", 0.0)) >= self.min_convex_score
        ]
        if not flagged:
            return []

        approval_required = ctx.mode != "paper"
        budget = float(ctx.budget_usd or 0.0)

        decisions: List[Decision] = []
        for it in flagged[: self.max_proposals]:
            cand = it.get("candidate", {})
            signal = it.get("signal", {})
            price = float(cand.get("price", 0.0))
            shares = self._shares_for_budget(budget, price)
            if shares <= 0:
                continue
            size_usd = round(shares * price, 6)
            note = (
                f"resolution_edge: convex_score={signal.get('convex_score')} "
                f"edge={signal.get('edge')} outcome={cand.get('outcome')!r}"
            )
            dec = Decision(
                ts=ctx.snapshot.ts if ctx.snapshot is not None else None,
                market_slug=cand.get("market_slug"),
                action="enter",
                side=cand.get("outcome"),
                limit_price=price,
                size_usd=size_usd,
                shares=shares,
                reason=note + (" [APPROVAL REQUIRED]" if approval_required else ""),
                risk_verdict="veto" if approval_required else "allow",
                risk_reason="approval_required" if approval_required else None,
                mode=ctx.mode,
            )
            # Attach the human-gating flag for the supervisor to honor. The shared
            # Decision dataclass is normative, so we carry this out-of-band.
            dec.approval_required = approval_required  # type: ignore[attr-defined]
            decisions.append(dec)
        return decisions
