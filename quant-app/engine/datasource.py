"""
datasource.py — pluggable market/spot data interfaces.

Abstract sources decouple the deterministic spine from where snapshots come from.
The same spine runs live and in backtest; only the source differs (`02 §2`).

Provided:
  - `MarketSnapshotSource` (abstract): yields `MarketSnapshot` objects.
  - `BtcSpotSource` (abstract): yields (ts, btc_price) for momentum.
  - `RecordedSource`: replays a JSONL fixture of normalized records.
  - `MockSource`: deterministic synthetic snapshots (seeded jitter).
  - `LiveBtcSpotSource`: STUB, NOT implemented — raises NotImplementedError.

No clock reads inside the deterministic path: timestamps are read from the data.
"""

from __future__ import annotations

import abc
import json
import random
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from .contracts import MarketSnapshot


class MarketSnapshotSource(abc.ABC):
    """Abstract source of `MarketSnapshot`s (oldest → newest)."""

    @abc.abstractmethod
    def snapshots(self) -> Iterator[MarketSnapshot]:
        raise NotImplementedError


class BtcSpotSource(abc.ABC):
    """Abstract source of BTC spot prices aligned to snapshot timestamps."""

    @abc.abstractmethod
    def price_at(self, ts: str) -> Optional[float]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Recorded (JSONL fixture) source
# ---------------------------------------------------------------------------

class RecordedSource(MarketSnapshotSource):
    """Reads normalized records from a JSONL file (one JSON object per line).

    Each line is a `MarketSnapshot` dict (possibly augmented with backtest-only
    keys like `settle_side`); unknown keys are ignored when building the snapshot.
    """

    def __init__(self, path: str):
        self.path = Path(path)

    def raw_records(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue

    def snapshots(self) -> Iterator[MarketSnapshot]:
        for rec in self.raw_records():
            yield MarketSnapshot.from_dict(rec)


# ---------------------------------------------------------------------------
# Mock (deterministic synthetic) source
# ---------------------------------------------------------------------------

class MockSource(MarketSnapshotSource):
    """Deterministic synthetic snapshots for tests/demos.

    Generates `n` snapshots counting down through the entry window with a steady
    BTC move and a seeded jitter so runs are reproducible (same seed ⇒ same data).
    """

    def __init__(
        self,
        n: int = 12,
        seed: int = 1337,
        market_slug: str = "btc-updown-mock",
        btc_open: float = 64000.0,
        btc_drift: float = 12.0,
        start_seconds_left: int = 150,
        step_sec: int = 5,
    ):
        self.n = n
        self.seed = seed
        self.market_slug = market_slug
        self.btc_open = btc_open
        self.btc_drift = btc_drift
        self.start_seconds_left = start_seconds_left
        self.step_sec = step_sec

    def snapshots(self) -> Iterator[MarketSnapshot]:
        rng = random.Random(self.seed)
        price = self.btc_open
        for i in range(self.n):
            price = price + self.btc_drift + rng.uniform(-2.0, 2.0)
            seconds_left = self.start_seconds_left - i * self.step_sec
            up_ask = min(0.95, 0.55 + 0.02 * i)
            yield MarketSnapshot(
                ts=f"2026-06-20T14:{i:02d}:00Z",
                market_slug=self.market_slug,
                seconds_left=seconds_left,
                clob_up_ask=round(up_ask, 3),
                clob_down_ask=round(1.0 - up_ask, 3),
                clob_up_bid=round(up_ask - 0.02, 3),
                clob_down_bid=round(1.0 - up_ask - 0.02, 3),
                gamma_up=round(up_ask - 0.01, 3),
                gamma_down=round(1.0 - up_ask + 0.01, 3),
                min_spread=0.02,
                top_ask_notional_usd=64.0,
                top_bid_notional_usd=51.0,
                btc_price_open=self.btc_open,
                btc_price_now=round(price, 2),
                age_sec=2,
                source="mock",
            )


# ---------------------------------------------------------------------------
# Live BTC spot — GATED stub (open decision per the prompt)
# ---------------------------------------------------------------------------

class LiveBtcSpotSource(BtcSpotSource):
    """STUB — the concrete live BTC spot feed is GATED on the owner.

    The choice of concrete feed (e.g. Binance or Coinbase websocket / REST) is an
    OPEN DECISION owned by the project owner and is NOT implemented in the
    deterministic core. Live execution + any networked spot feed live in the
    separate crypto workstream (`crypto/`, `02 §2`), behind the same
    `BtcSpotSource` interface so the spine is unchanged.

    Implementing this class requires: (1) a chosen venue, (2) network access (which
    is forbidden inside the pure indicator/signal/decision path), and (3) the owner
    sign-off recorded in the runbook. Until then it raises.
    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "LiveBtcSpotSource is GATED on the owner: the concrete BTC spot feed "
            "(e.g. Binance/Coinbase websocket) is an open decision and is not part "
            "of the deterministic core. Use RecordedSource/MockSource for backtests "
            "and dry-run; wire the live feed in the crypto/ workstream behind this "
            "interface once the owner has chosen the venue."
        )

    def price_at(self, ts: str) -> Optional[float]:  # pragma: no cover - never reached
        raise NotImplementedError
