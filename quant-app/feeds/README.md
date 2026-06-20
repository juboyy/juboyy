# feeds — LIVE, READ-ONLY market-data feeds + capture runner

This package provides the **live, read-only** market-data feeds and the
data-collection runner that records normalized `MarketSnapshot`s for the
backtest dataset (`docs/03_QUANT_STRATEGY.md §9`, `docs/05_DATA_CONTRACTS.md`).

> **STRICTLY READ-ONLY.** No private key. No orders. No funds. No auth. No LLM.
> Only Python stdlib `urllib.request` is used for HTTP (no `requests`/`aiohttp`).
> It fetches **public** market data and writes a local JSONL capture file —
> nothing else.

## What it does

1. **`PolymarketSnapshotSource`** (`live.py`) — a concrete
   `engine.datasource.MarketSnapshotSource`. It fetches the current BTC
   5-minute up/down market from the official **public** Polymarket gamma + CLOB
   endpoints and assembles a `MarketSnapshot`: `market_slug`, `seconds_left` to
   close, `clob_up_ask`/`clob_down_ask` (+ bids), `gamma_up`/`gamma_down`,
   `min_spread`, and top-of-book notional. It picks the current market (and
   exposes the next) and returns last-good / `None` on failures, stamping
   `age_sec` for staleness.

2. **BTC spot feed** (`CoinbaseSpotSource` / `BinanceSpotSource`, `live.py`) —
   concrete `engine.datasource.BtcSpotSource` implementations behind a small
   provider abstraction (`make_spot_source("coinbase"|"binance")`). This
   **resolves the engine README "Open decision: BTC spot source"**: the concrete
   live BTC spot feed is implemented here as a **read-only public REST feed**
   (no key, no funds), and the **operator chooses the provider**. The engine's
   pure core is unchanged — both providers sit behind the same `BtcSpotSource`
   interface.

3. **`capture_runner.py`** — a loop that every `poll_sec` (default 5) pulls a
   snapshot (Polymarket + BTC spot folded together) and appends the normalized
   record to `runtime/captured_snapshots.jsonl` via
   `engine.capture.CaptureRecorder`. Run over ≥ 60 days it produces the backtest
   dataset.

4. **`parsers.py`** — the **pure, deterministic** parsers. No network, no clock.
   They are unit-tested offline against saved JSON fixtures, separated from the
   I/O fetch layer in `live.py`.

## Public, no-key endpoints used

All read-only; **no API key, no auth** (per `dashboard/docs/SECURITY_AUDIT.md`,
which confirms these are the official Polymarket hosts):

| Purpose | Endpoint |
|---------|----------|
| Gamma markets (slugs, gamma prices, spread, close time) | `https://gamma-api.polymarket.com/events` |
| CLOB order book (best ask/bid, top notional) | `https://clob.polymarket.com/book?token_id=<id>` |
| BTC spot (default provider) | `https://api.coinbase.com/v2/prices/BTC-USD/spot` |
| BTC spot (alternate provider) | `https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT` |

## How `btc_price_open` is defined / captured

`btc_price_open` is the BTC spot **open of the current 5-minute market interval**.
The interval is bucketed by `epoch // 300` (`parsers.interval_open_key`). The
**first spot price observed at or after each interval boundary** is recorded by
`live.IntervalOpenTracker` and **held constant for every snapshot in that
interval**; it only resets when the interval bucket advances. `btc_price_now` is
the latest spot price on each poll. Together they give the per-interval BTC move
the momentum indicators need.

## How to run a capture session

Run from the `quant-app/` directory (so `engine` and `feeds` import):

```bash
cd quant-app

# one snapshot, parse + assemble only, write nothing (smoke check)
python -m feeds.capture_runner --once --dry

# capture for one hour at the default 5s cadence into ./runtime/
python -m feeds.capture_runner --duration 3600 --poll-sec 5 --runtime runtime

# single recorded snapshot
python -m feeds.capture_runner --once

# choose the Binance spot provider instead of Coinbase
python -m feeds.capture_runner --once --spot binance
```

Flags: `--once`, `--duration <sec>`, `--max-polls <n>`, `--poll-sec <sec>`,
`--runtime <dir>`, `--dry` (parse only, no write), `--spot {coinbase,binance}`,
`--timeout <sec>`.

The capture file is `runtime/captured_snapshots.jsonl` (one normalized
`MarketSnapshot` JSON object per line), the exact format `engine.backtest` /
`RecordedSource` replay.

## Tests

```bash
cd quant-app && python -m pytest feeds -q
```

- `test_parsers.py` — pure parsers against saved fixtures
  (`tests/fixtures/*.json`); fully offline and deterministic.
- `test_live.py` — `PolymarketSnapshotSource` + spot sources with an **injected**
  `http_get` (no real network), incl. last-good caching and the
  `btc_price_open` interval behaviour.
- `test_capture_runner.py` — end-to-end against a fake injected source writing to
  a temp runtime dir; asserts JSONL field coverage and that `btc_price_open` is
  held within an interval and resets across one.
- `test_live_smoke.py` — best-effort **one real fetch** per endpoint; if the
  sandbox blocks outbound it is **skipped, never failed**
  (set `FEEDS_DISABLE_LIVE_SMOKE=1` to disable the attempt entirely).
```
