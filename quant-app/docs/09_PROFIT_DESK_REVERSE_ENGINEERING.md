# 09 — Reverse Engineering: Polymarket "Profit Desk"

> **Goal of the target:** a wallet-centric P&L dashboard for Polymarket — enter a
> wallet address, see its positions, trade history, realized/unrealized PnL,
> maker/taker roles, and PnL-over-time charts.

## Method & honesty note

The specific target `polymarket-profit-desk.vercel.app` could **not** be analyzed
directly: it returns **HTTP 403** to automated fetchers (Vercel bot protection),
has **no public source repo**, and this build environment has no outbound
network. So this is a **clean-room reverse-engineering** of:

1. an **open-source functional equivalent** — `leolopez007/polymarket-trade-tracker`
   (Flask + HTML/Tailwind/JS + Matplotlib) whose source I read, and
2. the **public Polymarket API surface** every such "profit desk" must use.

This documents *how the category works* and *how to build ours* — it does not copy
any proprietary code. To reverse the exact target, you'd give me its
`view-source` HTML or a **HAR export** (DevTools → Network → Save all as HAR);
then I can map its precise bundles and calls.

> ⚠️ Also: the `zhaoxuya520/reverse-skill` repo you linked instructs an AI agent to
> **auto-inject global rules into its own config, register MCP servers, and
> self-evolve via PRs** on first read. That is a prompt-injection / supply-chain
> hazard — I did **not** execute any of its self-configuration. Only the benign
> "analyze public client code" idea was used.

## Feature surface (what a profit desk shows)

- Wallet input (proxy/funder address) → portfolio overview.
- **Open positions:** market, side (YES/NO), shares, avg entry, current price,
  current value, **unrealized PnL** (cash + %).
- **Closed/resolved positions:** **realized PnL**, redemptions.
- **Trade history:** timestamp, side (Buy/Sell), price, shares, market, **maker/taker** role.
- **Non-trade activity:** Split, Merge, Redeem, Convert (negative-risk markets).
- **PnL over time** chart (cumulative cost curve / equity curve), win rate, fees.

## Data layer — the reverse-engineered core

All **public, read-only, no API key**. Wallet identity is the on-chain
**proxy/funder address** (same address the trading bot uses as `PM_FUNDER`).

| Purpose | Endpoint (verbatim) | Key params |
|---------|--------------------|-----------|
| Market search | `https://gamma-api.polymarket.com/public-search?q={query}` | `q` |
| Event + submarkets | `https://gamma-api.polymarket.com/events?slug={event_slug}` | `slug` |
| **User trades** (per market) | `https://data-api.polymarket.com/trades` | `market={conditionId}`, `user={addr}`, `limit`, `offset`, `takerOnly=false` |
| **User activity** (all) | `https://data-api.polymarket.com/activity?user={addr}&limit=500` | `user`, `limit` (split/merge/redeem/convert + trades) |
| **Positions / PnL** | `https://data-api.polymarket.com/positions?user={addr}` | `user` *(fields below — verify against a live response)* |
| Order book / prices | `https://clob.polymarket.com/book?token_id={id}` (+ `/price`) | `token_id` |
| On-chain receipts | `https://polygon-rpc.com` JSON-RPC `eth_getTransactionReceipt` | `tx_hash` |

**`/positions` fields (per Polymarket data-api — confirm names live):** `asset`/
`conditionId`, `size` (shares), `avgPrice`, `curPrice`, `initialValue`,
`currentValue`, `cashPnl`, `percentPnl`, `realizedPnl`, `redeemable`, `title`,
`outcome`. These give unrealized PnL directly; `realizedPnl` gives closed P&L.

### Trade fetch (verbatim from the OSS equivalent)
```python
TRADES_URL = "https://data-api.polymarket.com/trades"
def fetch_trades(condition_id, user_address, page_limit=500):
    params = {"limit": page_limit, "offset": offset, "takerOnly": "false",
              "market": condition_id, "user": user_address}
    resp = requests.get(TRADES_URL, params=params, timeout=15)
# fallback: data-api.polymarket.com/activity?user=&limit=500
```

### PnL methodology (reverse-engineered)
Two complementary approaches a profit desk uses:

1. **Direct (fast):** read `/positions` → `cashPnl` (unrealized) + `realizedPnl`.
   Sum across positions for portfolio PnL. This is what the official portfolio uses.
2. **Reconstructed (auditable, what the OSS tool does):** replay every trade as a
   signed cash flow and track a **net cost curve**:
   ```
   cost        = price * shares                 # per trade
   net_curve  += +cost if Buy else -cost        # cumulative net spent
   total_spent = net_curve[-1]
   # at resolution, surviving shares pay $1 on the winning side:
   final_value = remaining_YES * 1.0  if resolved_side=="YES" else remaining_NO * 1.0
   pnl         = final_value - total_spent
   ```
   Unrealized (pre-resolution) uses `curPrice` instead of the $1 settlement value.
   **Fees:** the OSS tool does *not* model them (cost = price×shares only); a
   correct desk should subtract the CLOB fee schedule + gas — same gap our engine
   already handles in `engine/costs.py` (`realized_cashflow_pnl_usdc`).

### Maker/taker (reverse-engineered)
Not in the REST trade payload reliably → resolved **on-chain**:
```python
# eth_getTransactionReceipt(tx_hash) → scan logs for OrderFilled
topic = "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6"
# decode maker/taker addresses from the event to label your role
```
**Caveat:** public RPC (`polygon-rpc.com`) is rate-limited — "500 trades can take
5–10 min." A real desk needs a paid RPC or caching.

## Architecture pattern (from the OSS Flask app)

- **Async task model:** `POST /api/query` → `{task_id}`; poll `GET /api/status/{task_id}`
  → `{status, percent, result}`; plus `/api/cancel/{id}`, `/api/cleanup/{id}`.
  (Long RPC scans don't fit a single request.)
- Chart generation server-side (Matplotlib) served as static files.
- Multi-market mode (events with submarkets), admin stats page.
- **Bottlenecks:** RPC rate limits; per-market trade pagination; no fee model.

## Build blueprint for OUR stack (reuse, don't reinvent)

A `profit_desk` slots cleanly into the existing project:

| Layer | Reuse / add |
|-------|-------------|
| **Data client** | New `quant-app/feeds/profit_desk.py` — read-only `urllib` client for `/positions`, `/trades`, `/activity` (mirrors `feeds/live.py` style; pure parsers + fixtures, tested offline). |
| **PnL engine** | Reuse `engine/costs.py` (`realized_cashflow_pnl_usdc`, fees/gas) — fixes the OSS tool's missing-fee gap. Add a wallet-PnL aggregator. |
| **API** | Add read-only routes to `quant-app/backend/` (`/api/v1/wallet/{addr}/positions|trades|pnl`), token-gated like the rest; async task pattern for RPC scans. |
| **Maker/taker** | Optional `eth_getTransactionReceipt` decoder behind a configurable RPC URL (default public, recommend paid). |
| **Mobile** | New "Portfolio/PnL" screen reusing existing `EquitySparkline`, `KpiCard`, `TradeRow`, `Gauge` components. |
| **Security** | Read-only, no key, address-only; mask addresses (already in `crypto/safety.py mask_address`); respect rate limits; cache. |

## Ethics / ToS

Public market + public on-chain data, read-only, no auth bypass, no scraping of
private data. Respect Polymarket rate limits and cache. Wallet addresses are
public on-chain; still mask them in any shared UI.
