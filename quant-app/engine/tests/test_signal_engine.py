"""Tests for hard gates, weighted score math, and the decision overlays."""

import pytest

from engine.config import Profile
from engine.contracts import MarketSnapshot, Position
from engine import indicators
from engine import signal_engine as signal_mod


def good_snapshot(**over):
    base = dict(
        ts="2026-06-20T14:03:55Z",
        market_slug="m1",
        seconds_left=120,
        clob_up_ask=0.75,
        clob_down_ask=0.25,
        clob_up_bid=0.73,
        clob_down_bid=0.23,
        gamma_up=0.74,
        gamma_down=0.26,
        min_spread=0.02,
        top_ask_notional_usd=64.0,
        top_bid_notional_usd=70.0,
        btc_price_open=64000.0,
        btc_price_now=64100.0,  # +100 move => momentum_score 1, side up
        age_sec=3,
        source="test",
    )
    base.update(over)
    return MarketSnapshot(**base)


def feats(snap, profile):
    return indicators.compute(snap, history=[], profile=profile)


# -- hard gates: pass --------------------------------------------------------

def test_all_gates_pass_and_enter():
    p = Profile()
    snap = good_snapshot()
    f = feats(snap, p)
    sig, dec = signal_mod.evaluate_and_decide(f, snap, p, risk_allows=True)
    assert sig.gates_passed is True
    assert sig.failed_gate is None
    assert all(sig.gates.values())
    assert dec.action == "enter"
    assert dec.side == "up"
    assert dec.limit_price == 0.75
    assert dec.shares == 6  # floor(min(5,8)/0.75) = floor(6.67) = 6


# -- hard gates: each failing in isolation -----------------------------------

def test_gate_health_fails_first():
    p = Profile()
    snap = good_snapshot(age_sec=20)  # stale
    sig = signal_mod.evaluate(feats(snap, p), snap, p, risk_allows=True)
    assert sig.gates["health"] is False
    assert sig.failed_gate == "health"
    assert sig.gates_passed is False


def test_gate_in_window_fails():
    p = Profile()
    snap = good_snapshot(seconds_left=40)
    sig = signal_mod.evaluate(feats(snap, p), snap, p, risk_allows=True)
    assert sig.gates["in_window"] is False
    assert sig.failed_gate == "in_window"


def test_gate_momentum_present_fails():
    p = Profile()
    snap = good_snapshot(btc_price_now=64050.0)  # +50 < 70
    sig = signal_mod.evaluate(feats(snap, p), snap, p, risk_allows=True)
    assert sig.gates["momentum_present"] is False
    assert sig.failed_gate == "momentum_present"


def test_gate_spread_fails():
    p = Profile()
    snap = good_snapshot(min_spread=0.05)
    sig = signal_mod.evaluate(feats(snap, p), snap, p, risk_allows=True)
    assert sig.gates["spread_ok"] is False
    assert sig.failed_gate == "spread_ok"


def test_gate_notional_fails():
    p = Profile()
    snap = good_snapshot(top_ask_notional_usd=10.0)
    sig = signal_mod.evaluate(feats(snap, p), snap, p, risk_allows=True)
    assert sig.gates["notional_ok"] is False
    assert sig.failed_gate == "notional_ok"


def test_gate_skew_agreement_fails():
    p = Profile()
    # momentum up, but skew side down (down ask bigger)
    snap = good_snapshot(clob_up_ask=0.30, clob_down_ask=0.75)
    sig = signal_mod.evaluate(feats(snap, p), snap, p, risk_allows=True)
    assert sig.gates["skew_agreement"] is False
    assert sig.failed_gate == "skew_agreement"


def test_gate_ask_ge_threshold_fails():
    p = Profile()
    snap = good_snapshot(clob_up_ask=0.65, clob_down_ask=0.35)
    sig = signal_mod.evaluate(feats(snap, p), snap, p, risk_allows=True)
    assert sig.gates["ask_ge_threshold"] is False
    assert sig.failed_gate == "ask_ge_threshold"


def test_gate_ask_le_max_fails():
    p = Profile()
    snap = good_snapshot(clob_up_ask=0.95, clob_down_ask=0.05)
    sig = signal_mod.evaluate(feats(snap, p), snap, p, risk_allows=True)
    assert sig.gates["ask_le_max"] is False
    assert sig.failed_gate == "ask_le_max"


def test_gate_risk_allows_fails():
    p = Profile()
    snap = good_snapshot()
    sig = signal_mod.evaluate(feats(snap, p), snap, p, risk_allows=False)
    assert sig.gates["risk_allows"] is False
    assert sig.failed_gate == "risk_allows"


# -- weighted score math -----------------------------------------------------

