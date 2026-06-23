"""portfolio/allocator.py — split a bankroll across strategies by weight.

``CapitalAllocator(bankroll_usd, weights)`` turns a global bankroll into a
per-strategy USD budget. Weights are normalized (they need not sum to 1). An
optional per-strategy ``caps`` dict bounds any single strategy's budget — the
same "binding cap is the min" idea as ``engine/sizing.py`` (size = min(stake,
notional, risk-cap)). :meth:`rebalance` swaps in new weights/bankroll at runtime.

Pure, stdlib-only, no I/O.
"""

from __future__ import annotations

from typing import Dict, Optional


class CapitalAllocator:
    """Allocate ``bankroll_usd`` across strategies by normalized ``weights``.

    ``budget_for(name)`` returns ``bankroll * weight_name / sum(weights)``, then
    clamps to ``caps[name]`` when a cap is set (mirrors the min-of-caps sizing
    rule in ``engine/sizing.py``). Unknown strategy names get ``0.0``.
    """

    def __init__(
        self,
        bankroll_usd: float,
        weights: Dict[str, float],
        *,
        caps: Optional[Dict[str, float]] = None,
    ) -> None:
        if bankroll_usd < 0:
            raise ValueError("bankroll_usd must be non-negative")
        self.bankroll_usd = float(bankroll_usd)
        self._weights: Dict[str, float] = {k: float(v) for k, v in weights.items()}
        self._caps: Dict[str, float] = dict(caps or {})

    @property
    def weights(self) -> Dict[str, float]:
        return dict(self._weights)

    @property
    def caps(self) -> Dict[str, float]:
        return dict(self._caps)

    def _weight_sum(self) -> float:
        # Only positive weights contribute to the denominator.
        return sum(w for w in self._weights.values() if w > 0.0)

    def budget_for(self, strategy_name: str) -> float:
        """USD budget for ``strategy_name`` (weight-share, clamped by any cap)."""
        w = self._weights.get(strategy_name, 0.0)
        total = self._weight_sum()
        if w <= 0.0 or total <= 0.0:
            return 0.0
        raw = self.bankroll_usd * (w / total)
        cap = self._caps.get(strategy_name)
        if cap is not None:
            raw = min(raw, float(cap))
        return round(max(0.0, raw), 6)

    def budgets(self) -> Dict[str, float]:
        """Budget for every weighted strategy."""
        return {name: self.budget_for(name) for name in self._weights}

    def rebalance(
        self,
        *,
        bankroll_usd: Optional[float] = None,
        weights: Optional[Dict[str, float]] = None,
        caps: Optional[Dict[str, float]] = None,
    ) -> "CapitalAllocator":
        """Update bankroll / weights / caps in place; returns self for chaining."""
        if bankroll_usd is not None:
            if bankroll_usd < 0:
                raise ValueError("bankroll_usd must be non-negative")
            self.bankroll_usd = float(bankroll_usd)
        if weights is not None:
            self._weights = {k: float(v) for k, v in weights.items()}
        if caps is not None:
            self._caps = dict(caps)
        return self
