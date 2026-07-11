"""
outcome_collector.py — READ-ONLY collector of CHEAP Polymarket outcomes + their
resolution criteria, feeding the OFFLINE convexity scanner.

Pipeline:

    fetch (network, public, NO key)
        -> parse gamma JSON into ``OutcomeCandidate`` records   (PURE)
        -> write ``candidates.jsonl``
        -> ``scanner.scan(candidates, analyzer, params)``        (OFFLINE)
        -> write ``watchlist.jsonl``

Only CHEAP outcomes (price <= ``MAX_CHEAP_PRICE`` = 0.15, the scanner's convex
zone) are emitted as candidates, each carrying the market's resolution text so an
analyzer can judge how misread-able the criteria are.

Design mirrors ``feeds/parsers.py`` / ``feeds/live.py``: the PURE mapping
(``gamma_events_to_candidates``) has NO network and unit-tests offline against a
saved fixture; the network fetch is an injectable seam (``fetcher=``) so the whole
collect->scan->watchlist pipeline runs offline in tests.

HARD INVARIANTS:
  * STRICTLY READ-ONLY public data — NO private key, NO orders, NO funds, NO auth.
  * Default analyzer is the OFFLINE HeuristicAnalyzer (no LLM in the default path).
  * stdlib-only for the network path (``urllib`` via ``feeds.live._http_get_json``).

CLI::

    python -m feeds.outcome_collector [--once] [--analyzer heuristic|claude] \
        [--runtime DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Callable, List, Optional

from scanner.analyzer import make_analyzer
from scanner.contracts import OutcomeCandidate
from scanner.scan import ScanParams, scan, to_jsonl

from . import parsers

# The scanner's convex zone: only outcomes priced at/below this are candidates.
MAX_CHEAP_PRICE = 0.15

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
DEFAULT_CANDIDATES_NAME = "candidates.jsonl"
DEFAULT_WATCHLIST_NAME = "watchlist.jsonl"
DEFAULT_RUNTIME = "runtime"


# ---------------------------------------------------------------------------
# PURE mapping: gamma JSON -> OutcomeCandidate (no network, no clock)
# ---------------------------------------------------------------------------

def _resolution_text(market: dict) -> str:
    """Best-effort extraction of the market's resolution criteria text.

    Gamma exposes the rules in ``description`` (and sometimes a separate
    ``resolutionSource``). We concatenate what is present; empty if none.
    """
    parts: List[str] = []
    for key in ("description", "resolutionSource", "resolution_source"):
        v = market.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " ".join(parts)


def market_to_candidates(market: dict, *, max_price: float = MAX_CHEAP_PRICE) -> List[OutcomeCandidate]:
    """Map ONE gamma market dict to zero+ CHEAP ``OutcomeCandidate`` records.

    One candidate is produced per outcome whose price is <= ``max_price``. Prices
    and outcome labels come from the gamma ``outcomes`` / ``outcomePrices`` arrays
    (which gamma may JSON-encode as strings — handled by ``_maybe_json_list``).
    """
    outcomes = parsers._maybe_json_list(market.get("outcomes"))
    prices = parsers._maybe_json_list(market.get("outcomePrices"))
    slug = market.get("slug") or market.get("id") or ""
    end_iso = market.get("endDate") or market.get("end_date") or ""
    res_text = _resolution_text(market)
    notional = parsers._to_float(market.get("liquidity")) or parsers._to_float(
        market.get("liquidityNum")
    )
    if notional is None:
        notional = 0.0

    out: List[OutcomeCandidate] = []
    for i, label in enumerate(outcomes):
        if i >= len(prices):
            break
        price = parsers._to_float(prices[i])
        if price is None or price > max_price or price <= 0:
            continue
        out.append(
            OutcomeCandidate(
                market_slug=str(slug),
                outcome=str(label),
                price=float(price),
                resolution_text=res_text,
                end_iso=str(end_iso),
                top_ask_notional_usd=float(notional),
            )
        )
    return out


def gamma_events_to_candidates(
    gamma_events_json: Any, *, max_price: float = MAX_CHEAP_PRICE
) -> List[OutcomeCandidate]:
    """Map a decoded gamma ``/events`` payload to CHEAP ``OutcomeCandidate``s.

    PURE: accepts a list of events (or a single event), each carrying a
    ``markets`` list (or being a bare market), and flattens every cheap outcome.
    Offline-testable against a saved fixture.
    """
    if isinstance(gamma_events_json, dict):
        events = [gamma_events_json]
    elif isinstance(gamma_events_json, list):
        events = gamma_events_json
    else:
        return []

    # Flatten to the underlying market dicts (an event holds a ``markets`` list,
    # or the event itself may already be a bare market).
    markets: List[dict] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        ev_markets = ev.get("markets")
        if isinstance(ev_markets, list):
            markets.extend(m for m in ev_markets if isinstance(m, dict))
        else:
            markets.append(ev)

    candidates: List[OutcomeCandidate] = []
    for m in markets:
        candidates.extend(market_to_candidates(m, max_price=max_price))
    return candidates


def candidates_to_jsonl(candidates: List[OutcomeCandidate]) -> str:
    """Serialize candidates to newline-delimited JSON (one per line)."""
    return "\n".join(json.dumps(c.to_dict(), sort_keys=True) for c in candidates)


# ---------------------------------------------------------------------------
# Network fetch seam (I/O) — injectable so the pipeline tests run offline
# ---------------------------------------------------------------------------

def default_fetcher(gamma_query: Optional[dict] = None, timeout: float = 8.0) -> Any:
    """Fetch the public gamma ``/events`` payload (READ-ONLY, NO key).

    Lazily imports ``feeds.live._http_get_json`` so unit tests that inject a fake
    fetcher never need the network path.
    """
    from .live import _http_get_json  # lazy: stdlib urllib under the hood

    query = gamma_query or {"active": "true", "closed": "false", "limit": "200"}
    url = GAMMA_EVENTS_URL + "?" + urllib.parse.urlencode(query)
    return _http_get_json(url, timeout)


# ---------------------------------------------------------------------------
# Pipeline: collect -> scan -> watchlist (orchestration; pure given seams)
# ---------------------------------------------------------------------------

def collect(
    *,
    fetcher: Callable[[], Any],
    analyzer=None,
    params: Optional[ScanParams] = None,
    runtime_dir: str = DEFAULT_RUNTIME,
    max_price: float = MAX_CHEAP_PRICE,
    write: bool = True,
) -> dict:
    """Run the full collect->scan->watchlist pipeline once.

    * ``fetcher`` — zero-arg callable returning a decoded gamma payload (inject a
      fake in tests; ``default_fetcher`` hits the public endpoint live).
    * ``analyzer`` — defaults to the OFFLINE HeuristicAnalyzer (no LLM).
    * Writes ``candidates.jsonl`` and ``watchlist.jsonl`` under ``runtime_dir``
      when ``write`` is True.

    Returns a summary dict: candidate count, watchlist count, and the paths.
    """
    if analyzer is None:
        analyzer = make_analyzer("heuristic")
    if params is None:
        params = ScanParams()

    payload = fetcher()
    candidates = gamma_events_to_candidates(payload, max_price=max_price)
    items = scan(candidates, analyzer, params)

    cand_path = Path(runtime_dir) / DEFAULT_CANDIDATES_NAME
    watch_path = Path(runtime_dir) / DEFAULT_WATCHLIST_NAME

    if write:
        Path(runtime_dir).mkdir(parents=True, exist_ok=True)
        cand_text = candidates_to_jsonl(candidates)
        cand_path.write_text(cand_text + ("\n" if cand_text else ""), encoding="utf-8")
        watch_text = to_jsonl(items)
        watch_path.write_text(watch_text + ("\n" if watch_text else ""), encoding="utf-8")

    return {
        "candidates": len(candidates),
        "watchlist": len(items),
        "candidates_path": str(cand_path),
        "watchlist_path": str(watch_path),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="feeds.outcome_collector",
        description="READ-ONLY collector of cheap Polymarket outcomes -> offline watchlist.",
    )
    p.add_argument("--once", action="store_true", help="collect once and exit (default)")
    p.add_argument(
        "--analyzer",
        choices=["heuristic", "claude"],
        default="heuristic",
        help="analyzer for the scan (default heuristic, fully offline, no key).",
    )
    p.add_argument(
        "--runtime",
        default=DEFAULT_RUNTIME,
        help=f"runtime dir for candidates/watchlist JSONL (default {DEFAULT_RUNTIME})",
    )
    p.add_argument(
        "--max-price",
        type=float,
        default=MAX_CHEAP_PRICE,
        help=f"only collect outcomes priced <= this (default {MAX_CHEAP_PRICE})",
    )
    p.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout seconds")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    analyzer = make_analyzer(args.analyzer)

    summary = collect(
        fetcher=lambda: default_fetcher(timeout=args.timeout),
        analyzer=analyzer,
        runtime_dir=args.runtime,
        max_price=args.max_price,
        write=True,
    )
    print(
        f"[collector] candidates={summary['candidates']} "
        f"watchlist={summary['watchlist']} -> {summary['watchlist_path']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
