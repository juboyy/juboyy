# 02 — System Specification

> Architecture for the deterministic trading system + mobile cockpit. Implements
> `01_PRODUCT_SPEC.md`. Field names/contracts are normative in `05_DATA_CONTRACTS.md`;
> API surface in `08_API_SPEC.md`.

## 1. Design principles
- **Deterministic core, thin shells.** All decisions live in pure functions
  (`engine/`). API and mobile are I/O shells around them.
- **No LLM at runtime.** The trading loop imports no model-inference of any kind
  in MVP/v1. (v2 optional offline model is frozen + deterministic — see `04`.)
- **Non-custodial boundary.** The private key exists only inside the **Execution
  Adapter** process. It is never read by the API or the mobile app.
- **Dry-run by default.** Execution requires an explicit `--execute` / `armed`
  flag *and* a runbook acknowledgement; absent that, the adapter simulates fills.
- **Reuse the existing dashboard.** The backend's read path is the dashboard's
  `parser.RuntimeReader` over the bot's runtime artifacts.

## 2. Components

| Component | Dir | Language | Responsibility | Holds key? |
|-----------|-----|----------|----------------|:---:|
| **Indicator Library** | `engine/indicators/` | Python | Pure feature functions (momentum, vol, skew, microstructure, staleness) → `Features`. See `04`. | no |
| **Signal Engine** | `engine/signal/` | Python | Deterministic scoring/threshold rule `Features → Signal → Decision`. See `03`/`04`. | no |
| **Risk Manager** | `engine/risk/` | Python | Applies caps (daily loss, trades/day, stop-loss, notional), profile gating, kill/arm state → may veto/clamp a Decision. | no |
| **Execution Adapter** | `crypto/` | Python | Wraps `py_clob_client` (ClobClient, POLYGON). Dry-run simulator by default; live signing gated. Emits trade results. | **yes** |
| **Runtime Artifacts** | `runtime/` | files | `btc5m.meta.json`, `btc5m_signal.json`, `btc5m_events.jsonl`, `btc5m_*.log`, `btc5m.pid` — written by the bot, read by the dashboard/API. | no |
| **Backend API** | `engine/api/` (or `backend/`) | Python (stdlib http first; FastAPI optional v1) | Reads artifacts via `dashboard/parser.py`; exposes REST + WS; owns control endpoints (arm/start/stop/kill). Token auth. See `08`. | no |
| **Read-only Dashboard** | `dashboard/` | Python stdlib `http.server` | Existing watchtower; kept as-is, aligned. | no |
| **Mobile App** | `mobile/` | Expo / React Native (TypeScript) | The cockpit. Consumes the API; never touches keys. | no |
| **Backtest Harness** | `engine/backtest/` | Python | Replays historical snapshots through the same pure functions; emits metrics. See `03`. | no |

### Component contracts (pure-function spine)
```
Snapshot ─▶ indicators.compute(Snapshot) ─▶ Features
Features ─▶ signal.evaluate(Features, Profile) ─▶ Signal
Signal   ─▶ signal.decide(Signal, Profile) ─▶ Decision
Decision ─▶ risk.apply(Decision, RiskState, Profile) ─▶ Decision'   (may veto/clamp)
Decision'─▶ execution.act(Decision', mode) ─▶ TradeResult            (dry-run | live)
```
Every arrow is a **pure function** of its inputs (except `execution.act`, the
only side-effecting boundary). The same spine runs live **and** in backtest — the
only difference is the source of `Snapshot` and the `execution` implementation.

## 3. Data flow

### Live loop (per poll, default `poll_sec = 5`)
1. **Adapter** polls Polymarket CLOB + Gamma → builds a `MarketSnapshot`
   (`clob_up_ask`, `clob_down_ask`, `gamma_up`, `gamma_down`, `seconds_left`,
   `min_spread`, `slug`, plus a BTC spot price for momentum).
2. Snapshot → **Indicators** → `Features`.
3. Features → **Signal Engine** → `Signal` (per-indicator subscores + total) →
   `Decision` (`enter`/`hold`/`exit`/`hedge`/`skip` + side + reason).
4. Decision → **Risk Manager** → `Decision'` (vetoed if cap hit / not armed /
   stale / outside entry window).
5. `Decision'` → **Execution Adapter**: if `mode=dry_run` → simulate; if
   `mode=live` and `armed` → place CLOB order via `py_clob_client`.
6. Adapter appends a heartbeat to the session report's `attempts[]` and, on
   open/close, a record to `btc5m_events.jsonl`; updates `btc5m_signal.json`.
7. **Backend API** reads those artifacts (via `RuntimeReader`) and serves the
   mobile app (REST snapshots + WS push). Mobile renders Live/Positions/etc.

