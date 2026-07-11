"""Known input → expected output tests for every indicator (incl. null/edges)."""

import math

import pytest

from engine.indicators import (
    momentum,
    realized_vol,
    skew,
    liquidity,
    imbalance,
    time_decay,
    staleness,
)


# -- momentum ---------------------------------------------------------------

def test_momentum_up_score():
    # move = 64080 - 64000 = 80; (80-70)/(100-70) = 1/3
    r = momentum(64000.0, 64080.0)
    assert r["btc_move_usd"] == 80.0
    assert r["momentum_side"] == "up"
    assert r["momentum_score"] == pytest.approx(1.0 / 3.0)


def test_momentum_down_and_clamp():
    r = momentum(64000.0, 63800.0)  # move = -200, |move| >> 100 => clamp 1
    assert r["momentum_side"] == "down"
    assert r["momentum_score"] == 1.0


def test_momentum_below_floor_zero():
    r = momentum(64000.0, 64050.0)  # |50| < 70 floor => 0
    assert r["momentum_score"] == 0.0
    assert r["momentum_side"] == "up"


def test_momentum_null_input():
    r = momentum(None, 64080.0)
    assert r["btc_move_usd"] is None
    assert r["momentum_score"] is None
    assert r["momentum_side"] is None


def test_momentum_zero_move_side_null():
    r = momentum(64000.0, 64000.0)
    assert r["momentum_side"] is None
    assert r["momentum_score"] == 0.0


# -- realized_vol -----------------------------------------------------------

def test_realized_vol_known():
    # 9 prices, constant +10 step => returns all 10 => stdev 0 => rv 0
    prices = [64000.0 + 10 * i for i in range(9)]
    r = realized_vol(prices, poll_sec=5, entry_window_target_sec=120, rv_cap_usd=150)
    assert r["rv_usd"] == 0.0
    assert r["rv_score"] == 0.0


def test_realized_vol_nonzero_and_scale():
    prices = [0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 0.0]  # alternating returns
    r = realized_vol(prices, poll_sec=5, entry_window_target_sec=120, rv_cap_usd=150)
    # returns alternate +10/-10; stdev of sample is sqrt(var); scaled by sqrt(24)
    assert r["rv_usd"] is not None and r["rv_usd"] > 0
    assert 0.0 <= r["rv_score"] <= 1.0


def test_realized_vol_insufficient_points_null():
    r = realized_vol([1.0, 2.0, 3.0])  # < 8 points
    assert r["rv_usd"] is None
    assert r["rv_score"] is None


# -- skew -------------------------------------------------------------------

def test_skew_clob_and_score():
    r = skew(0.71, 0.30, 0.68, 0.32, skew_score_cap=0.95)
    # skew_clob = 0.71/1.01
    assert r["skew_clob"] == pytest.approx(0.71 / 1.01)
    assert r["skew_side"] == "up"
    # gamma side up too
    assert r["skew_agree"] is True
    # score = (0.70297 - 0.5)/(0.95-0.5)
    assert r["skew_score"] == pytest.approx((0.71 / 1.01 - 0.5) / 0.45)


def test_skew_disagree():
    r = skew(0.71, 0.30, 0.40, 0.60)  # clob up, gamma down
    assert r["skew_side"] == "up"
    assert r["skew_agree"] is False


def test_skew_null_clob():
    r = skew(None, 0.30, 0.68, 0.32)
    assert r["skew_clob"] is None
    assert r["skew_side"] is None
    assert r["skew_score"] is None


def test_skew_tie_defaults_up():
    r = skew(0.5, 0.5, None, None)
    assert r["skew_side"] == "up"
    assert r["skew_clob"] == 0.5
    assert r["skew_score"] == 0.0
    assert r["skew_agree"] is None  # gamma missing


# -- liquidity --------------------------------------------------------------

def test_liquidity_known():
    r = liquidity(0.02, 64.0, skip_if_spread_gt=0.03, skip_if_top_ask_notional_usd_lt=30,
                  spread_ref=0.005, notional_ref=100)
    assert r["spread_ok"] is True
    assert r["notional_ok"] is True
    # spread_score = (0.03-0.02)/(0.03-0.005)=0.4 ; depth=64/100=0.64
    assert r["liquidity_score"] == pytest.approx(0.5 * 0.4 + 0.5 * 0.64)


def test_liquidity_gates_fail():
    r = liquidity(0.05, 10.0)  # wide spread, thin depth
    assert r["spread_ok"] is False
    assert r["notional_ok"] is False


def test_liquidity_null():
    r = liquidity(None, None)
    assert r["liquidity_score"] is None
    assert r["spread_ok"] is False
    assert r["notional_ok"] is False


# -- imbalance --------------------------------------------------------------

def test_imbalance_known():
    r = imbalance(51.0, 64.0, candidate_side="up")
    # imb = (51-64)/115 = -0.113
    assert r["imbalance"] == pytest.approx((51 - 64) / 115)
    assert r["imbalance_score"] == pytest.approx(((51 - 64) / 115 + 1) / 2)


def test_imbalance_veto_zeroes_score():
    # strong sell pressure on UP candidate: bid<<ask => imb very negative
    r = imbalance(5.0, 95.0, candidate_side="up", imbalance_veto=-0.6)
    assert r["imbalance_score"] == 0.0


def test_imbalance_down_candidate_flips():
    # same notionals but DOWN candidate: buy pressure on up book is adverse
    r = imbalance(95.0, 5.0, candidate_side="down", imbalance_veto=-0.6)
    # effective imbalance = -0.9 < veto => 0
    assert r["imbalance_score"] == 0.0


def test_imbalance_missing_neutral():
    r = imbalance(None, None, candidate_side="up")
    assert r["imbalance"] is None
    assert r["imbalance_score"] == 0.5


# -- time_decay -------------------------------------------------------------

def test_time_decay_peak_at_target():
    r = time_decay(120)
    assert r["in_window"] is True
    assert r["time_decay_score"] == 1.0


def test_time_decay_edges():
    assert time_decay(90)["time_decay_score"] == pytest.approx(0.0)
    assert time_decay(150)["time_decay_score"] == pytest.approx(0.0)
    # 105 => 1 - 15/30 = 0.5
    assert time_decay(105)["time_decay_score"] == pytest.approx(0.5)


def test_time_decay_out_of_window():
    r = time_decay(40)
    assert r["in_window"] is False


def test_time_decay_null():
    r = time_decay(None)
    assert r["in_window"] is False
    assert r["time_decay_score"] is None


# -- staleness --------------------------------------------------------------

def test_staleness_healthy():
    r = staleness(3, running=True, skip_if_quote_stale_sec_gt=8, dead_man_sec=30)
    assert r["fresh"] is True
    assert r["process_ok"] is True
    assert r["dead_man_tripped"] is False
    assert r["health_score"] == 1.0


def test_staleness_stale():
    r = staleness(10, running=True, skip_if_quote_stale_sec_gt=8, dead_man_sec=30)
    assert r["fresh"] is False
    assert r["health_score"] == 0.0
    assert r["dead_man_tripped"] is False  # 10 <= 30


def test_staleness_dead_man_age():
    r = staleness(40, running=True, dead_man_sec=30)
    assert r["dead_man_tripped"] is True


def test_staleness_not_running():
    r = staleness(2, running=False)
    assert r["process_ok"] is False
    assert r["health_score"] == 0.0
    assert r["dead_man_tripped"] is True


def test_staleness_null_age_failsafe():
    r = staleness(None, running=True)
    assert r["fresh"] is False
    assert r["dead_man_tripped"] is True
    assert r["health_score"] == 0.0
