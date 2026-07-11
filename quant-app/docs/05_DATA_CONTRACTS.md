# 05 — Data Contracts

> Canonical JSON contracts shared by the engine, backend API, and mobile app.
> **These field names are normative**: `08_API_SPEC.md` returns them verbatim and
> `07_UX_UI.md` binds to them. Where a field already exists in the dashboard
> (`dashboard/parser.py`, `config_defaults.json`), we **reuse the exact name**
> (e.g. `clob_up_ask`, `seconds_left`, `realized_cashflow_pnl_usdc`).

## 0. Conventions
- Encoding: UTF-8 JSON. Times are **ISO-8601 UTC** strings (e.g.
  `"2026-06-20T14:03:55Z"`); ages/durations are integer **seconds**.
- Money: USDC as JSON numbers (USDC, 6dp tolerated). Prices/probabilities are
  numbers in **[0,1]**. `null` = unknown/unavailable (never `0` to mean missing).
- Enums are lowercase strings. `side ∈ {"up","down"}`. Profiles
  `∈ {"conservative","aggressive"}`. Mode `∈ {"dry_run","live"}`.
- Every top-level object carries `schema_version` (string, starts `"1.0"`).

---

## 1. `MarketSnapshot`
Raw, point-in-time market state (built by the Execution Adapter; persisted to
`btc5m_signal.json` / heartbeats). Inputs to the indicator library.
```json
{
  "schema_version": "1.0",
  "ts": "2026-06-20T14:03:55Z",
  "market_slug": "btc-updown-2026-06-20-1405",
  "seconds_left": 118,
  "clob_up_ask": 0.71,
  "clob_down_ask": 0.30,
  "clob_up_bid": 0.69,
  "clob_down_bid": 0.28,
  "gamma_up": 0.68,
  "gamma_down": 0.32,
  "min_spread": 0.02,
  "top_ask_notional_usd": 64.0,
  "top_bid_notional_usd": 51.0,
  "btc_price_open": 64850.0,
  "btc_price_now": 64928.0,
  "age_sec": 3,
  "source": "clob+gamma"
}
```
| Field | Type | Notes |
|-------|------|-------|
| `ts` | string(ISO) | snapshot time |
| `market_slug` | string | matches dashboard `slug`/`market_slug` |
| `seconds_left` | int | `T_close − now`; dashboard field |
| `clob_up_ask` / `clob_down_ask` | number[0,1]\|null | dashboard fields |
| `clob_up_bid` / `clob_down_bid` | number[0,1]\|null | top bids (exit pricing) |
| `gamma_up` / `gamma_down` | number[0,1]\|null | dashboard fields |
| `min_spread` | number\|null | dashboard field |
| `top_ask_notional_usd` / `top_bid_notional_usd` | number\|null | depth for liquidity/imbalance |
| `btc_price_open` / `btc_price_now` | number\|null | BTC spot for momentum |
| `age_sec` | int\|null | dashboard-style staleness |
| `source` | string | provenance tag |

---

## 2. `Features`
Output of `engine/indicators` (`04`). Pure function of a `MarketSnapshot` + history.
```json
{
  "schema_version": "1.0",
  "ts": "2026-06-20T14:03:55Z",
  "btc_move_usd": 78.0,
  "momentum_side": "up",
  "momentum_score": 0.27,
  "rv_usd": 41.2,
  "rv_score": 0.27,
  "skew_clob": 0.703,
  "skew_gamma": 0.68,
  "skew_side": "up",
  "skew_agree": true,
  "skew_score": 0.45,
  "spread_ok": true,
  "notional_ok": true,
  "liquidity_score": 0.71,
  "imbalance": 0.13,
  "imbalance_score": 0.565,
  "in_window": true,
  "time_decay_score": 0.93,
  "seconds_left": 118,
  "fresh": true,
  "process_ok": true,
  "dead_man_tripped": false,
  "health_score": 1.0
}
```
All numeric subscores ∈ [0,1] (or signed where noted in `04`). Booleans drive
hard gates.

---

