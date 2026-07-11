"""
sizing.py — Position sizing (`03 §4`).

Pure functions. The binding size is the min of the stake, the notional cap, and the
risk-per-trade cap (when equity is known):

    size_usd = min(stake_usd, max_notional_usd[, risk_per_trade_pct * equity])
    shares   = floor(min(stake_usd, max_notional_usd) / limit_price)

Per the spec note "Shares: shares = floor(min(stake_usd, max_notional_usd) /
limit_price)" — shares use the stake/notional pair; the risk cap further bounds the
USD committed when equity is known.

Also provides the fractional-Kelly helper and the `w <= p ⇒ do-not-trade` guard:

    b = (1 - p) / p
    f* = w - (1 - w)/b = (w*b - (1-w)) / b
    if w <= p ⇒ f* <= 0 ⇒ do not trade.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .config import Profile


@dataclass(frozen=True)
class SizeResult:
    size_usd: float
    shares: int
    do_not_trade: bool = False
    reason: Optional[str] = None


def kelly_fraction(p: float, w: float) -> float:
    """Full-Kelly fraction for a binary buy at ask `p` with win prob `w`.

    b = (1-p)/p (odds), loss-if-lose = 1. f* = w - (1-w)/b.
    Returns f* (can be <= 0 ⇒ do not trade). Edge cases (p<=0 or p>=1) ⇒ 0.
    """
    if p <= 0.0 or p >= 1.0:
        return 0.0
    b = (1.0 - p) / p
    if b <= 0:
        return 0.0
    return w - (1.0 - w) / b


def fractional_kelly(p: float, w: float, fraction: float = 0.25) -> float:
    """Fractional Kelly (default 1/4 Kelly per `03 §4`). Floors negative to 0."""
    f = kelly_fraction(p, w)
    if f <= 0.0:
        return 0.0
    return fraction * f


def do_not_trade(p: float, w: float) -> bool:
    """`w <= p ⇒ f* <= 0 ⇒ do not trade` guard (`03 §4`)."""
    return w <= p


def size_position(
    limit_price: float,
    profile: Profile,
    equity_usd: Optional[float] = None,
    win_prob: Optional[float] = None,
) -> SizeResult:
    """Compute size_usd and shares for an entry at `limit_price`.

    `win_prob`, when supplied, activates the do-not-trade guard against the
    entry price (`w <= p`). `equity_usd` (or `profile.equity_usd`) activates the
    per-trade risk cap.
    """
    if limit_price is None or limit_price <= 0.0:
        return SizeResult(0.0, 0, do_not_trade=True, reason="invalid_price")

    equity = equity_usd if equity_usd is not None else profile.equity_usd

    # do-not-trade guard: if win prob known and w <= p, refuse.
    if win_prob is not None and do_not_trade(limit_price, win_prob):
        return SizeResult(0.0, 0, do_not_trade=True, reason="kelly_nonpositive")

    # USD caps
    caps = [profile.stake_usd, profile.max_notional_usd]
    if equity is not None:
        caps.append(equity * profile.risk_per_trade_pct_equity / 100.0)
    size_usd = min(caps)
    if size_usd <= 0.0:
        return SizeResult(0.0, 0, do_not_trade=True, reason="zero_size")

    # shares per the spec formula: floor(min(stake, notional) / price)
    share_budget = min(profile.stake_usd, profile.max_notional_usd)
    # the risk cap also bounds the actual committed USD
    if equity is not None:
        share_budget = min(share_budget, equity * profile.risk_per_trade_pct_equity / 100.0)
    shares = int(math.floor(share_budget / limit_price))

    if shares <= 0:
        return SizeResult(0.0, 0, do_not_trade=True, reason="below_one_share")

    return SizeResult(size_usd=round(size_usd, 6), shares=shares, do_not_trade=False)