### Control flow (operator → system)
```
Mobile (Settings/Kill) ──token──▶ Backend API control endpoint
   ▶ /control/kill   → write kill flag → adapter halts new entries, attempts safe close
   ▶ /control/arm    → set armed=true (requires typed confirm + biometric on device)
   ▶ /control/profile→ swap active profile (validated ranges)
```
Control endpoints never receive keys; they flip flags the adapter reads.

## 4. ASCII architecture diagram

```
                          OPERATOR'S PHONE
        ┌──────────────────────────────────────────────────┐
        │  Mobile App (Expo / React Native, TypeScript)     │
        │  Live · Positions · History · Risk · Equity ·     │
        │  Settings/Profiles · Kill switch                  │
        │  (secure storage; biometric gate; NO private key) │
        └───────────────▲───────────────┬──────────────────┘
              WS push    │   REST + token│  control (arm/stop/kill)
                         │               ▼
        ┌────────────────┴──────────────────────────────────┐
        │            BACKEND API  (engine/api)                │
        │  read: GET snapshot/signal/decision/positions/...   │
        │  control: POST arm/disarm/start/stop/kill/profile   │
        │  auth: bearer token · enforces dry-run-by-default   │
        └──────▲──────────────────────────────┬──────────────┘
   reads via   │ dashboard/parser.py            │ writes flags
   RuntimeReader│  (RODANDO/PARADO, KPIs)       │ (armed/kill/profile)
        ┌───────┴───────────────┐   ┌───────────▼──────────────┐
        │   runtime/ artifacts   │◀──│  TRADING PROCESS (host)   │   ⟵ NON-CUSTODIAL
        │  meta.json · signal.json│  │ ┌───────────────────────┐ │     BOUNDARY
        │  events.jsonl · *.log   │  │ │ Pure deterministic    │ │
        │  btc5m.pid              │  │ │ spine (no LLM):        │ │
        └────────────────────────┘  │ │ Indicators→Signal→     │ │
                  ▲                  │ │ Risk→Decision          │ │
                  │ (also read by)   │ └──────────┬────────────┘ │
        ┌─────────┴───────────┐      │            ▼              │
        │ Read-only Dashboard │      │  Execution Adapter        │
        │ (http.server)       │      │  py_clob_client (POLYGON) │
        └─────────────────────┘      │  dry-run default | live*  │
                                     │  *gated: armed + runbook  │
                                     │  holds PM_PRIVATE_KEY      │
                                     └────────────┬──────────────┘
                                                  │ HTTPS (official hosts only)
                              ┌───────────────────▼───────────────────┐
                              │ Polymarket CLOB  · Gamma API · (BTC px)│
                              └────────────────────────────────────────┘
```

## 5. Deployment topology
- **Trading process + Execution Adapter:** single VPS / home server, inside an
  isolated container (per `SAFE_OPERATION.md` §2). Holds `PM_PRIVATE_KEY` in env
  only. Pinned deps (`requirements.pinned.txt` → lock).
- **Backend API:** same host (loopback to runtime dir) or a co-located sidecar.
  Exposed to the phone over **HTTPS + bearer token** (reverse proxy / Tailscale /
  Cloudflare Tunnel). No key access.
- **Mobile app:** operator's device; stores only the API base URL + bearer token
  in secure storage (Keychain/Keystore), gated by biometrics.
- **Dashboard:** optional, same host, read-only.

### Modes
- `mode=dry_run` (default): adapter simulates fills; identical decision spine.
- `mode=live` (gated): requires `armed=true` + runbook ack; live CLOB orders.

## 6. Failure modes & responses
| Failure | Detection | Response |
|---------|-----------|----------|
| Trading process dies with open position | `btc5m.pid` not alive / `signal.age_sec` stale | API marks `PARADO`; **dead-man's switch** alert; mobile banner |
| Stale/zero quotes | `age_sec > skip_if_quote_stale_sec_gt` (8) | Risk vetoes entry; mobile shows "stale" state |
| Cap reached | Risk Manager counters | Veto new entries; mobile gauge → 100%, armed→blocked |
| API unreachable | Mobile request timeout | Mobile error state + last-known cache; kill still attempted on reconnect |
| Wrong/unknown market | slug mismatch vs expected | Adapter refuses; logged; alert |

## 7. Tech choices (locked)
- Engine/backtest/adapter: **Python 3.11+**, pure-stdlib core where possible;
  `py_clob_client` for live only.
- Backend: **start on Python stdlib `http.server`** (reuse dashboard patterns);
  may graduate to **FastAPI** in v1 for WS + OpenAPI.
- Mobile: **Expo / React Native + TypeScript**; data layer **TanStack Query**;
  WS for live push; secure storage via `expo-secure-store`; biometrics via
  `expo-local-authentication`.
