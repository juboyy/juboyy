"""portfolio/risk_portfolio.py — portfolio-level risk veto layer.

``engine/risk.py`` enforces caps for a *single* BTC-5m strategy via
``apply(state, profile, …) -> Allowance``. ``PortfolioRisk`` lifts that idea to
the *portfolio*: it vetoes a strategy's decision when

  * the global kill flag is set, or
  * the GLOBAL daily-loss cap (USD) is hit, or
  * that strategy's per-strategy daily-loss cap is hit, or
  * routing it would exceed the max concurrent exposure cap.

It reuses the engine's :class:`~engine.risk.Allowance` value object (same
``allowed``/``reason`` shape) rather than reinventing it. Pure, stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Reuse the engine's Allowance contract verbatim (compose, don't duplicate).
from engine.risk import Allowance
from engine.contracts import Decision


@dataclass
class PortfolioState:
    """Live portfolio accounting the veto layer reads.

    ``pnl_today`` is the global realized P&L for the day (USD; negative = loss).
    ``pnl_today_by_strategy`` is the same per strategy. ``open_exposure_usd`` is
    the total USD currently committed across open positions. ``killed`` mirrors
    the global :class:`~crypto.safety.KillSwitch`.
    """

    pnl_today: float = 0.0
    pnl_today_by_strategy: Dict[str, float] = field(default_factory=dict)
    open_exposure_usd: float = 0.0
    killed: bool = False


class PortfolioRisk:
    """Global + per-strategy risk caps with a hard global kill.

    Caps are expressed as positive USD magnitudes; a cap "binds" when the
    relevant loss has reached (≤ −cap) that magnitude. ``approve`` is the single
    entry point the supervisor calls per candidate decision.
    """

    def __init__(
        self,
        *,
        global_daily_loss_cap_usd: Optional[float] = None,
        per_strategy_daily_loss_cap_usd: Optional[Dict[str, float]] = None,
        max_concurrent_exposure_usd: Optional[float] = None,
        killed: bool = False,
    ) -> None:
        self.global_daily_loss_cap_usd = (
            abs(global_daily_loss_cap_usd) if global_daily_loss_cap_usd is not None else None
        )
        self.per_strategy_daily_loss_cap_usd: Dict[str, float] = {
            k: abs(v) for k, v in (per_strategy_daily_loss_cap_usd or {}).items()
        }
        self.max_concurrent_exposure_usd = (
            abs(max_concurrent_exposure_usd) if max_concurrent_exposure_usd is not None else None
        )
        self._killed = bool(killed)

    # -- global kill --------------------------------------------------------
    @property
    def killed(self) -> bool:
        return self._killed

    def kill(self, reason: str = "operator_kill") -> None:
        self._killed = True
        self.kill_reason = reason

    def reset_kill(self) -> None:
        self._killed = False

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _decision_exposure_usd(decision: Decision) -> float:
        size = getattr(decision, "size_usd", None)
        if size is None:
            return 0.0
        try:
            return abs(float(size))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _is_entry(decision: Decision) -> bool:
        # Only entries add exposure / consume budget. Exits/holds always pass the
        # exposure check (closing risk is allowed even when capped).
        return getattr(decision, "action", None) in {"enter", "hedge"}

    # -- the veto -----------------------------------------------------------
    def approve(
        self,
        strategy_name: str,
        decision: Decision,
        state: PortfolioState,
    ) -> Allowance:
        """Decide whether ``decision`` from ``strategy_name`` may be routed.

        Order is the audit order; the first failing check wins. Returns the
        engine :class:`Allowance` (``allowed``/``reason``). ``reason`` vocabulary:
        ``global_kill`` | ``global_daily_loss_cap`` | ``strategy_daily_loss_cap``
        | ``max_concurrent_exposure``.
        """
        # 1. Global kill (also honor a kill recorded on the state).
        if self._killed or state.killed:
            return Allowance(False, "global_kill")

        # 2. Global daily-loss cap.
        if (
            self.global_daily_loss_cap_usd is not None
            and state.pnl_today <= -self.global_daily_loss_cap_usd
        ):
            return Allowance(False, "global_daily_loss_cap")

        # 3. Per-strategy daily-loss cap.
        strat_cap = self.per_strategy_daily_loss_cap_usd.get(strategy_name)
        if strat_cap is not None:
            strat_pnl = state.pnl_today_by_strategy.get(strategy_name, 0.0)
            if strat_pnl <= -strat_cap:
                return Allowance(False, "strategy_daily_loss_cap")

        # 4. Max concurrent exposure (only entries add exposure).
        if self.max_concurrent_exposure_usd is not None and self._is_entry(decision):
            projected = state.open_exposure_usd + self._decision_exposure_usd(decision)
            if projected > self.max_concurrent_exposure_usd:
                return Allowance(False, "max_concurrent_exposure")

        return Allowance(True, None)
