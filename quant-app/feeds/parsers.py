"""
parsers.py — PURE, deterministic parsers for the public Polymarket + BTC-spot
feeds. NO network I/O lives here, so every function is unit-testable offline
against saved JSON fixtures.

The fetch layer (``live.py``) calls these on raw decoded JSON; the parsers never
touch the clock or the network. ``None`` means unknown/unavailable (never ``0``),
matching ``05_DATA_CONTRACTS.md``.

Public endpoint response shapes handled here (all READ-ONLY, NO key):

  * gamma-api.polymarket.com/events  — events[].markets[] with ``slug``,
    ``outcomes``, ``outcomePrices``, ``clobTokenIds``, ``endDate``,
    ``spread``/``bestAsk``/``bestBid``.
  * clob.polymarket.com/book?token_id=  — ``{"bids":[{price,size}...],
    "asks":[{price,size}...]}`` (price-ascending or descending; we sort).
  * coinbase  /v2/prices/BTC-USD/spot — ``{"data":{"amount":"...", ...}}``
  * binance   /api/v3/ticker/price    — ``{"symbol":"BTCUSDT","price":"..."}``
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# small numeric coercion helpers
# ---------------------------------------------------------------------------

def _to_float(v: Any) -> Optional[float]:
    """Coerce JSON value to float; ``None``/blank/garbage -> ``None``."""
    if v is None:
        return None
    if isinstance(v, bool):  # bools are ints in python; never a price
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _maybe_json_list(v: Any) -> List[Any]:
    """Gamma returns some array fields as JSON-encoded strings; decode both."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, list) else []
        except ValueError:
            return []
    return []


# ---------------------------------------------------------------------------
# time helpers (pure: caller supplies "now")
# ---------------------------------------------------------------------------

def parse_iso8601_to_epoch(ts: Optional[str]) -> Optional[float]:
    """Parse an ISO-8601 UTC timestamp to epoch seconds. Pure, no clock read."""
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        from datetime import datetime

        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return None


def seconds_left(end_date: Optional[str], now_epoch: float) -> Optional[int]:
    """Whole seconds until ``end_date`` given a caller-supplied ``now_epoch``.

    Never negative-clamped *below* 0 silently swallowing data: a closed market
    returns a value <= 0 so the caller can decide it is stale / rolled over.
    """
    end = parse_iso8601_to_epoch(end_date)
    if end is None:
        return None
    return int(round(end - now_epoch))


# ---------------------------------------------------------------------------
# Gamma markets parsing
# ---------------------------------------------------------------------------

def _is_btc_5m_market(market: Dict[str, Any]) -> bool:
    """Heuristic: a BTC up/down 5-minute market.

    We match on slug/question text mentioning bitcoin/btc and the up-down or
    5-minute cadence. Kept loose but specific enough to exclude other assets.
    """
    blob = " ".join(
        str(market.get(k, "")).lower()
        for k in ("slug", "question", "title", "groupItemTitle")
    )
    if "btc" not in blob and "bitcoin" not in blob:
        return False
    # up/down framing or explicit 5m cadence markers
    return (
        "up" in blob
        or "down" in blob
        or "5m" in blob
        or "5-min" in blob
        or "5 min" in blob
    )


def _outcome_index(outcomes: List[Any], target: str) -> Optional[int]:
    """Index of the 'Up'/'Down' (or 'Yes'/'No') outcome, case-insensitive."""
    target = target.lower()
    synonyms = {
        "up": ("up", "yes"),
        "down": ("down", "no"),
    }.get(target, (target,))
    for i, o in enumerate(outcomes):
        if str(o).strip().lower() in synonyms:
            return i
    return None


def parse_gamma_market(market: Dict[str, Any]) -> Dict[str, Optional[Any]]:
    """Normalize ONE gamma market dict into the fields a snapshot needs.

    Returns a dict with: slug, end_date, gamma_up, gamma_down, min_spread,
    best_up_ask, best_down_ask, clob_up_token_id, clob_down_token_id.
    All unknowns are ``None``.
    """
    outcomes = _maybe_json_list(market.get("outcomes"))
    prices = _maybe_json_list(market.get("outcomePrices"))
    token_ids = _maybe_json_list(market.get("clobTokenIds"))

    up_i = _outcome_index(outcomes, "up")
    down_i = _outcome_index(outcomes, "down")

    def _at(arr: List[Any], i: Optional[int]) -> Optional[Any]:
        if i is None or i < 0 or i >= len(arr):
            return None
        return arr[i]

    gamma_up = _to_float(_at(prices, up_i))
    gamma_down = _to_float(_at(prices, down_i))

    return {
        "slug": market.get("slug"),
        "end_date": market.get("endDate") or market.get("end_date"),
        "gamma_up": gamma_up,
        "gamma_down": gamma_down,
        "min_spread": _to_float(market.get("spread")),
        # gamma sometimes exposes a single bestAsk/bestBid for the "yes" side
        "best_ask": _to_float(market.get("bestAsk")),
        "best_bid": _to_float(market.get("bestBid")),
        "clob_up_token_id": _at(token_ids, up_i),
        "clob_down_token_id": _at(token_ids, down_i),
    }


