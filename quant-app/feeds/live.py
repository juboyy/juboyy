"""
live.py — READ-ONLY live feeds for Polymarket market data and BTC spot.

STRICTLY READ-ONLY public data. NO private key, NO orders, NO funds, NO auth.
Only Python stdlib ``urllib.request`` is used for HTTP (no requests/aiohttp).

This module is the I/O boundary: it fetches raw JSON from the official PUBLIC
endpoints and hands it to the pure parsers in ``parsers.py``. All network and
clock reads live here so the parsers stay deterministic and offline-testable.

Official public endpoints (no key needed — see dashboard SECURITY_AUDIT.md):
  * GAMMA : https://gamma-api.polymarket.com/events
  * CLOB  : https://clob.polymarket.com/book?token_id=<id>
  * SPOT  : https://api.coinbase.com/v2/prices/BTC-USD/spot   (default)
            https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT (alt)

Failure handling: every fetch returns ``None`` (or last-good) on
timeout/error/garbage; sources stamp ``age_sec`` so staleness is visible.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from engine.contracts import MarketSnapshot
from engine.datasource import BtcSpotSource, MarketSnapshotSource

from . import parsers

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
CLOB_BOOK_URL = "https://clob.polymarket.com/book"
COINBASE_SPOT_URL = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
BINANCE_SPOT_URL = "https://api.binance.com/api/v3/ticker/price"

USER_AGENT = "juboyy-quant-feeds/1.0 (read-only public market data)"
DEFAULT_TIMEOUT = 8.0


# ---------------------------------------------------------------------------
# clock + http helpers (the ONLY place clock/network are read)
# ---------------------------------------------------------------------------

def now_epoch() -> float:
    return time.time()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http_get_json(url: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[Any]:
    """GET a URL and decode JSON. Returns ``None`` on any failure (read-only)."""
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        return None


# ---------------------------------------------------------------------------
# BTC spot sources (operator-selectable provider abstraction)
# ---------------------------------------------------------------------------
#
# This RESOLVES the engine README "Open decision: BTC spot source": the concrete
# live BTC spot feed is implemented here as a READ-ONLY public REST feed (no key,
# no funds). The operator chooses the provider ("coinbase" | "binance"); both
# sit behind the same ``BtcSpotSource`` interface, so the spine is unchanged.

class _BasePublicSpotSource(BtcSpotSource):
    """Common live-spot plumbing: fetch + cache last-good + age stamping."""

    name = "public-spot"
    url = ""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT, http_get=None):
        self._timeout = timeout
        self._http_get = http_get or (lambda u: _http_get_json(u, self._timeout))
        self._last_price: Optional[float] = None
        self._last_epoch: Optional[float] = None

    def _parse(self, payload: Any) -> Optional[float]:  # pragma: no cover - abstract
        raise NotImplementedError

    def fetch(self) -> Optional[float]:
        """Fetch the current spot price; cache & return last-good on failure."""
        payload = self._http_get(self.url)
        price = self._parse(payload)
        if price is not None and price > 0:
            self._last_price = price
            self._last_epoch = now_epoch()
            return price
        return self._last_price  # last-good (may be None)

    def age_sec(self) -> Optional[int]:
        if self._last_epoch is None:
            return None
        return int(round(now_epoch() - self._last_epoch))

    def price_at(self, ts: str) -> Optional[float]:
        """``BtcSpotSource`` contract. Live feed has no history, so the latest
        fetched price is the best estimate at any recent ``ts``."""
        return self.fetch()


class CoinbaseSpotSource(_BasePublicSpotSource):
    name = "coinbase"
    url = COINBASE_SPOT_URL

    def _parse(self, payload: Any) -> Optional[float]:
        return parsers.parse_coinbase_spot(payload)


class BinanceSpotSource(_BasePublicSpotSource):
    name = "binance"
    url = BINANCE_SPOT_URL + "?" + urllib.parse.urlencode({"symbol": "BTCUSDT"})

    def _parse(self, payload: Any) -> Optional[float]:
        return parsers.parse_binance_spot(payload)


_SPOT_PROVIDERS = {
    "coinbase": CoinbaseSpotSource,
    "binance": BinanceSpotSource,
}


def make_spot_source(provider: str = "coinbase", **kwargs) -> _BasePublicSpotSource:
    """Operator's choice of READ-ONLY public BTC spot provider."""
    key = (provider or "coinbase").lower()
    if key not in _SPOT_PROVIDERS:
        raise ValueError(
            f"unknown spot provider {provider!r}; choose from "
            f"{sorted(_SPOT_PROVIDERS)}"
        )
    return _SPOT_PROVIDERS[key](**kwargs)


# ---------------------------------------------------------------------------
# btc_price_open tracking
# ---------------------------------------------------------------------------

