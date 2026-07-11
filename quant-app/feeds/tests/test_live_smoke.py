"""Best-effort LIVE smoke test (one real fetch each).

Guarded so a sandbox with no outbound network NEVER fails the suite: any network
error / blocked socket -> the test is SKIPPED, not failed. Run with
``-rs`` to see whether the live fetch succeeded or was skipped.

These hit ONLY the official PUBLIC read-only endpoints (no key, no orders).
"""

from __future__ import annotations

import os

import pytest

from feeds import live

# Opt-out switch for CI that wants zero outbound attempts.
_DISABLED = os.environ.get("FEEDS_DISABLE_LIVE_SMOKE") == "1"


@pytest.mark.skipif(_DISABLED, reason="FEEDS_DISABLE_LIVE_SMOKE=1 set")
def test_live_coinbase_spot_smoke():
    src = live.CoinbaseSpotSource(timeout=6.0)
    price = src.fetch()
    if price is None:
        pytest.skip("live coinbase spot fetch blocked/unavailable in sandbox")
    assert price > 0, "BTC spot should be a positive USD price"


@pytest.mark.skipif(_DISABLED, reason="FEEDS_DISABLE_LIVE_SMOKE=1 set")
def test_live_polymarket_snapshot_smoke():
    src = live.PolymarketSnapshotSource(timeout=6.0)
    snap = src.poll_once()
    if snap is None:
        pytest.skip("live Polymarket gamma/CLOB fetch blocked/unavailable in sandbox")
    # if we got a snapshot, it must at least carry a slug
    assert snap.market_slug is not None
