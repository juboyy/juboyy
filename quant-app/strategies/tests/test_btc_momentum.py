"""BtcMomentumStrategy wraps the engine and returns a Decision (or []).

Offline + deterministic: builds a MarketSnapshot directly (no network), runs the
strategy, and asserts it returns the same actionable Decision the engine spine
produces — proving the wrapper reuses the engine rather than reimplementing it.
"""

from engine.config import Profile
from engine.contracts import MarketSnapshot
from engine import indicators
from engine import signal_engine

from strategies.base import StrategyContext
from strategies.btc_momentum import BtcMomentumStrategy


def good_snapshot(**over) -> MarketSnapshot:
    base = dict(
        ts="2026-06-23T14:03:55Z",
        market_slug="btc-5m",
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
        btc_price_now=64100.0,  # +100 move => momentum up
        age_sec=3,
        source="test",
    )
    base.update(over)
    return MarketSnapshot(**base)


def _ctx(snap, profile, **kw) -> StrategyContext:
    return StrategyContext(snapshot=snap, profile=profile, budget_usd=8.0, history=[], **kw)


def test_proposes_enter_decision_matching_engine():
    p = Profile()
    snap = good_snapshot()
    strat = BtcMomentumStrategy()

    decisions = strat.propose(_ctx(snap, p))

    assert len(decisions) == 1
    dec = decisions[0]
    assert dec.action == "enter"
    assert dec.side == "up"

    # Identical to the engine spine called directly (proves it's a thin wrapper).
    feats = indicators.compute(snap, history=[], profile=p)
    _sig, engine_dec = signal_engine.evaluate_and_decide(feats, snap, p, risk_allows=True)
    assert dec.action == engine_dec.action
    assert dec.side == engine_dec.side
    assert dec.limit_price == engine_dec.limit_price
    assert dec.shares == engine_dec.shares


def test_returns_empty_on_skip():
    p = Profile()
    # Tiny BTC move => momentum gate fails => engine decides "skip" => [].
    snap = good_snapshot(btc_price_now=64000.5)
    strat = BtcMomentumStrategy()

    decisions = strat.propose(_ctx(snap, p))
    assert decisions == []


def test_uses_precomputed_features_when_supplied():
    p = Profile()
    snap = good_snapshot()
    feats = indicators.compute(snap, history=[], profile=p)
    strat = BtcMomentumStrategy()

    decisions = strat.propose(_ctx(snap, p, features=feats))
    assert len(decisions) == 1
    assert decisions[0].action == "enter"


def test_defaults_paper_mode_and_data_needs():
    strat = BtcMomentumStrategy()
    assert strat.mode == "paper"
    assert strat.cadence_sec == 5.0
    assert strat.data_needs() == {"snapshot", "history"}
