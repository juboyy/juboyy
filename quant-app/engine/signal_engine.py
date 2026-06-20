"""
signal.py — Signal Engine (`04 §8`, `05 §3/§4`).

Pure deterministic spine: `Features → Signal → Decision`.

Step 1 — hard gates (all must pass, else Decision=skip, reason=first failed gate).
Step 2 — weighted composite score (only if gates pass).
Step 3 — decision (enter/hold/skip) plus overlays (stop_loss / time_exit / hedge /
          kill) that are independent of the enter path.

The `Signal` carries every subscore, the passed/failed gate list, the weights and
the score breakdown so a UI can reconstruct "why". No I/O, no clock reads.
`risk.allows` enters as a precomputed boolean (`risk.apply`) so this module stays a
pure function of its arguments.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .contracts import Decision, Features, MarketSnapshot, Position, Signal
from .config import Profile
from .indicators._common import clamp, UP, DOWN
from . import sizing as sizing_mod

# Gate evaluation order == audit order; `failed_gate` is the first False here.
GATE_ORDER = [
    "health",
    "in_window",
    "momentum_present",
    "spread_ok",
    "notional_ok",
    "skew_agreement",
    "ask_ge_threshold",
    "ask_le_max",
    "risk_allows",
]


def _chosen_side_ask(features: Features, snapshot: MarketSnapshot, side: Optional[str]) -> Optional[float]:
    if side == UP:
        return snapshot.clob_up_ask
    if side == DOWN:
        return snapshot.clob_down_ask
    return None


def evaluate(
    features: Features,
    snapshot: MarketSnapshot,
    profile: Profile,
    risk_allows: bool = True,
) -> Signal:
    """Step 1 + Step 2 → `Signal` (`05 §3`).

    `risk_allows` is the boolean verdict of `risk.apply` (kept external so this is a
    pure function). The chosen side is the momentum side (which must equal the skew
    side for the agreement gate to pass).
    """
    chosen_side = features.momentum_side
    chosen_ask = _chosen_side_ask(features, snapshot, chosen_side)

    # ---- Step 1: hard gates -------------------------------------------------
    health = bool(features.fresh) and bool(features.process_ok)
    in_window = bool(features.in_window)

    momentum_present = (
        features.btc_move_usd is not None
        and abs(features.btc_move_usd) >= profile.btc_move_usd_min
    )

    spread_ok = bool(features.spread_ok)
    notional_ok = bool(features.notional_ok)

    skew_agreement = (
        features.momentum_side is not None
        and features.skew_side is not None
        and features.momentum_side == features.skew_side
    )

    ask_ge_threshold = chosen_ask is not None and chosen_ask >= profile.threshold_price
    ask_le_max = chosen_ask is not None and chosen_ask <= profile.max_entry_ask

    gates = {
        "health": health,
        "in_window": in_window,
        "momentum_present": momentum_present,
        "spread_ok": spread_ok,
        "notional_ok": notional_ok,
        "skew_agreement": skew_agreement,
        "ask_ge_threshold": ask_ge_threshold,
        "ask_le_max": ask_le_max,
        "risk_allows": bool(risk_allows),
    }

    failed_gate: Optional[str] = None
    for g in GATE_ORDER:
        if not gates[g]:
            failed_gate = g
            break
    gates_passed = failed_gate is None

    # ---- Step 2: weighted composite score (only if gates pass) -------------
    subscores: Dict[str, Optional[float]] = {
        "momentum_score": features.momentum_score,
        "skew_score": features.skew_score,
        "liquidity_score": features.liquidity_score,
        "imbalance_score": features.imbalance_score,
        "time_decay_score": features.time_decay_score,
        "rv_penalty": None,
        "agreement_bonus": 0.0,
    }
    weights = {
        "w_mom": profile.w_mom,
        "w_skew": profile.w_skew,
        "w_liq": profile.w_liq,
        "w_imb": profile.w_imb,
        "w_time": profile.w_time,
        "w_vol": profile.w_vol,
    }

    total_score: Optional[float] = None
    if gates_passed:
        mom = features.momentum_score or 0.0
        sk = features.skew_score or 0.0
        liq = features.liquidity_score or 0.0
        imb = features.imbalance_score if features.imbalance_score is not None else 0.5
        td = features.time_decay_score or 0.0
        rv = features.rv_score or 0.0  # null rv ⇒ no penalty

        raw = (
            profile.w_mom * mom
            + profile.w_skew * sk
            + profile.w_liq * liq
            + profile.w_imb * imb
            + profile.w_time * td
        )
        rv_penalty = profile.w_vol * rv
        vol_adj = 1.0 - rv_penalty
        agreement_bonus = profile.agreement_bonus if features.skew_agree else 0.0

        total_score = clamp(raw * vol_adj + agreement_bonus, 0.0, 1.0)

        subscores["imbalance_score"] = imb
        subscores["rv_penalty"] = round(rv_penalty, 6)
        subscores["agreement_bonus"] = agreement_bonus

    return Signal(
        ts=features.ts,
        market_slug=snapshot.market_slug,
        chosen_side=chosen_side,
        chosen_side_ask=chosen_ask,
        total_score=round(total_score, 6) if total_score is not None else None,
        enter_score_min=profile.enter_score_min,
        subscores=subscores,
        weights=weights,
        gates=gates,
        gates_passed=gates_passed,
        failed_gate=failed_gate,
        model_version=profile.model_version,
        age_sec=snapshot.age_sec,
        source=snapshot.source or "session_report",
    )


def decide(
    signal: Signal,
    profile: Profile,
    seconds_left: Optional[int] = None,
    skew_clob: Optional[float] = None,
    open_position: Optional[Position] = None,
    kill_flag: bool = False,
) -> Decision:
    """Step 3 → `Decision` (`05 §4`) with overlays (`04 §8`).

    Precedence (most-urgent first): kill → stop_loss → time_exit → enter/hold/skip.
    Overlays act on an `open_position`. The hedge leg is attached to an `enter`
    when the skew is extreme and time is short (`03 §5`). `seconds_left` and
    `skew_clob` are passed explicitly (time/market state) so this is a pure
    function of its arguments.
    """
    sl = seconds_left

    dec = Decision(
        ts=signal.ts,
        market_slug=signal.market_slug,
        signal_ref_ts=signal.ts,
        mode="dry_run",
    )

    # ---- kill overlay (highest precedence) ---------------------------------
    if kill_flag:
        if open_position is not None:
            dec.action = "exit"
            dec.side = open_position.side
            dec.reason = "kill"
        else:
            dec.action = "skip"
            dec.reason = "killed"
        return dec

    # ---- exit overlays on an open position ---------------------------------
    if open_position is not None:
        # stop_loss: current chosen-side ask fell >= stop_loss_pct below entry.
        cur_ask = signal.chosen_side_ask
        if (
            open_position.entry_price is not None
            and cur_ask is not None
            and open_position.side == signal.chosen_side
        ):
            drop = (open_position.entry_price - cur_ask) / open_position.entry_price
            if drop >= profile.stop_loss_pct_from_entry:
                dec.action = "exit"
                dec.side = open_position.side
                dec.reason = "stop_loss"
                return dec
        # also honour an explicit stop_loss_price on the position
        if (
            open_position.stop_loss_price is not None
            and cur_ask is not None
            and cur_ask <= open_position.stop_loss_price
            and open_position.side == signal.chosen_side
        ):
            dec.action = "exit"
            dec.side = open_position.side
            dec.reason = "stop_loss"
            return dec

        # time_exit: seconds_left <= exit_before_sec.
        if sl is not None and sl <= profile.exit_before_sec:
            dec.action = "exit"
            dec.side = open_position.side
            dec.reason = "time_exit"
            return dec

    # ---- enter / hold / skip path ------------------------------------------
    if not signal.gates_passed:
        dec.action = "skip"
        dec.reason = signal.failed_gate
        return dec

    if signal.total_score is not None and signal.total_score >= profile.enter_score_min:
        dec.action = "enter"
        dec.side = signal.chosen_side
        dec.limit_price = signal.chosen_side_ask
        size = sizing_mod.size_position(signal.chosen_side_ask, profile, equity_usd=profile.equity_usd)
        if size.do_not_trade:
            dec.action = "skip"
            dec.reason = size.reason or "do_not_trade"
            return dec
        dec.size_usd = size.size_usd
        dec.shares = size.shares
        dec.reason = (
            f"score_{signal.total_score:.2f}_ge_min_{profile.enter_score_min:.2f}"
        )

        # hedge overlay (`03 §5`): extreme skew + short time ⇒ attach opposite leg.
        if (
            profile.hedge_enabled
            and skew_clob is not None
            and skew_clob >= profile.hedge_trigger_side_price_gte
            and sl is not None
            and sl <= profile.hedge_trigger_seconds_left_lte
        ):
            hedge_side = DOWN if dec.side == UP else UP
            # hedge never larger than the main leg; use the min of the band.
            notional = min(profile.hedge_notional_usd_min, dec.size_usd or profile.hedge_notional_usd_min)
            notional = max(notional, 0.0)
            notional = min(notional, profile.hedge_notional_usd_max)
            dec.hedge = {"enabled": True, "side": hedge_side, "notional_usd": notional}
        return dec

    dec.action = "hold"
    dec.reason = "score_below_min"
    return dec


def evaluate_and_decide(
    features: Features,
    snapshot: MarketSnapshot,
    profile: Profile,
    risk_allows: bool = True,
    open_position: Optional[Position] = None,
    kill_flag: bool = False,
) -> Tuple[Signal, Decision]:
    """Convenience: run `evaluate` then `decide`, threading seconds_left/skew_clob.

    Pure: seconds_left comes from the snapshot, skew_clob from the features.
    """
    signal = evaluate(features, snapshot, profile, risk_allows=risk_allows)
    decision = decide(
        signal,
        profile,
        seconds_left=snapshot.seconds_left,
        skew_clob=features.skew_clob,
        open_position=open_position,
        kill_flag=kill_flag,
    )
    return signal, decision
