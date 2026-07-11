"""
indicators — pure deterministic feature functions (`docs/04_INDICATORS.md`).

Every function here is pure: same input ⇒ same output, no I/O, no clock reads
(time enters as `seconds_left`/`ts` parameters). `null`/missing input ⇒ the
indicator returns `null` for its score and the relevant gate fails (the staleness
gate / Signal Engine treats `null` subscores as failing gates).

`compute(snapshot, history, profile)` runs them all and assembles a `Features`.
"""

from __future__ import annotations

from typing import List, Optional

from ..contracts import Features, MarketSnapshot
from ..config import Profile
from .momentum import momentum
from .realized_vol import realized_vol
from .skew import skew
from .liquidity import liquidity
from .imbalance import imbalance
from .time_decay import time_decay
from .staleness import staleness

__all__ = [
    "momentum",
    "realized_vol",
    "skew",
    "liquidity",
    "imbalance",
    "time_decay",
    "staleness",
    "compute",
]


def compute(
    snapshot: MarketSnapshot,
    history: Optional[List[MarketSnapshot]] = None,
    profile: Optional[Profile] = None,
) -> Features:
    """Run all indicators and assemble a `Features` object (`05 §2`).

    `history` is the last `lookback_polls` snapshots (oldest→newest), used by
    `realized_vol`. The candidate `side` for the imbalance check comes from
    momentum. Everything is a pure function of the passed arguments.
    """
    if profile is None:
        profile = Profile()
    history = history or []

    mom = momentum(
        snapshot.btc_price_open,
        snapshot.btc_price_now,
        btc_move_usd_min=profile.btc_move_usd_min,
        btc_move_usd_max_reference=profile.btc_move_usd_max_reference,
    )

    prices = [s.btc_price_now for s in history]
    # ensure the current snapshot's price is included as the newest point
    if snapshot.btc_price_now is not None:
        prices = prices + [snapshot.btc_price_now]
    rv = realized_vol(
        prices,
        rv_window=profile.rv_window,
        rv_cap_usd=profile.rv_cap_usd,
        poll_sec=profile.poll_sec,
        entry_window_target_sec=profile.entry_window_target_sec,
    )

    sk = skew(
        snapshot.clob_up_ask,
        snapshot.clob_down_ask,
        snapshot.gamma_up,
        snapshot.gamma_down,
        skew_score_cap=profile.skew_score_cap,
    )

    liq = liquidity(
        snapshot.min_spread,
        snapshot.top_ask_notional_usd,
        skip_if_spread_gt=profile.skip_if_spread_gt,
        skip_if_top_ask_notional_usd_lt=profile.skip_if_top_ask_notional_usd_lt,
        spread_ref=profile.spread_ref,
        notional_ref=profile.notional_ref,
    )

    imb = imbalance(
        snapshot.top_bid_notional_usd,
        snapshot.top_ask_notional_usd,
        candidate_side=mom["momentum_side"],
        imbalance_veto=profile.imbalance_veto,
    )

    td = time_decay(
        snapshot.seconds_left,
        min_entry_seconds_left=profile.min_entry_seconds_left,
        entry_window_target_sec=profile.entry_window_target_sec,
        entry_window_tolerance_sec=profile.entry_window_tolerance_sec,
    )

    st = staleness(
        snapshot.age_sec,
        running=True,
        skip_if_quote_stale_sec_gt=profile.skip_if_quote_stale_sec_gt,
        dead_man_sec=profile.dead_man_sec,
    )

    return Features(
        ts=snapshot.ts,
        btc_move_usd=mom["btc_move_usd"],
        momentum_side=mom["momentum_side"],
        momentum_score=mom["momentum_score"],
        rv_usd=rv["rv_usd"],
        rv_score=rv["rv_score"],
        skew_clob=sk["skew_clob"],
        skew_gamma=sk["skew_gamma"],
        skew_side=sk["skew_side"],
        skew_agree=sk["skew_agree"],
        skew_score=sk["skew_score"],
        spread_ok=liq["spread_ok"],
        notional_ok=liq["notional_ok"],
        liquidity_score=liq["liquidity_score"],
        imbalance=imb["imbalance"],
        imbalance_score=imb["imbalance_score"],
        in_window=td["in_window"],
        time_decay_score=td["time_decay_score"],
        seconds_left=td["seconds_left"],
        fresh=st["fresh"],
        process_ok=st["process_ok"],
        dead_man_tripped=st["dead_man_tripped"],
        health_score=st["health_score"],
    )
