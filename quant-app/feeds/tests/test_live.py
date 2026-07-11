"""Offline tests for the live I/O sources using an INJECTED http_get so no real
network is touched. Verifies snapshot assembly, last-good caching, the spot
provider abstraction, and btc_price_open interval behaviour."""

from __future__ import annotations

from feeds import live, parsers
from feeds.tests.conftest import load_fixture


def make_fake_http(routes):
    """Return an http_get(url)->json that dispatches by substring match."""

    def _http(url):
        for needle, payload in routes.items():
            if needle in url:
                return payload
        return None

    return _http


def build_routes():
    gamma = load_fixture("gamma_events.json")
    up = load_fixture("clob_book_up.json")
    down = load_fixture("clob_book_down.json")
    coinbase = load_fixture("coinbase_spot.json")
    return {
        "gamma-api.polymarket.com/events": gamma,
        "token_id=111111111111": up,
        "token_id=222222222222": down,
        "coinbase.com": coinbase,
    }


# ---------------------------------------------------------------------------
# spot sources
# ---------------------------------------------------------------------------

def test_coinbase_spot_source_fetch_and_last_good():
    routes = {"coinbase.com": load_fixture("coinbase_spot.json")}
    src = live.CoinbaseSpotSource(http_get=make_fake_http(routes))
    assert src.fetch() == 64928.41
    # simulate feed dropping: returns last-good
    src._http_get = lambda u: None
    assert src.fetch() == 64928.41


def test_binance_spot_source_fetch():
    routes = {"binance.com": load_fixture("binance_spot.json")}
    src = live.BinanceSpotSource(http_get=make_fake_http(routes))
    assert src.fetch() == 64931.55


def test_make_spot_source_provider_choice():
    assert isinstance(live.make_spot_source("coinbase"), live.CoinbaseSpotSource)
    assert isinstance(live.make_spot_source("binance"), live.BinanceSpotSource)
    try:
        live.make_spot_source("kraken")
        assert False, "should reject unknown provider"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# interval open tracker
# ---------------------------------------------------------------------------

def test_interval_open_tracker_holds_then_resets():
    base = parsers.parse_iso8601_to_epoch("2026-06-20T18:00:00Z")
    t = live.IntervalOpenTracker(interval_sec=300)
    assert t.update(base + 1, 64900.0) == 64900.0
    # same interval: open held constant even if price moves
    assert t.update(base + 120, 65000.0) == 64900.0
    assert t.update(base + 299, 65100.0) == 64900.0
    # new interval: open resets to the new first price
    assert t.update(base + 300, 65200.0) == 65200.0
    assert t.update(base + 360, 65300.0) == 65200.0


# ---------------------------------------------------------------------------
# Polymarket snapshot source
# ---------------------------------------------------------------------------

def test_polymarket_snapshot_assembly(monkeypatch):
    # freeze "now" inside the live module to 18:03 (current = 18:05 market)
    fixed_now = parsers.parse_iso8601_to_epoch("2026-06-20T18:03:00Z")
    monkeypatch.setattr(live, "now_epoch", lambda: fixed_now)

    http = make_fake_http(build_routes())
    spot = live.CoinbaseSpotSource(http_get=http)
    src = live.PolymarketSnapshotSource(spot_source=spot, http_get=http)

    snap = src.poll_once()
    assert snap is not None
    assert snap.market_slug == "btc-updown-2026-06-20-1405"
    assert snap.seconds_left == 120          # 18:05 - 18:03
    assert snap.clob_up_ask == 0.71
    assert snap.clob_down_ask == 0.30
    assert snap.clob_up_bid == 0.69
    assert snap.clob_down_bid == 0.28
    assert snap.gamma_up == 0.68
    assert snap.gamma_down == 0.32
    assert snap.min_spread == 0.02
    assert snap.btc_price_now == 64928.41
    assert snap.btc_price_open == 64928.41   # first price this interval
    assert snap.top_ask_notional_usd is not None
    assert snap.source == "clob+gamma"


def test_polymarket_returns_last_good_on_feed_down(monkeypatch):
    fixed_now = parsers.parse_iso8601_to_epoch("2026-06-20T18:03:00Z")
    monkeypatch.setattr(live, "now_epoch", lambda: fixed_now)
    http = make_fake_http(build_routes())
    spot = live.CoinbaseSpotSource(http_get=http)
    src = live.PolymarketSnapshotSource(spot_source=spot, http_get=http)

    good = src.poll_once()
    assert good is not None
    # now the gamma feed goes dark
    src._http_get = lambda u: None
    again = src.poll_once()
    assert again is good  # last-good returned, no crash