def test_weighted_score_math_exact():
    p = Profile()
    snap = good_snapshot()
    f = feats(snap, p)
    sig = signal_mod.evaluate(f, snap, p, risk_allows=True)

    mom = f.momentum_score
    sk = f.skew_score
    liq = f.liquidity_score
    imb = f.imbalance_score if f.imbalance_score is not None else 0.5
    td = f.time_decay_score
    rv = f.rv_score or 0.0
    raw = p.w_mom * mom + p.w_skew * sk + p.w_liq * liq + p.w_imb * imb + p.w_time * td
    vol_adj = 1 - p.w_vol * rv
    bonus = p.agreement_bonus if f.skew_agree else 0.0
    expected = min(1.0, max(0.0, raw * vol_adj + bonus))
    assert sig.total_score == pytest.approx(round(expected, 6))
    # breakdown carried
    assert sig.subscores["momentum_score"] == mom
    assert sig.subscores["agreement_bonus"] == bonus
    assert sig.weights["w_mom"] == p.w_mom


def test_hold_when_score_below_min():
    # crank enter_score_min above any achievable score
    p = Profile(enter_score_min=0.99)
    snap = good_snapshot()
    f = feats(snap, p)
    sig, dec = signal_mod.evaluate_and_decide(f, snap, p, risk_allows=True)
    assert sig.gates_passed is True
    assert dec.action == "hold"
    assert dec.reason == "score_below_min"


# -- decision overlays -------------------------------------------------------

def test_skip_on_failed_gate():
    p = Profile()
    snap = good_snapshot(seconds_left=40)
    f = feats(snap, p)
    _, dec = signal_mod.evaluate_and_decide(f, snap, p, risk_allows=True)
    assert dec.action == "skip"
    assert dec.reason == "in_window"


def test_exit_stop_loss_overlay():
    p = Profile()
    # current up ask 0.50 vs entry 0.75 => drop 0.33 >= 0.25
    snap = good_snapshot(clob_up_ask=0.50, clob_down_ask=0.50, gamma_up=0.50, gamma_down=0.50)
    f = feats(snap, p)
    pos = Position(side="up", entry_price=0.75, shares=6, market_slug="m1",
                   stop_loss_price=0.75 * (1 - 0.25))
    _, dec = signal_mod.evaluate_and_decide(f, snap, p, risk_allows=True, open_position=pos)
    assert dec.action == "exit"
    assert dec.reason == "stop_loss"


def test_exit_time_exit_overlay():
    p = Profile()
    snap = good_snapshot(seconds_left=15)  # <= exit_before_sec 20
    f = feats(snap, p)
    pos = Position(side="up", entry_price=0.75, shares=6, market_slug="m1")
    _, dec = signal_mod.evaluate_and_decide(f, snap, p, risk_allows=True, open_position=pos)
    assert dec.action == "exit"
    assert dec.reason == "time_exit"


def test_hedge_overlay_attached():
    # Extreme skew + short time on an enter. The entry window requires
    # seconds_left >= 60, so for the hedge (seconds_left <= trigger) to overlap an
    # *enter*, the trigger must be >= 60. We use 70 (within the 10-90 range) and
    # raise max_entry_ask so the extreme 0.94 ask still passes the price gate.
    p = Profile.aggressive(max_entry_ask=0.97, hedge_trigger_seconds_left_lte=70)
    snap = good_snapshot(seconds_left=65, clob_up_ask=0.94, clob_down_ask=0.05,
                         gamma_up=0.94, gamma_down=0.06)
    f = feats(snap, p)
    sig, dec = signal_mod.evaluate_and_decide(f, snap, p, risk_allows=True)
    assert dec.action == "enter"
    assert dec.hedge["enabled"] is True
    assert dec.hedge["side"] == "down"
    assert dec.hedge["notional_usd"] is not None


def test_hedge_not_attached_when_skew_not_extreme():
    p = Profile.aggressive(hedge_trigger_seconds_left_lte=70)
    snap = good_snapshot(seconds_left=65)  # skew ~0.75, below 0.93 trigger
    f = feats(snap, p)
    _, dec = signal_mod.evaluate_and_decide(f, snap, p, risk_allows=True)
    assert dec.action == "enter"
    assert dec.hedge["enabled"] is False


def test_kill_overlay_blocks_and_exits():
    p = Profile()
    snap = good_snapshot()
    f = feats(snap, p)
    # kill with no position => skip/killed
    _, dec = signal_mod.evaluate_and_decide(f, snap, p, risk_allows=True, kill_flag=True)
    assert dec.action == "skip"
    assert dec.reason == "killed"
    # kill with position => exit/kill
    pos = Position(side="up", entry_price=0.75, shares=6, market_slug="m1")
    _, dec2 = signal_mod.evaluate_and_decide(f, snap, p, risk_allows=True,
                                             open_position=pos, kill_flag=True)
    assert dec2.action == "exit"
    assert dec2.reason == "kill"
