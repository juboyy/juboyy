"""
capture.py — data-capture recorder.

Appends normalized `MarketSnapshot` records (+ optional spot/settlement) to
`runtime/captured_snapshots.jsonl`, one JSON object per line, so a backtest dataset
can be accumulated over time (addresses the "need >= 60d data" gap in `03 §9`).

The recorder itself does file I/O (it is the capture boundary), but it never
mutates or decides — it just normalizes and appends. It does not read the clock for
any decision; `ts` comes from the snapshot.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Optional

from .contracts import MarketSnapshot

DEFAULT_PATH = "runtime/captured_snapshots.jsonl"


def normalize(snapshot: MarketSnapshot, settle_side: Optional[str] = None) -> dict:
    """Return the canonical dict to persist. `settle_side` (the realized outcome,
    'up'/'down') is an optional backtest-only label revealed only after T_close."""
    rec = snapshot.to_dict()
    if settle_side is not None:
        rec["settle_side"] = settle_side
    return rec


class CaptureRecorder:
    """Append-only JSONL recorder for snapshots."""

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = Path(path)

    def _ensure_dir(self) -> None:
        if self.path.parent and not self.path.parent.exists():
            os.makedirs(self.path.parent, exist_ok=True)

    def record(self, snapshot: MarketSnapshot, settle_side: Optional[str] = None) -> dict:
        """Append one normalized record; returns it."""
        self._ensure_dir()
        rec = normalize(snapshot, settle_side)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def record_stream(self, snapshots: Iterable[MarketSnapshot]) -> int:
        """Append a stream of snapshots; returns the count written."""
        self._ensure_dir()
        count = 0
        with open(self.path, "a", encoding="utf-8") as fh:
            for snap in snapshots:
                fh.write(json.dumps(normalize(snap), ensure_ascii=False) + "\n")
                count += 1
        return count

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with open(self.path, "r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
