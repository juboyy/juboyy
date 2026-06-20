"""Offline unit tests for the PURE parsers against saved JSON fixtures.

Deterministic: no network, no clock dependence (``now_epoch`` is supplied).
"""

from __future__ import annotations

from feeds import parsers


# ---------------------------------------------------------------------------
# numeric coercion
# ---------------------------------------------------------------------------

def test_to_float_handles_strings_and_garbage():
    assert parsers._to_float("0.71") == 0.71
    assert parsers._to_float(0.71) == 0.71
    assert parsers._to_float("") is None
    assert parsers._to_float(None) is None
    assert parsers._to_float("abc") is None
    assert parsers._to_float(True) is None


def test_maybe_json_list_decodes_string_arrays():
    assert parsers._maybe_json_list('["Up", "Down"]') == ["Up", "Down"]
    assert parsers._maybe_json_list(["Up", "Down"]) == ["Up", "Down"]
    assert parsers._maybe_json_list("") == []
    assert parsers._maybe_json_list("not json") == []


# ---------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------

def test_parse_iso8601_and_seconds_left():
    epoch = parsers.parse_iso8601_to_epoch("2026-06-20T18:05:00Z")
    assert epoch is not None
    # 2 minutes before close
    now = epoch - 120
    assert parsers.seconds_left("2026-06-20T18:05:00Z", now) == 120
    # closed market -> non-positive
    assert parsers.seconds_left("2026-06-20T18:05:00Z", epoch + 5) == -5
    assert parsers.seconds_left(None, now) is None


def test_interval_open_key_buckets_by_5min():
    # 18:02:30 and 18:04:59 share a bucket; 18:05:00 starts a new one
    base = parsers.parse_iso8601_to_epoch("2026-06-20T18:00:00Z")
    assert parsers.interval_open_key(base + 150) == parsers.interval_open_key(base + 299)
    assert parsers.interval_open_key(base + 299) != parsers.interval_open_key(base + 300)


# ---------------------------------------------------------------------------
# gamma market selection + parsing
# ---------------------------------------------------------------------------

def test_select_btc_5m_markets_excludes_eth(gamma_events):
    markets = parsers.select_btc_5m_markets(gamma_events)
    slugs = {m["slug"] for m in markets}
    assert "btc-updown-2026-06-20-1405" in slugs
    assert "btc-updown-2026-06-20-1410" in slugs
    assert "eth-updown-2026-06-20-1405" not in slugs


def test_parse_gamma_market_fields(gamma_events):
    markets = parsers.select_btc_5m_markets(gamma_events)
    m1405 = next(m for m in markets if m["slug"] == "btc-updown-2026-06-20-1405")
    parsed = parsers.parse_gamma_market(m1405)
    assert parsed["slug"] == "btc-updown-2026-06-20-1405"
    assert parsed["gamma_up"] == 0.68
    assert parsed["gamma_down"] == 0.32
    assert parsed["min_spread"] == 0.02
    assert parsed["end_date"] == "2026-06-20T18:05:00Z"
    assert parsed["clob_up_token_id"] == "111111111111"
    assert parsed["clob_down_token_id"] == "222222222222"


def test_pick_current_and_next(gamma_events):
    markets = parsers.select_btc_5m_markets(gamma_events)
    # now = 18:03 -> current is the 18:05 market, next is 18:10
    now = parsers.parse_iso8601_to_epoch("2026-06-20T18:03:00Z")
    current, nxt = parsers.pick_current_and_next(markets, now)
    assert current["slug"] == "btc-updown-2026-06-20-1405"
    assert nxt["slug"] == "btc-updown-2026-06-20-1410"


def test_pick_current_falls_back_when_all_closed(gamma_events):
    markets = parsers.select_btc_5m_markets(gamma_events)
    now = parsers.parse_iso8601_to_epoch("2026-06-20T20:00:00Z")  # after all closes
    current, nxt = parsers.pick_current_and_next(markets, now)
    assert current is not None  # most recent kept as current
    assert nxt is None


# ---------------------------------------------------------------------------
# CLOB book parsing
# ---------------------------------------------------------------------------

def test_parse_clob_book_best_levels_and_notional(clob_book_up):
    book = parsers.parse_clob_book(clob_book_up)
    assert book["best_ask"] == 0.71        # lowest ask
    assert book["best_bid"] == 0.69        # highest bid
    # top ask notional = 0.71 * 90
    assert round(book["top_ask_notional_usd"], 2) == round(0.71 * 90.0, 2)
    assert round(book["top_bid_notional_usd"], 2) == round(0.69 * 120.0, 2)


def test_parse_clob_book_empty_is_none():
    book = parsers.parse_clob_book({"bids": [], "asks": []})
    assert book["best_ask"] is None
    assert book["best_bid"] is None
    assert book["top_ask_notional_usd"] is None
    assert parsers.parse_clob_book(None)["best_ask"] is None


# ---------------------------------------------------------------------------
# spot parsing
# ---------------------------------------------------------------------------

def test_parse_coinbase_spot(coinbase_spot):
    assert parsers.parse_coinbase_spot(coinbase_spot) == 64928.41
    assert parsers.parse_coinbase_spot({}) is None
    assert parsers.parse_coinbase_spot({"data": {}}) is None


def test_parse_binance_spot(binance_spot):
    assert parsers.parse_binance_spot(binance_spot) == 64931.55
    assert parsers.parse_binance_spot({}) is None
