"""
feeds — LIVE, READ-ONLY public market-data feeds + capture runner.

STRICTLY READ-ONLY public data. NO private key, NO orders, NO funds, NO auth.
Only Python stdlib ``urllib.request`` is used for HTTP.

  * ``parsers``        — pure, deterministic parsers (offline unit-testable).
  * ``live``           — I/O fetch layer: ``PolymarketSnapshotSource`` (gamma+CLOB)
                         and ``CoinbaseSpotSource`` / ``BinanceSpotSource``.
  * ``capture_runner`` — the snapshot-capture loop (builds the backtest dataset).
"""

from __future__ import annotations

__all__ = [
    "parsers",
    "live",
    "capture_runner",
]