## 3. `Signal`
Output of `signal.evaluate` (`04` §8). Carries the full scoring breakdown so the
Live UI can explain *why*.
```json
{
  "schema_version": "1.0",
  "ts": "2026-06-20T14:03:55Z",
  "market_slug": "btc-updown-2026-06-20-1405",
  "chosen_side": "up",
  "chosen_side_ask": 0.71,
  "total_score": 0.64,
  "enter_score_min": 0.60,
  "subscores": {
    "momentum_score": 0.27,
    "skew_score": 0.45,
    "liquidity_score": 0.71,
    "imbalance_score": 0.565,
    "time_decay_score": 0.93,
    "rv_penalty": 0.054,
    "agreement_bonus": 0.05
  },
  "weights": {
    "w_mom": 0.35, "w_skew": 0.25, "w_liq": 0.15,
    "w_imb": 0.10, "w_time": 0.15, "w_vol": 0.20
  },
  "gates": {
    "health": true, "in_window": true, "momentum_present": true,
    "spread_ok": true, "notional_ok": true, "skew_agreement": true,
    "ask_ge_threshold": true, "ask_le_max": true, "risk_allows": true
  },
  "gates_passed": true,
  "failed_gate": null,
  "model_version": "rule-1.0",
  "age_sec": 3,
  "source": "session_report"
}
```
| Field | Type | Notes |
|-------|------|-------|
| `chosen_side` | "up"\|"down"\|null | momentum/skew side |
| `chosen_side_ask` | number[0,1] | price gate input |
| `total_score` | number[0,1] | composite (`04` §8) |
| `subscores` / `weights` | object | full reconstruction of the score |
| `gates` | object<bool> | each hard gate result |
| `failed_gate` | string\|null | first failed gate when `gates_passed=false` |
| `model_version` | string | `"rule-1.0"` (or offline model id, `04` §9) |

---

## 4. `Decision`
Output of `signal.decide` then `risk.apply`. What execution acts on.
```json
{
  "schema_version": "1.0",
  "ts": "2026-06-20T14:03:55Z",
  "market_slug": "btc-updown-2026-06-20-1405",
  "action": "enter",
  "side": "up",
  "limit_price": 0.71,
  "size_usd": 5.0,
  "shares": 7,
  "reason": "score_0.64_ge_min_0.60",
  "hedge": {
    "enabled": false, "side": null, "notional_usd": null
  },
  "risk_verdict": "allow",
  "risk_reason": null,
  "mode": "dry_run",
  "armed": false,
  "signal_ref_ts": "2026-06-20T14:03:55Z"
}
```
| Field | Type | Notes |
|-------|------|-------|
| `action` | enum | `"enter"\|"hold"\|"exit"\|"hedge"\|"skip"` |
| `side` | "up"\|"down"\|null | for enter/exit |
| `limit_price` | number[0,1]\|null | marketable limit = chosen ask |
| `size_usd` / `shares` | number/int | from `03` §4 sizing |
| `reason` | string | human/audit reason (e.g. `time_exit`, `stop_loss`, failed gate) |
| `hedge` | object | `03` §5 hedge leg if attached |
| `risk_verdict` | enum | `"allow"\|"veto"\|"clamp"` (Risk Manager) |
| `risk_reason` | string\|null | e.g. `daily_loss_cap`, `max_trades`, `not_armed`, `killed`, `stale` |
| `mode` | enum | `"dry_run"\|"live"` |
| `armed` | bool | live gate state |

---

## 5. `Order` / `Position`
An open or attempted order and the resulting position. Mirrors the bot's
`opened` block.
```json
{
  "schema_version": "1.0",
  "order_id": "ord_01H...",
  "ts": "2026-06-20T14:04:01Z",
  "market_slug": "btc-updown-2026-06-20-1405",
  "side": "up",
  "entry_price": 0.71,
  "shares": 7,
  "cost_usdc": 4.97,
  "open_tx": "0xabc...",
  "mode": "dry_run",
  "status": "open",
  "stop_loss_price": 0.5325,
  "seconds_left_at_entry": 116,
  "profile": "conservative"
}
```
| Field | Type | Notes |
|-------|------|-------|
| `entry_price` | number[0,1] | dashboard `entry_price` |
| `shares` | int | dashboard `shares` |
| `cost_usdc` | number | dashboard `cost_usdc` |
| `open_tx` | string\|null | dashboard `open_tx`; null in dry-run |
| `status` | enum | `"open"\|"closed"\|"settled"\|"failed"` |
| `stop_loss_price` | number | `entry_price × (1 − stop_loss_pct_from_entry)` |
| `seconds_left_at_entry` | int | dashboard field |

---

