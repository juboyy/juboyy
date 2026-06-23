"""PortfolioRisk vetoes on global cap, per-strategy cap, and global kill; else allows."""

from engine.contracts import Decision

from portfolio.risk_portfolio import PortfolioRisk, PortfolioState


def _enter(size_usd=5.0):
    return Decision(action="enter", side="up", market_slug="btc-5m", size_usd=size_usd, shares=6)


def test_allows_when_no_caps_bind():
    risk = PortfolioRisk(
        global_daily_loss_cap_usd=50.0,
        per_strategy_daily_loss_cap_usd={"btc_momentum": 20.0},
        max_concurrent_exposure_usd=100.0,
    )
    state = PortfolioState(pnl_today=-5.0, pnl_today_by_strategy={"btc_momentum": -2.0})
    allow = risk.approve("btc_momentum", _enter(), state)
    assert allow.allowed is True
    assert allow.reason is None


def test_vetoes_on_global_daily_loss_cap():
    risk = PortfolioRisk(global_daily_loss_cap_usd=50.0)
    state = PortfolioState(pnl_today=-50.0)  # exactly at the cap binds
    allow = risk.approve("btc_momentum", _enter(), state)
    assert allow.allowed is False
    assert allow.reason == "global_daily_loss_cap"


def test_vetoes_on_per_strategy_daily_loss_cap():
    risk = PortfolioRisk(
        global_daily_loss_cap_usd=100.0,
        per_strategy_daily_loss_cap_usd={"btc_momentum": 20.0},
    )
    state = PortfolioState(
        pnl_today=-25.0,  # global cap NOT hit
        pnl_today_by_strategy={"btc_momentum": -21.0},  # strategy cap hit
    )
    allow = risk.approve("btc_momentum", _enter(), state)
    assert allow.allowed is False
    assert allow.reason == "strategy_daily_loss_cap"


def test_vetoes_on_global_kill_flag():
    risk = PortfolioRisk(global_daily_loss_cap_usd=100.0)
    risk.kill("operator")
    state = PortfolioState()
    allow = risk.approve("btc_momentum", _enter(), state)
    assert allow.allowed is False
    assert allow.reason == "global_kill"


def test_vetoes_on_kill_recorded_in_state():
    risk = PortfolioRisk()
    state = PortfolioState(killed=True)
    allow = risk.approve("btc_momentum", _enter(), state)
    assert allow.allowed is False
    assert allow.reason == "global_kill"


def test_vetoes_on_max_concurrent_exposure():
    risk = PortfolioRisk(max_concurrent_exposure_usd=10.0)
    state = PortfolioState(open_exposure_usd=8.0)
    # 8 + 5 = 13 > 10 => veto
    allow = risk.approve("btc_momentum", _enter(size_usd=5.0), state)
    assert allow.allowed is False
    assert allow.reason == "max_concurrent_exposure"


def test_exposure_cap_ignores_non_entries():
    risk = PortfolioRisk(max_concurrent_exposure_usd=10.0)
    state = PortfolioState(open_exposure_usd=8.0)
    exit_dec = Decision(action="exit", side="up", market_slug="btc-5m", size_usd=5.0)
    allow = risk.approve("btc_momentum", exit_dec, state)
    assert allow.allowed is True
