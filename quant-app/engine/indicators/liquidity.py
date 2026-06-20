"""
liquidity — spread / liquidity quality (`04 §4`).

    spread_ok  = min_spread <= skip_if_spread_gt
    notional_ok = top_ask_notional_usd >= skip_if_top_ask_notional_usd_lt
    spread_score = clamp((skip_if_spread_gt - min_spread) /
                         (skip_if_spread_gt - spread_ref), 0, 1)
    depth_score  = clamp(top_ask_notional_usd / notional_ref, 0, 1)
    liquidity_score = 0.5*spread_score + 0.5*depth_score

Null handling: a missing input makes its gate False and its score 0 (and the
overall score is the average of whatever is computable; a fully-missing input pair
yields score None which the Signal Engine treats as a failed gate).
"""

from __future__ import annotations

from typing import Dict, Optional

from ._common import clamp


def liquidity(
    min_spread: Optional[float],
    top_ask_notional_usd: Optional[float],
    skip_if_spread_gt: float = 0.03,
    skip_if_top_ask_notional_usd_lt: float = 30.0,
    spread_ref: float = 0.005,
    notional_ref: float = 100.0,
) -> Dict[str, object]:
    if min_spread is None or top_ask_notional_usd is None:
        return {
            "spread_ok": False if min_spread is None else (min_spread <= skip_if_spread_gt),
            "notional_ok": False if top_ask_notional_usd is None
            else (top_ask_notional_usd >= skip_if_top_ask_notional_usd_lt),
            "liquidity_score": None,
        }

    spread_ok = min_spread <= skip_if_spread_gt
    notional_ok = top_ask_notional_usd >= skip_if_top_ask_notional_usd_lt

    denom = skip_if_spread_gt - spread_ref
    spread_score = clamp((skip_if_spread_gt - min_spread) / denom, 0.0, 1.0) if denom > 0 else (
        1.0 if min_spread <= spread_ref else 0.0
    )
    depth_score = clamp(top_ask_notional_usd / notional_ref, 0.0, 1.0) if notional_ref > 0 else 0.0
    liquidity_score = 0.5 * spread_score + 0.5 * depth_score

    return {
        "spread_ok": spread_ok,
        "notional_ok": notional_ok,
        "liquidity_score": liquidity_score,
    }
