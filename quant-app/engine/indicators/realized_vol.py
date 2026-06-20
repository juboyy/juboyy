"""
realized_vol — realized volatility context (`04 §2`).

    per-poll returns r_i = price_i - price_{i-1}   (USD)
    rv_usd = stdev(r_i) * sqrt(N_polls_per_interval)
    rv_score = clamp(rv_usd / rv_cap_usd, 0, 1)

`N_polls_per_interval` scales the per-poll sigma up to the interval horizon; it is
derived deterministically from `entry_window_target_sec / poll_sec` (e.g.
120/5 = 24). Needs >= 8 price points (>= 2 returns and enough to be meaningful);
fewer ⇒ rv_usd/rv_score are null and the score term is treated as neutral by the
Signal Engine penalty (a null rv_score contributes no penalty).

Stdlib only: uses `statistics.pstdev`? No — uses the sample stdev `statistics.stdev`
to match "stdev(r_i)". Pure function.
"""

from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional

from ._common import clamp

MIN_POINTS = 8


def realized_vol(
    prices: List[Optional[float]],
    rv_window: int = 24,
    rv_cap_usd: float = 150.0,
    poll_sec: int = 5,
    entry_window_target_sec: int = 120,
) -> Dict[str, object]:
    # keep only the most recent rv_window points; drop missing values
    clean = [p for p in prices if p is not None]
    if rv_window and rv_window > 0:
        clean = clean[-rv_window:]

    if len(clean) < MIN_POINTS:
        return {"rv_usd": None, "rv_score": None}

    returns = [clean[i] - clean[i - 1] for i in range(1, len(clean))]
    if len(returns) < 2:
        return {"rv_usd": None, "rv_score": None}

    sigma = statistics.stdev(returns)
    n_polls = max(1, int(round(entry_window_target_sec / poll_sec))) if poll_sec else 1
    rv_usd = sigma * math.sqrt(n_polls)
    rv_score = clamp(rv_usd / rv_cap_usd, 0.0, 1.0) if rv_cap_usd > 0 else 0.0

    return {"rv_usd": rv_usd, "rv_score": rv_score}
