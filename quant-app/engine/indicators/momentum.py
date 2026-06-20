"""
momentum — BTC interval momentum / move (`04 §1`).

Pure function of the open and current BTC spot price.

    btc_move_usd = btc_price_now - btc_price_open
    side = UP if btc_move_usd > 0 else (DOWN if < 0 else null)
    momentum_score = clamp((|btc_move_usd| - min) / (max_ref - min), 0, 1)

Null handling: if either price is missing, all outputs are null and the momentum
gate fails.
"""

from __future__ import annotations

from typing import Dict, Optional

from ._common import clamp, UP, DOWN


def momentum(
    btc_price_open: Optional[float],
    btc_price_now: Optional[float],
    btc_move_usd_min: float = 70.0,
    btc_move_usd_max_reference: float = 100.0,
) -> Dict[str, object]:
    if btc_price_open is None or btc_price_now is None:
        return {"btc_move_usd": None, "momentum_side": None, "momentum_score": None}

    move = btc_price_now - btc_price_open
    if move > 0:
        side: Optional[str] = UP
    elif move < 0:
        side = DOWN
    else:
        side = None

    denom = btc_move_usd_max_reference - btc_move_usd_min
    if denom <= 0:
        # degenerate config: any move at/above floor scores 1, else 0
        score = 1.0 if abs(move) >= btc_move_usd_min else 0.0
    else:
        score = clamp((abs(move) - btc_move_usd_min) / denom, 0.0, 1.0)

    return {
        "btc_move_usd": move,
        "momentum_side": side,
        "momentum_score": score,
    }