class IntervalOpenTracker:
    """Holds ``btc_price_open`` constant within a 5-min interval, resetting at
    each new interval boundary.

    Definition (resolves how the market "open" is captured): the **first BTC
    spot price observed at or after each interval start** is recorded and carried
    as ``btc_price_open`` for every snapshot in that interval; it only changes
    when the interval bucket key (``epoch // 300``) advances.
    """

    def __init__(self, interval_sec: int = 300):
        self.interval_sec = interval_sec
        self._bucket: Optional[int] = None
        self._open_price: Optional[float] = None

    def update(self, now_epoch_val: float, price_now: Optional[float]) -> Optional[float]:
        bucket = parsers.interval_open_key(now_epoch_val, self.interval_sec)
        if bucket != self._bucket:
            # new interval: capture this price as the open
            self._bucket = bucket
            self._open_price = price_now
        elif self._open_price is None and price_now is not None:
            # we entered the interval without a price; backfill first good one
            self._open_price = price_now
        return self._open_price


# ---------------------------------------------------------------------------
# Polymarket live snapshot source
# ---------------------------------------------------------------------------

class PolymarketSnapshotSource(MarketSnapshotSource):
    """Concrete READ-ONLY ``MarketSnapshotSource`` over the official PUBLIC
    Polymarket gamma + CLOB endpoints.

    It fetches the current BTC 5-minute up/down market (slug, gamma prices,
    min_spread, seconds_left) and the CLOB order book for both legs (asks/bids,
    top notional), then assembles a ``MarketSnapshot``. Combined with a
    ``BtcSpotSource`` it fills ``btc_price_open``/``btc_price_now``.

    Strictly read-only: no auth, no orders, no funds.
    """

    def __init__(
        self,
        spot_source: Optional[_BasePublicSpotSource] = None,
        gamma_query: Optional[dict] = None,
        timeout: float = DEFAULT_TIMEOUT,
        interval_sec: int = 300,
        http_get=None,
    ):
        self._timeout = timeout
        self._http_get = http_get or (lambda u: _http_get_json(u, self._timeout))
        self._spot = spot_source if spot_source is not None else make_spot_source("coinbase")
        # default gamma query: active, open, BTC-tagged events
        self._gamma_query = gamma_query or {
            "active": "true",
            "closed": "false",
            "limit": "100",
        }
        self._open_tracker = IntervalOpenTracker(interval_sec)
        self._last_good: Optional[MarketSnapshot] = None

    # -- raw fetch helpers (I/O) --------------------------------------------

    def _fetch_gamma_events(self) -> Optional[Any]:
        url = GAMMA_EVENTS_URL + "?" + urllib.parse.urlencode(self._gamma_query)
        return self._http_get(url)

    def _fetch_clob_book(self, token_id: Optional[str]) -> Optional[Any]:
        if not token_id:
            return None
        url = CLOB_BOOK_URL + "?" + urllib.parse.urlencode({"token_id": str(token_id)})
        return self._http_get(url)

    # -- snapshot assembly --------------------------------------------------

    def poll_once(self) -> Optional[MarketSnapshot]:
        """Fetch + assemble a single ``MarketSnapshot``. Returns last-good (or
        ``None``) on failure so the caller never crashes on a dropped poll."""
        t0 = now_epoch()
        events = self._fetch_gamma_events()
        if events is None:
            return self._last_good

        candidates = parsers.select_btc_5m_markets(events)
        current, _next = parsers.pick_current_and_next(candidates, t0)
        if current is None:
            return self._last_good

        gm = parsers.parse_gamma_market(current)

        up_book = parsers.parse_clob_book(self._fetch_clob_book(gm["clob_up_token_id"]))
        down_book = parsers.parse_clob_book(self._fetch_clob_book(gm["clob_down_token_id"]))

        price_now = self._spot.fetch() if self._spot else None
        price_open = self._open_tracker.update(t0, price_now)

        secs_left = parsers.seconds_left(gm["end_date"], t0)
        # age of the freshest underlying datum we used
        age = int(round(now_epoch() - t0))

        snap = MarketSnapshot(
            ts=now_iso(),
            market_slug=gm["slug"],
            seconds_left=secs_left,
            clob_up_ask=up_book["best_ask"],
            clob_down_ask=down_book["best_ask"],
            clob_up_bid=up_book["best_bid"],
            clob_down_bid=down_book["best_bid"],
            gamma_up=gm["gamma_up"],
            gamma_down=gm["gamma_down"],
            min_spread=gm["min_spread"],
            top_ask_notional_usd=up_book["top_ask_notional_usd"],
            top_bid_notional_usd=down_book["top_bid_notional_usd"],
            btc_price_open=price_open,
            btc_price_now=price_now,
            age_sec=age,
            source="clob+gamma",
        )
        self._last_good = snap
        return snap

    def snapshots(self) -> Iterator[MarketSnapshot]:
        """One-shot generator (the runner loop calls ``poll_once`` directly)."""
        snap = self.poll_once()
        if snap is not None:
            yield snap
