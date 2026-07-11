"""
skew — market skew, two independent estimates (`04 §3`).

    skew_clob  = max(up_ask, down_ask) / (up_ask + down_ask)        in [0.5, 1]
    skew_clob_side = UP if up_ask >= down_ask else DOWN
    skew_gamma = max(gamma_up, gamma_down) / (gamma_up + gamma_down)
    skew_side  = skew_clob_side    (CLOB is the tradable book; gamma confirms)
    skew_agree = (skew_clob_side == skew_gamma_side)
    skew_score = clamp((skew_clob - 0.5) / (skew_score_cap - 0.5), 0, 1)

Null handling: if CLOB asks are missing/non-positive sum ⇒ skew_clob/side/score are
null (skew gate fails). If gamma is missing, gamma fields + agreement are null but
CLOB-side outputs still compute.
"""

from __future__ import annotations

from typing import Dict, Optional

from ._common import clamp, UP, DOWN


def _side(up: float, down: float) -> str:
    return UP if up >= down else DOWN


def skew(
    clob_up_ask: Optional[float],
    clob_down_ask: Optional[float],
    gamma_up: Optional[float],
    gamma_down: Optional[float],
    skew_score_cap: float = 0.95,
) -> Dict[str, object]:
    out: Dict[str, object] = {
        "skew_clob": None,
        "skew_gamma": None,
        "skew_side": None,
        "skew_agree": None,
        "skew_score": None,
    }

    # CLOB skew (tradable book) -------------------------------------------------
    if clob_up_ask is not None and clob_down_ask is not None:
        total = clob_up_ask + clob_down_ask
        if total > 0:
            skew_clob = max(clob_up_ask, clob_down_ask) / total
            clob_side = _side(clob_up_ask, clob_down_ask)
            denom = skew_score_cap - 0.5
            if denom > 0:
                score = clamp((skew_clob - 0.5) / denom, 0.0, 1.0)
            else:
                score = 1.0 if skew_clob > 0.5 else 0.0
            out["skew_clob"] = skew_clob
            out["skew_side"] = clob_side
            out["skew_score"] = score

    # Gamma skew (confirmation) -------------------------------------------------
    gamma_side: Optional[str] = None
    if gamma_up is not None and gamma_down is not None:
        gtotal = gamma_up + gamma_down
        if gtotal > 0:
            out["skew_gamma"] = max(gamma_up, gamma_down) / gtotal
            gamma_side = _side(gamma_up, gamma_down)

    # Agreement only defined when both sides are known
    if out["skew_side"] is not None and gamma_side is not None:
        out["skew_agree"] = out["skew_side"] == gamma_side

    return out
