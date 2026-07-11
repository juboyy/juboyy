"""
capture_runner.py — READ-ONLY data-collection loop.

Every ``poll_sec`` it pulls a snapshot from a ``MarketSnapshotSource`` (the live
``PolymarketSnapshotSource`` by default, which already folds in the BTC spot +
``btc_price_open``) and appends the normalized ``MarketSnapshot`` to a runtime
JSONL via ``engine.capture.CaptureRecorder``. Run over >= 60 days this produces
the backtest dataset described in ``03_QUANT_STRATEGY.md §9``.

STRICTLY READ-ONLY: no private key, no orders, no funds, no auth. stdlib only.

Usage::

    cd quant-app
    python -m feeds.capture_runner --duration 3600 --poll-sec 5 --runtime runtime
    python -m feeds.capture_runner --once
    python -m feeds.capture_runner --dry            # parse/assemble, NO write
    python -m feeds.capture_runner --once --spot binance
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from engine.capture import CaptureRecorder
from engine.datasource import MarketSnapshotSource

DEFAULT_POLL_SEC = 5
DEFAULT_RUNTIME = "runtime"
DEFAULT_CAPTURE_NAME = "captured_snapshots.jsonl"


def _poll_source(source: MarketSnapshotSource):
    """Pull one snapshot from a source. Supports both the live
    ``poll_once`` fast-path and any generic ``snapshots()`` source."""
    poll_once = getattr(source, "poll_once", None)
    if callable(poll_once):
        return poll_once()
    for snap in source.snapshots():
        return snap
    return None


def run_capture(
    source: MarketSnapshotSource,
    recorder: Optional[CaptureRecorder],
    *,
    once: bool = False,
    duration: Optional[float] = None,
    max_polls: Optional[int] = None,
    poll_sec: float = DEFAULT_POLL_SEC,
    dry: bool = False,
    sleep_fn=time.sleep,
    now_fn=time.monotonic,
    log=lambda msg: print(msg, file=sys.stderr),
) -> int:
    """Drive the capture loop. Dependency-injected source/recorder/clock so it is
    end-to-end testable offline. Returns the number of records written.

    * ``once``      — poll exactly once and stop.
    * ``duration``  — run until this many seconds elapse (``None`` = forever).
    * ``max_polls`` — stop after this many polls (``None`` = unbounded).
    * ``dry``       — assemble snapshots but DO NOT write (parse-only).
    """
    written = 0
    polls = 0
    start = now_fn()

    while True:
        snap = None
        try:
            snap = _poll_source(source)
        except Exception as exc:  # never let a transient feed error kill capture
            log(f"[capture] poll error: {exc!r}")

        polls += 1
        if snap is None:
            log("[capture] no snapshot this poll (stale/feed down); skipping")
        else:
            if dry:
                log(
                    f"[capture] DRY slug={snap.market_slug} "
                    f"secs_left={snap.seconds_left} up_ask={snap.clob_up_ask} "
                    f"btc_open={snap.btc_price_open} btc_now={snap.btc_price_now}"
                )
            elif recorder is not None:
                recorder.record(snap)
                written += 1

        if once:
            break
        if max_polls is not None and polls >= max_polls:
            break
        if duration is not None and (now_fn() - start) >= duration:
            break
        sleep_fn(poll_sec)

    log(f"[capture] done: polls={polls} written={written} dry={dry}")
    return written


def build_default_source(spot_provider: str = "coinbase", timeout: float = 8.0):
    """Construct the live read-only Polymarket source (imported lazily so unit
    tests that inject a fake source never need network deps)."""
    from .live import PolymarketSnapshotSource, make_spot_source

    spot = make_spot_source(spot_provider, timeout=timeout)
    return PolymarketSnapshotSource(spot_source=spot, timeout=timeout)


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="feeds.capture_runner",
        description="READ-ONLY Polymarket BTC-5m + BTC-spot snapshot capture loop.",
    )
    p.add_argument("--once", action="store_true", help="poll exactly once and exit")
    p.add_argument(
        "--duration",
        type=float,
        default=None,
        help="run for N seconds then stop (default: run forever)",
    )
    p.add_argument(
        "--max-polls",
        type=int,
        default=None,
        help="stop after N polls (default: unbounded)",
    )
    p.add_argument(
        "--poll-sec",
        type=float,
        default=DEFAULT_POLL_SEC,
        help=f"seconds between polls (default {DEFAULT_POLL_SEC})",
    )
    p.add_argument(
        "--runtime",
        default=DEFAULT_RUNTIME,
        help=f"runtime dir for the capture JSONL (default {DEFAULT_RUNTIME})",
    )
    p.add_argument(
        "--dry",
        action="store_true",
        help="parse/assemble only; do NOT write any file",
    )
    p.add_argument(
        "--spot",
        default="coinbase",
        choices=["coinbase", "binance"],
        help="public BTC spot provider (operator's choice, read-only)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="HTTP timeout seconds per request",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    source = build_default_source(spot_provider=args.spot, timeout=args.timeout)

    recorder = None
    if not args.dry:
        path = f"{args.runtime.rstrip('/')}/{DEFAULT_CAPTURE_NAME}"
        recorder = CaptureRecorder(path)

    run_capture(
        source,
        recorder,
        once=args.once,
        duration=args.duration,
        max_polls=args.max_polls,
        poll_sec=args.poll_sec,
        dry=args.dry,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
