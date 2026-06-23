"""Live adapter order methods, exercised with an INJECTED FAKE CLOB client.

No network and no real key: a fake ``py_clob_client``-shaped object is injected
via the ``client=`` constructor seam. These tests assert that

  * place_market / place_limit / cancel / replace / positions / balance call the
    right fake-client methods with the right args,
  * results map to the canonical Quote/Order/Position/TradeResult/Balance shapes,
  * the private key never appears in any repr/log/result,
  * the gate still refuses when disarmed or env creds are missing — injecting a
    client cannot bypass arming.

The real ``py_clob_client`` is NOT installed: an autouse fixture installs a fake
``py_clob_client.clob_types`` module into ``sys.modules`` so the adapter's lazy
``from py_clob_client.clob_types import OrderArgs`` resolves to a fake. No network.
"""

import sys
import types

import pytest

from crypto.adapter import Balance, Order, Position, Quote, TradeResult
from crypto.polymarket import LiveGateError, PolymarketExecutionAdapter

FULL_ENV = {
    "PM_PRIVATE_KEY": "0x" + "ab" * 32,
    "PM_FUNDER": "0xFunderAddress0000000000000000000000000000",
    "PM_SIGNATURE_TYPE": "2",
    "PM_API_KEY": "dummy-key",
    "PM_API_SECRET": "dummy-secret",
    "PM_API_PASSPHRASE": "dummy-pass",
}

class _FakeOrderArgs:
    """Stand-in for ``py_clob_client.clob_types.OrderArgs`` (records its fields).

    Installed into ``sys.modules`` by the autouse fixture below so the adapter's
    lazy ``from py_clob_client.clob_types import OrderArgs`` resolves WITHOUT the
    real SDK and WITHOUT any network. The real import path is therefore exercised.
    """

    def __init__(self, price, size, side, token_id):
        self.price = price
        self.size = size
        self.side = side
        self.token_id = token_id


@pytest.fixture(autouse=True)
def fake_py_clob_client(monkeypatch):
    pkg = types.ModuleType("py_clob_client")
    clob_types = types.ModuleType("py_clob_client.clob_types")
    clob_types.OrderArgs = _FakeOrderArgs
    pkg.clob_types = clob_types
    monkeypatch.setitem(sys.modules, "py_clob_client", pkg)
    monkeypatch.setitem(sys.modules, "py_clob_client.clob_types", clob_types)
    yield


class FakeClient:
    """Records calls and returns canned, dict-shaped responses like the SDK."""

    def __init__(self):
        self.calls = []
        self.last_order_args = None

    # create/post order path
    def create_order(self, args):
        self.calls.append(("create_order", args))
        self.last_order_args = args
        return {"signed": True, "args": args}

    def post_order(self, signed):
        self.calls.append(("post_order", signed))
        return {"orderID": "ord-123", "transactionHash": "0xdeadbeef", "cashflow_usdc": 12.5}

    def cancel(self, order_id):
        self.calls.append(("cancel", order_id))
        return {"canceled": [order_id], "not_canceled": {}}

    def get_order(self, order_id):
        self.calls.append(("get_order", order_id))
        return {"asset_id": "tok-9", "side": "buy", "market": "mkt-x", "id": order_id}

    def get_orders(self):
        self.calls.append(("get_orders",))
        return [
            {
                "id": "ord-1",
                "market": "mkt-a",
                "side": "buy",
                "price": "0.10",
                "size_matched": "50",
                "status": "open",
                "transactionHash": "0xaaa",
            }
        ]

    def get_order_book(self, token_id):
        self.calls.append(("get_order_book", token_id))
        return {
            "asks": [{"price": "0.12", "size": "100"}, {"price": "0.15", "size": "40"}],
            "bids": [{"price": "0.09", "size": "80"}, {"price": "0.08", "size": "60"}],
        }

    def get_balance_allowance(self, *a, **k):
        self.calls.append(("get_balance_allowance",))
        return {"balance": "250.75"}


def _armed(client=None, env=None):
    return PolymarketExecutionAdapter(
        armed=True, mode="live", env=env or FULL_ENV, client=client
    )


# --- gate still holds even with an injected client ----------------------
def test_injected_client_cannot_bypass_disarmed_gate():
    fc = FakeClient()
    with pytest.raises(LiveGateError):
        PolymarketExecutionAdapter(armed=False, mode="live", env=FULL_ENV, client=fc)


def test_injected_client_cannot_bypass_missing_env():
    fc = FakeClient()
    with pytest.raises(LiveGateError):
        PolymarketExecutionAdapter(armed=True, mode="live", env={}, client=fc)