## 6. `TradeResult`
Closed/settled trade. **Canonical record** appended to `btc5m_events.jsonl` and
read by `dashboard/parser.py::_normalize_trade`. Field names match the dashboard.
```json
{
  "schema_version": "1.0",
  "ts": "2026-06-20T14:05:00Z",
  "profile": "conservative",
  "result": "win",
  "side": "up",
  "market_slug": "btc-updown-2026-06-20-1405",
  "entry_price": 0.71,
  "shares": 7,
  "cost_usdc": 4.97,
  "open_tx": "0xabc...",
  "close_reason": "settlement",
  "close_success": true,
  "close_status": "settled",
  "close_skipped": false,
  "close_tx": "0xdef...",
  "realized_cashflow_pnl_usdc": 2.03,
  "btc_move_usd": 78.0,
  "skew": 0.703,
  "seconds_left_at_entry": 116,
  "threshold_price": 0.70,
  "stake_usd": 5,
  "fees_usdc": 0.0,
  "slippage_usdc": 0.07,
  "gas_usdc": 0.04,
  "mode": "dry_run"
}
```
| Field | Type | Notes |
|-------|------|-------|
| `result` | enum | `"win"\|"loss"\|"breakeven"` |
| `close_reason` | string | `settlement\|stop_loss\|time_exit\|kill` (dashboard `close_reason`) |
| `close_success`/`close_status`/`close_skipped`/`close_tx` | mixed | dashboard fields |
| `realized_cashflow_pnl_usdc` | number | **net** P&L after costs (dashboard field, `03` §8) |
| `btc_move_usd`/`skew`/`threshold_price`/`stake_usd` | mixed | dashboard fields |
| `fees_usdc`/`slippage_usdc`/`gas_usdc` | number | cost breakdown (`03` §8) |

---

## 7. `RiskState`
Live risk/cap state (Risk Manager + `parser.summary`). Drives Risk/Limits UI.
```json
{
  "schema_version": "1.0",
  "ts": "2026-06-20T14:05:05Z",
  "profile": "conservative",
  "mode": "dry_run",
  "armed": false,
  "killed": false,
  "running": true,
  "pnl_today": -0.40,
  "pnl_total": 12.10,
  "trades_today": 4,
  "trades_total": 37,
  "wins": 24,
  "losses": 11,
  "win_rate": 68.6,
  "max_trades_per_day": 12,
  "trades_cap_used_pct": 33.3,
  "daily_loss_cap_usd": 9.60,
  "daily_loss_cap_pct": 10,
  "loss_cap_used_pct": 4.2,
  "best_trade": 2.9,
  "worst_trade": -3.5,
  "open_position": null,
  "dead_man_tripped": false
}
```
All cap/KPI fields use the **exact names produced by `parser.summary()`**
(`pnl_today`, `loss_cap_used_pct`, `trades_cap_used_pct`, `daily_loss_cap_usd`,
`win_rate`, `open_position`, …). `armed`/`killed`/`mode`/`dead_man_tripped` are
added by the Risk Manager.

---

## 8. `Account` / `Equity`
Operator account/equity state and the equity curve (`parser.equity_curve`).
```json
{
  "schema_version": "1.0",
  "ts": "2026-06-20T14:05:05Z",
  "equity_usd": 96.0,
  "funder_address_masked": "0x1234…ab12",
  "signature_type": 2,
  "currency": "USDC",
  "equity_curve": [
    {"ts": "2026-06-20T13:40:00Z", "cum_pnl": 10.07, "pnl": 2.10},
    {"ts": "2026-06-20T14:05:00Z", "cum_pnl": 12.10, "pnl": 2.03}
  ]
}
```
| Field | Type | Notes |
|-------|------|-------|
| `equity_usd` | number\|null | bankroll (config `equity_usd`) |
| `funder_address_masked` | string | **masked** funder; never the private key |
| `signature_type` | int | from `PM_SIGNATURE_TYPE` (2 = proxy) |
| `equity_curve[]` | array | `{ts, cum_pnl, pnl}` exactly as `parser.equity_curve()` |

> **Security:** no contract ever contains `PM_PRIVATE_KEY`, API secrets, or any
> seed material. Addresses are masked. See `06_SECURITY.md`.

---

## 9. `BotStatus`
Process/session status (`parser.status`). Drives the global RODANDO/PARADO banner.
```json
{
  "schema_version": "1.0",
  "running": true,
  "state": "RODANDO",
  "pid": 4821,
  "profile": "conservative",
  "mode": "dry_run",
  "armed": false,
  "killed": false,
  "started_at": "2026-06-20T13:30:00Z",
  "uptime_sec": 2105,
  "params": {
    "threshold": 0.70, "stake_usd": 5, "stop_loss_pct": 0.25,
    "exit_before_sec": 20, "min_entry_seconds_left": 60, "poll_sec": 5,
    "execute": false
  },
  "log_path": "/workspace/runtime/btc5m_conservative_20260620T133000.log"
}
```
`state ∈ {"RODANDO","PARADO","STALE"}` (derived: running+fresh, dead, alive-but-stale).
`params` mirrors `parser.status().params`; `execute=false` ⇒ dry-run.

---

## 10. Versioning & compatibility
- `schema_version` bumps on breaking change; additive fields are non-breaking.
- The backend reads legacy bot artifacts via `dashboard/parser.py`; any new field
  must remain optional so old logs still parse (parser degrades gracefully).
