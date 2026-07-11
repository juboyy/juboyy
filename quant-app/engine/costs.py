"""
costs.py — Cost model (`03 §8`).

Pure functions. For each simulated/real trade:

    slippage_usdc = shares * slip_ticks * tick      (default slip_ticks=1, tick=0.01)
    gas_usdc      = profile.gas_usdc per on-chain action (open and close)
    fees_usdc     = fee_bps/10000 * notional         (default fee_bps=0)

Canonical net P&L (`03 §8`):

    realized_cashflow_pnl_usdc = settlement_or_exit_cashflow
                                 - cost_basis - slippage - gas - fees

For a binary buy of `shares` at `entry_price`:
    cost_basis = shares * entry_price
    settlement cashflow on WIN  = shares * 1.0
    settlement cashflow on LOSS = 0.0
    exit cashflow (early close) = shares * exit_price

Gas is charged per action: 1 action for a settled trade (open only — settlement is
on-chain resolution, not a trade we send), 2 actions for an explicitly-closed trade
(open + close). This is configurable via `n_gas_actions`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import Profile


@dataclass(frozen=True)
class CostBreakdown:
    cost_basis_usdc: float
    slippage_usdc: float
    gas_usdc: float
    fees_usdc: float
    gross_cashflow_usdc: float
    realized_cashflow_pnl_usdc: float
    result: str  # win|loss|breakeven


def slippage(shares: int, profile: Profile) -> float:
    return round(shares * profile.slip_ticks * profile.tick, 6)


def gas(profile: Profile, n_actions: int = 1) -> float:
    return round(profile.gas_usdc * n_actions, 6)


def fees(notional_usdc: float, profile: Profile) -> float:
    return round(notional_usdc * profile.fee_bps / 10000.0, 6)


def compute_costs(
    shares: int,
    entry_price: float,
    won: bool,
    profile: Profile,
    exit_price: Optional[float] = None,
    n_gas_actions: int = 1,
) -> CostBreakdown:
    """Compute the full cost breakdown + canonical net P&L for one trade.

    If `exit_price` is provided the trade was closed early (exit cashflow =
    shares*exit_price, default 2 gas actions). Otherwise it settles binary
    (cashflow = shares on win else 0, default 1 gas action).
    """
    cost_basis = shares * entry_price
    notional = cost_basis

    if exit_price is not None:
        gross_cashflow = shares * exit_price
        if n_gas_actions == 1:
            n_gas_actions = 2  # open + close by default for an early exit
    else:
        gross_cashflow = shares * 1.0 if won else 0.0

    slip = slippage(shares, profile)
    g = gas(profile, n_gas_actions)
    f = fees(notional, profile)

    net = gross_cashflow - cost_basis - slip - g - f
    net = round(net, 6)

    if net > 0:
        result = "win"
    elif net < 0:
        result = "loss"
    else:
        result = "breakeven"

    return CostBreakdown(
        cost_basis_usdc=round(cost_basis, 6),
        slippage_usdc=slip,
        gas_usdc=g,
        fees_usdc=f,
        gross_cashflow_usdc=round(gross_cashflow, 6),
        realized_cashflow_pnl_usdc=net,
        result=result,
    )


def cost_adjusted_breakeven(entry_price: float, shares: int, profile: Profile) -> float:
    """The win rate `w` an entry at `entry_price` must clear AFTER costs (`03 §9`).

    Per-trade EV(w) = w*(shares - cost_basis - costs) + (1-w)*(-cost_basis - costs).
    Solve EV=0 for w:  w = (cost_basis + costs) / shares.
    With shares*price = cost_basis this is price + costs/shares. Costs here are the
    one-trade open-side slippage+gas+fees (settlement, 1 gas action).
    """
    if shares <= 0:
        return entry_price
    cost_basis = shares * entry_price
    slip = slippage(shares, profile)
    g = gas(profile, 1)
    f = fees(cost_basis, profile)
    return (cost_basis + slip + g + f) / shares
