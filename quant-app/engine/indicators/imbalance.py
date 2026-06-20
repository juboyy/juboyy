"""
imbalance — order-book imbalance (`04 §5`).

    imbalance = (bid_notional - ask_notional) / (bid_notional + ask_notional)  in [-1,1]
    imbalance_score = clamp((imbalance + 1) / 2, 0, 1)
    side check: if imbalance opposes the candidate side strongly
                (< imbalance_veto, default -0.6) ⇒ subscore 0.

When depth data is unavailable, imbalance_score = 0.5 (neutral) and imbalance =
None. The "opposes the candidate side" check: a positive imbalance favours buy
pressure on the long (chosen) side. If the chosen side is DOWN, buy pressure on the
UP book is adverse, so the signed imbalance is interpreted relative to the
candidate side: for a DOWN candidate the effective imbalance is negated before the
veto test.
"""

from __future__ import annotations

from typing import Dict, Optional

from ._common import clamp, UP, DOWN


def imbalance(
    bid_notional_usd: Optional[float],
    ask_notional_usd: Optional[float],
    candidate_side: Optional[str] = None,
    imbalance_veto: float = -0.6,
) -> Dict[str, object]:
    if bid_notional_usd is None or ask_notional_usd is None:
        # neutral when depth is unavailable
        return {"imbalance": None, "imbalance_score": 0.5}

    total = bid_notional_usd + ask_notional_usd
    if total <= 0:
        return {"imbalance": None, "imbalance_score": 0.5}

    imb = (bid_notional_usd - ask_notional_usd) / total
    imb = clamp(imb, -1.0, 1.0)

    # interpret relative to the candidate side: buy pressure helps the long side.
    effective = imb
    if candidate_side == DOWN:
        effective = -imb

    if effective < imbalance_veto:
        score = 0.0
    else:
        score = clamp((effective + 1.0) / 2.0, 0.0, 1.0)

    return {"imbalance": imb, "imbalance_score": score}