def select_btc_5m_markets(gamma_events_json: Any) -> List[Dict[str, Any]]:
    """From a decoded gamma ``/events`` response, return the candidate BTC 5-min
    markets (raw market dicts). Accepts either a list of events or a single
    event, each of which carries a ``markets`` list (or a bare market list).
    """
    events: List[Any]
    if isinstance(gamma_events_json, dict):
        events = [gamma_events_json]
    elif isinstance(gamma_events_json, list):
        events = gamma_events_json
    else:
        return []

    out: List[Dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        markets = ev.get("markets")
        if isinstance(markets, list):
            for m in markets:
                if isinstance(m, dict) and _is_btc_5m_market(m):
                    out.append(m)
        elif _is_btc_5m_market(ev):
            # the event itself looks like a market
            out.append(ev)
    return out


def pick_current_and_next(
    markets: List[Dict[str, Any]], now_epoch: float
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Given parsed-or-raw BTC 5-min markets, choose the CURRENT (soonest open
    market still in the future) and the NEXT one after it, ordered by end time.

    A market is "current" if its end is in the future and nearest to now.
    """
    enriched: List[Tuple[float, Dict[str, Any]]] = []
    for m in markets:
        end = parse_iso8601_to_epoch(m.get("endDate") or m.get("end_date"))
        if end is None:
            continue
        enriched.append((end, m))
    enriched.sort(key=lambda t: t[0])

    future = [m for (end, m) in enriched if end > now_epoch]
    if future:
        current = future[0]
        nxt = future[1] if len(future) > 1 else None
        return current, nxt
    # all closed: fall back to the most recent as "current"
    if enriched:
        return enriched[-1][1], None
    return None, None


# ---------------------------------------------------------------------------
# CLOB order book parsing
# ---------------------------------------------------------------------------

def parse_clob_book(book_json: Any) -> Dict[str, Optional[float]]:
    """Parse a CLOB ``/book`` response into best ask/bid + top notional.

    Response shape: ``{"bids": [{"price","size"}...], "asks": [...]}``.
    Best ask = lowest ask price; best bid = highest bid price. ``size`` is in
    shares; notional = price * size (USDC, since shares settle at $1).
    """
    if not isinstance(book_json, dict):
        return {
            "best_ask": None,
            "best_bid": None,
            "top_ask_notional_usd": None,
            "top_bid_notional_usd": None,
        }

    def _levels(key: str) -> List[Tuple[float, float]]:
        out: List[Tuple[float, float]] = []
        for lvl in book_json.get(key) or []:
            if isinstance(lvl, dict):
                p = _to_float(lvl.get("price"))
                s = _to_float(lvl.get("size"))
            elif isinstance(lvl, (list, tuple)) and len(lvl) >= 2:
                p = _to_float(lvl[0])
                s = _to_float(lvl[1])
            else:
                p = s = None
            if p is not None:
                out.append((p, s if s is not None else 0.0))
        return out

    asks = _levels("asks")
    bids = _levels("bids")

    best_ask = min(asks, key=lambda t: t[0]) if asks else None
    best_bid = max(bids, key=lambda t: t[0]) if bids else None

    return {
        "best_ask": best_ask[0] if best_ask else None,
        "best_bid": best_bid[0] if best_bid else None,
        "top_ask_notional_usd": (best_ask[0] * best_ask[1]) if best_ask else None,
        "top_bid_notional_usd": (best_bid[0] * best_bid[1]) if best_bid else None,
    }


# ---------------------------------------------------------------------------
# BTC spot parsing
# ---------------------------------------------------------------------------

def parse_coinbase_spot(json_obj: Any) -> Optional[float]:
    """Coinbase ``/v2/prices/BTC-USD/spot`` -> ``{"data":{"amount":"64850.1"}}``."""
    if not isinstance(json_obj, dict):
        return None
    data = json_obj.get("data")
    if not isinstance(data, dict):
        return None
    return _to_float(data.get("amount"))


def parse_binance_spot(json_obj: Any) -> Optional[float]:
    """Binance ``/api/v3/ticker/price`` -> ``{"symbol":"BTCUSDT","price":"..."}``."""
    if not isinstance(json_obj, dict):
        return None
    return _to_float(json_obj.get("price"))


def interval_open_key(now_epoch: float, interval_sec: int = 300) -> int:
    """Bucket ``now`` into its 5-minute interval start (epoch seconds).

    This is how ``btc_price_open`` is anchored: the first spot price observed at
    or after each interval boundary is held constant as the interval's open and
    only resets when the bucket key changes. Pure function of the timestamp.
    """
    if interval_sec <= 0:
        interval_sec = 300
    return int(now_epoch // interval_sec) * interval_sec