# --- place_limit -------------------------------------------------------
def test_place_limit_maps_to_order_and_calls_client():
    fc = FakeClient()
    a = _armed(fc)
    order = a.place_limit(
        token_id="tok-9", price=0.10, size=50, side="buy", market_slug="mkt-x", seconds_left=200
    )
    assert isinstance(order, Order)
    assert order.order_id == "ord-123"
    assert order.open_tx == "0xdeadbeef"
    assert order.side == "buy"
    assert order.entry_price == 0.10
    assert order.shares == 50
    assert order.cost_usdc == pytest.approx(5.0)
    assert order.status == "open"
    assert order.mode == "live"
    assert order.seconds_left_at_entry == 200
    # right client methods called
    names = [c[0] for c in fc.calls]
    assert names == ["create_order", "post_order"]
    # OrderArgs carried the right fields
    assert fc.last_order_args.price == 0.10
    assert fc.last_order_args.size == 50.0
    assert fc.last_order_args.side == "buy"
    assert fc.last_order_args.token_id == "tok-9"


def test_place_market_delegates_to_limit():
    fc = FakeClient()
    a = _armed(fc)
    order = a.place_market(token_id="tok-9", size=20, side="up", price=0.13, market_slug="mkt-x")
    assert isinstance(order, Order)
    assert order.shares == 20
    assert [c[0] for c in fc.calls] == ["create_order", "post_order"]


# --- cancel ------------------------------------------------------------
def test_cancel_returns_true_on_canceled_list():
    fc = FakeClient()
    a = _armed(fc)
    assert a.cancel("ord-123") is True
    assert ("cancel", "ord-123") in fc.calls


def test_cancel_returns_false_when_not_canceled():
    fc = FakeClient()
    fc.cancel = lambda oid: {"canceled": [], "not_canceled": {oid: "too late"}}
    a = _armed(fc)
    assert a.cancel("ord-x") is False


# --- replace -----------------------------------------------------------
def test_replace_cancels_then_places_new():
    fc = FakeClient()
    a = _armed(fc)
    new = a.replace("ord-123", new_price=0.11, new_size=30)
    assert isinstance(new, Order)
    assert new.entry_price == 0.11
    assert new.shares == 30
    names = [c[0] for c in fc.calls]
    assert names == ["get_order", "cancel", "create_order", "post_order"]


def test_replace_refuses_if_cancel_fails():
    fc = FakeClient()
    fc.cancel = lambda oid: {"canceled": [], "not_canceled": {oid: "x"}}
    a = _armed(fc)
    with pytest.raises(LiveGateError):
        a.replace("ord-123", new_price=0.11, new_size=30)
    # never placed a replacement after the failed cancel
    assert not any(c[0] == "post_order" for c in fc.calls)


# --- positions ---------------------------------------------------------
def test_positions_map_to_position_shape():
    fc = FakeClient()
    a = _armed(fc)
    poss = a.positions()
    assert len(poss) == 1
    p = poss[0]
    assert isinstance(p, Position)
    assert p.order_id == "ord-1"
    assert p.market_slug == "mkt-a"
    assert p.side == "buy"
    assert p.entry_price == 0.10
    assert p.shares == 50
    assert p.cost_usdc == pytest.approx(5.0)
    assert ("get_orders",) in fc.calls


# --- quote -------------------------------------------------------------
def test_quote_maps_book_to_quote():
    fc = FakeClient()
    a = _armed(fc)
    q = a.quote("tok-9")
    assert isinstance(q, Quote)
    assert q.clob_up_ask == 0.12  # lowest ask
    assert q.clob_up_bid == 0.09  # highest bid
    assert q.min_spread == pytest.approx(0.03)
    assert q.source == "live"


# --- balance -----------------------------------------------------------
def test_balance_reads_equity_via_client():
    fc = FakeClient()
    a = _armed(fc)
    bal = a.balance()
    assert isinstance(bal, Balance)
    assert bal.equity_usd == pytest.approx(250.75)
    assert bal.signature_type == 2
    assert "…" in (bal.funder_address_masked or "")


# --- close_position ----------------------------------------------------
def test_close_position_builds_trade_result():
    fc = FakeClient()
    a = _armed(fc)
    pos = a.place_limit(token_id="tok-9", price=0.10, size=50, side="buy", market_slug="mkt-x")
    fc.calls.clear()
    res = a.close_position(pos)
    assert isinstance(res, TradeResult)
    # exit cashflow 12.5 - cost basis 5.0 => +7.5 pnl => win
    assert res.realized_cashflow_pnl_usdc == pytest.approx(7.5)
    assert res.result == "win"
    assert res.close_tx == "0xdeadbeef"
    assert res.mode == "live"


# --- key never leaks ---------------------------------------------------
def test_key_never_in_results_or_repr():
    fc = FakeClient()
    a = _armed(fc)
    key = FULL_ENV["PM_PRIVATE_KEY"]
    blobs = [
        repr(a),
        repr(a.balance().to_dict()),
        repr([p.to_dict() for p in a.positions()]),
        repr(a.quote("tok-9").to_dict()),
    ]
    for b in blobs:
        assert key not in b
        assert "abab" not in b  # raw key bytes absent
