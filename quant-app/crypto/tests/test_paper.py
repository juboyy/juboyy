"""Paper adapter: deterministic fills + cost-model integration (03 §8, 05 §5/§6)."""

import pytest

from crypto.adapter import Order, TradeResult
from crypto.paper import CostModel, PaperExecutionAdapter


def _decision(**over):
    d = {
        "action": "enter",
        "side": "up",
        "limit_price": 0.71,
        "shares": 7,
        "size_usd": 5.0,
        "market_slug": "btc-updown-2026-06-20-1405",
        "seconds_left_at_entry": 116,
        "btc_move_usd": 78.0,
        "skew": 0.703,
        "threshold_price": 0.70,
    }
    d.update(over)
    return d


def test_open_produces_dry_run_order_no_tx():
    a = PaperExecutionAdapter()
    order = a.open_position(_decision())
    assert isinstance(order, Order)
    assert order.mode == "dry_run"
    assert order.status == "open"
    assert order.open_tx is None  # dry-run never has an on-chain tx (05 §5)
    assert order.shares == 7
    assert order.entry_price == 0.71
    # cost basis = shares × fill (no jitter by default)
    assert order.cost_usdc == pytest.approx(7 * 0.71)
    # stop_loss_price = entry × (1 - stop_loss_pct)
    assert order.stop_loss_price == pytest.approx(0.71 * (1 - 0.25))


def test_deterministic_fills_identical_inputs_identical_outputs():
    a1 = PaperExecutionAdapter(seed=42)
    a2 = PaperExecutionAdapter(seed=42)
    o1 = a1.open_position(_decision())
    o2 = a2.open_position(_decision())
    t1 = a1.close_position(o1, outcome="win", close_reason="settlement")
    t2 = a2.close_position(o2, outcome="win", close_reason="settlement")
    assert o1.to_dict() | {"ts": None, "order_id": None} == o2.to_dict() | {"ts": None, "order_id": None}
    assert t1.realized_cashflow_pnl_usdc == t2.realized_cashflow_pnl_usdc
    assert t1.slippage_usdc == t2.slippage_usdc
    assert t1.gas_usdc == t2.gas_usdc


def test_seeded_jitter_is_reproducible():
    a1 = PaperExecutionAdapter(seed=7, jitter_ticks=2)
    a2 = PaperExecutionAdapter(seed=7, jitter_ticks=2)
    o1 = a1.open_position(_decision())
    o2 = a2.open_position(_decision())
    assert o1.entry_price == o2.entry_price  # same seed ⇒ same jitter


def test_settlement_win_pnl_matches_cost_model():
    # shares=7, entry 0.71 → cost 4.97. Settlement win pays $7.
    # costs: slip = 7 * 1 * 0.01 = 0.07; gas = 0.02 * (open + settle) = 0.04;
    #        fees = 0 (fee_bps=0).
    a = PaperExecutionAdapter()
    order = a.open_position(_decision())
    tr = a.close_position(order, outcome="win", close_reason="settlement")
    assert tr.cost_usdc == pytest.approx(4.97)
    assert tr.slippage_usdc == pytest.approx(0.07)
    assert tr.gas_usdc == pytest.approx(0.04)
    assert tr.fees_usdc == pytest.approx(0.0)
    expected = 7.0 - 4.97 - 0.07 - 0.04 - 0.0
    assert tr.realized_cashflow_pnl_usdc == pytest.approx(expected)
    assert tr.result == "win"
    assert tr.mode == "dry_run"
    assert tr.close_tx is None


def test_settlement_loss_pnl_is_full_premium_plus_costs():
    a = PaperExecutionAdapter()
    order = a.open_position(_decision())
    tr = a.close_position(order, outcome="loss", close_reason="settlement")
    # loss pays $0: pnl = 0 - 4.97 - 0.07 - 0.04 = -5.08
    assert tr.realized_cashflow_pnl_usdc == pytest.approx(-5.08)
    assert tr.result == "loss"


def test_fee_bps_applied_to_notional():
    a = PaperExecutionAdapter(cost_model=CostModel(fee_bps=100))  # 1%
    order = a.open_position(_decision())
    tr = a.close_position(order, outcome="win", close_reason="settlement")
    # settlement: notional = cost basis only (no exit notional). 1% of 4.97
    assert tr.fees_usdc == pytest.approx(4.97 * 0.01)


def test_active_exit_uses_exit_price_and_double_slippage_and_gas():
    a = PaperExecutionAdapter()
    order = a.open_position(_decision())
    tr = a.close_position(
        order, exit_price=0.50, close_reason="stop_loss"
    )
    # exit cashflow = 7 * 0.50 = 3.50; slip = 0.07 (entry) + 0.07 (exit) = 0.14;
    # gas = 0.02 * (open + close) = 0.04.
    assert tr.close_status == "closed"
    assert tr.close_reason == "stop_loss"
    assert tr.slippage_usdc == pytest.approx(0.14)
    assert tr.gas_usdc == pytest.approx(0.04)
    expected = 3.50 - 4.97 - 0.14 - 0.04
    assert tr.realized_cashflow_pnl_usdc == pytest.approx(expected)


def test_close_skipped_held_to_settlement_no_close_gas():
    a = PaperExecutionAdapter()
    order = a.open_position(_decision())
    tr = a.close_position(
        order, outcome="win", close_reason="settlement", close_skipped=True
    )
    assert tr.close_skipped is True
    assert tr.close_success is False
    # skipped close ⇒ only the open action's gas counts.
    assert tr.gas_usdc == pytest.approx(0.02)


def test_trade_result_has_canonical_fields():
    a = PaperExecutionAdapter()
    order = a.open_position(_decision())
    tr = a.close_position(order, outcome="win", close_reason="settlement")
    d = tr.to_dict()
    for k in (
        "realized_cashflow_pnl_usdc",
        "close_reason",
        "close_success",
        "close_status",
        "close_skipped",
        "fees_usdc",
        "slippage_usdc",
        "gas_usdc",
        "btc_move_usd",
        "skew",
        "seconds_left_at_entry",
        "threshold_price",
    ):
        assert k in d
    assert d["btc_move_usd"] == 78.0
    assert d["skew"] == 0.703
    assert d["seconds_left_at_entry"] == 116


def test_paper_adapter_holds_no_keys_and_is_dry_run():
    a = PaperExecutionAdapter()
    assert a.mode == "dry_run"
    assert a.is_live() is False
    bal = a.balance()
    assert bal.funder_address_masked is None  # no wallet in paper mode
    # No attribute on the adapter should contain a key.
    for v in vars(a).values():
        assert "PM_PRIVATE_KEY" not in repr(v)
