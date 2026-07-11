"""Tests for sizing (incl. do-not-trade), costs, and risk caps (cap-respect)."""

import math

import pytest

from engine.config import Profile
from engine.contracts import RiskState
from engine import sizing, costs, risk


# -- sizing -----------------------------------------------------------------

def test_size_shares_floor():
    p = Profile()  # stake 5, notional 8
    r = sizing.size_position(0.70, p)
    assert r.do_not_trade is False
    assert r.shares == math.floor(5 / 0.70)  # 7
    assert r.size_usd == 5.0


def test_size_notional_binds():
    p = Profile(stake_usd=50, max_notional_usd=8)
    r = sizing.size_position(0.70, p)
    # min(50,8)=8 => floor(8/0.7)=11
    assert r.shares == math.floor(8 / 0.70)
    assert r.size_usd == 8.0


def test_size_risk_cap_binds():
    p = Profile(stake_usd=50, max_notional_usd=50, risk_per_trade_pct_equity=8, equity_usd=100)
    r = sizing.size_position(0.70, p)
    # risk cap = 8 USD => floor(8/0.7)=11
    assert r.size_usd == pytest.approx(8.0)
    assert r.shares == math.floor(8 / 0.70)


def test_do_not_trade_when_w_le_p():
    p = Profile()
    # win prob 0.70 <= price 0.70 => f* <= 0 => refuse
    r = sizing.size_position(0.70, p, win_prob=0.70)
    assert r.do_not_trade is True
    assert r.reason == "kelly_nonpositive"
    assert r.shares == 0


def test_trade_when_w_gt_p():
    p = Profile()
    r = sizing.size_position(0.70, p, win_prob=0.75)
    assert r.do_not_trade is False
    assert r.shares > 0


def test_kelly_fraction_known():
    # p=0.70, w=0.72 => f* ~ 0.067 per 03 §4
    f = sizing.kelly_fraction(0.70, 0.72)
    assert f == pytest.approx(0.72 - 0.28 / (0.30 / 0.70), rel=1e-6)
    assert sizing.fractional_kelly(0.70, 0.72, 0.25) == pytest.approx(f * 0.25)


def test_kelly_nonpositive_floor():
    assert sizing.fractional_kelly(0.70, 0.65) == 0.0
    assert sizing.do_not_trade(0.70, 0.70) is True


# -- costs ------------------------------------------------------------------

def test_costs_win_settlement():
    p = Profile()  # slip_ticks 1, tick 0.01, gas 0.02, fee 0
    cb = costs.compute_costs(shares=7, entry_price=0.70, won=True, profile=p)
    # cost_basis 4.9; gross 7.0; slip 7*1*0.01=0.07; gas 0.02; fee 0
    assert cb.cost_basis_usdc == pytest.approx(4.9)
    assert cb.slippage_usdc == pytest.approx(0.07)
    assert cb.gas_usdc == pytest.approx(0.02)
    assert cb.realized_cashflow_pnl_usdc == pytest.approx(7.0 - 4.9 - 0.07 - 0.02)
    assert cb.result == "win"


def test_costs_loss_settlement():
    p = Profile()
    cb = costs.compute_costs(shares=7, entry_price=0.70, won=False, profile=p)
    assert cb.realized_cashflow_pnl_usdc == pytest.approx(0.0 - 4.9 - 0.07 - 0.02)
    assert cb.result == "loss"


def test_costs_early_exit_two_gas():
    p = Profile()
    cb = costs.compute_costs(shares=7, entry_price=0.70, won=False, profile=p,
                             exit_price=0.60)
    # gross 4.2; cost_basis 4.9; slip 0.07; gas 0.04 (2 actions)
    assert cb.gas_usdc == pytest.approx(0.04)
    assert cb.realized_cashflow_pnl_usdc == pytest.approx(4.2 - 4.9 - 0.07 - 0.04)


def test_cost_adjusted_breakeven():
    p = Profile()
    be = costs.cost_adjusted_breakeven(0.70, 7, p)
    # (4.9 + 0.07 + 0.02 + 0)/7
    assert be == pytest.approx((4.9 + 0.07 + 0.02) / 7)
    assert be > 0.70  # above the raw price


# -- risk caps --------------------------------------------------------------

def base_state(**over):
    d = dict(profile="conservative", running=True, age_sec=2, max_trades_per_day=12)
    d.update(over)
    return RiskState(**d)


def test_risk_allows_clean():
    p = Profile()
    a = risk.apply(base_state(), p)
    assert a.allowed is True
    assert a.reason is None


def test_risk_killed():
    p = Profile()
    a = risk.apply(base_state(killed=True), p)
    assert a.allowed is False
    assert a.reason == "killed"


def test_risk_not_running():
    p = Profile()
    a = risk.apply(base_state(running=False), p)
    assert a.allowed is False
    assert a.reason in ("not_running", "dead_man")


def test_risk_max_trades_cap():
    p = Profile(max_trades_per_day=12)
    a = risk.apply(base_state(trades_today=12), p)
    assert a.allowed is False
    assert a.reason == "max_trades"


def test_risk_daily_loss_cap():
    p = Profile(equity_usd=100, daily_max_loss_pct=10)
    # cap = 10 USD; pnl_today -10 hits it
    a = risk.apply(base_state(pnl_today=-10.0, daily_loss_cap_usd=10.0), p)
    assert a.allowed is False
    assert a.reason == "daily_loss_cap"


def test_risk_dead_man_age():
    p = Profile(dead_man_sec=30)
    a = risk.apply(base_state(age_sec=40), p)
    assert a.allowed is False
    assert a.reason == "dead_man"


def test_risk_conflicting_position():
    p = Profile()
    st = base_state(open_position={"side": "down", "market_slug": "m2"})
    a = risk.apply(st, p, candidate_side="up", candidate_market="m1")
    assert a.allowed is False
    assert a.reason == "conflicting_position"
