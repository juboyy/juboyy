# 08 — API Specification (REST + WebSocket)

> The contract between the **Backend API** (`engine/api`, over `dashboard/parser.py`)
> and the **Mobile App**. All payloads are the objects defined in
> `05_DATA_CONTRACTS.md` (field names verbatim). Read endpoints are safe;
> **control endpoints require the control scope and respect dry-run-by-default**
> (`02`, `06`).

## 1. Conventions
- Base URL: `https://<host>/api/v1`. JSON only; UTF-8; ISO-8601 UTC times.
- All responses wrap data:
  `{ "schema_version": "1.0", "ts": "...", "data": <object|array> }`.
- Errors: HTTP status + `{ "error": { "code": "...", "message": "...", "detail": {} } }`.
  Codes: `unauthorized`, `forbidden`, `not_armed`, `cap_reached`, `killed`,
  `validation`, `unavailable`, `rate_limited`.
- Pagination (lists): `?limit` (default 200, max 1000) `&before=<ISO ts>`.

## 2. Auth model
- **Bearer token** in `Authorization: Bearer <token>` over TLS.
- Two **scopes**:
  - `read` — all `GET` read endpoints.
  - `control` — `POST` control endpoints (arm/disarm/start/stop/kill/profile/config).
- Tokens are issued server-side, stored in mobile **secure storage**, rotatable
  and **revocable per device** (`06` §3/§8). Control actions additionally require
  client-side **biometric + typed confirm** (enforced in app; server logs intent).
- Every control call is written to an **append-only audit log** (who/when/device).

## 3. Read endpoints (scope: `read`)

| Method | Path | Returns (`data`) | Source |
|--------|------|------------------|--------|
| GET | `/status` | `BotStatus` (`05` §9) | `parser.status()` + mode/armed/killed |
| GET | `/snapshot` | `MarketSnapshot` (`05` §1) | adapter/heartbeat |
| GET | `/signal` | `Signal` (`05` §3) | `signal.evaluate` (live) |
| GET | `/decision` | `Decision` (`05` §4) | `signal.decide`+`risk.apply` (latest) |
| GET | `/positions` | `Position[]` (`05` §5) | open positions |
| GET | `/trades?limit&before` | `TradeResult[]` (`05` §6) | `parser.trades()` |
| GET | `/trades/{order_id}` | `TradeResult` | single trade |
| GET | `/risk` | `RiskState` (`05` §7) | `parser.summary()` + risk flags |
| GET | `/equity?range` | `Account`+`equity_curve` (`05` §8) | `parser.equity_curve()` |
| GET | `/config` | active `profile`, params (`03` §7), ranges | `config_defaults.json` |
| GET | `/health` | `{ ok, state, age_sec, dead_man_tripped }` | liveness/dead-man |

`range ∈ {session,7d,30d,all}` (default `session`).

### Example — `GET /signal`
```http
GET /api/v1/signal   Authorization: Bearer <read-token>
```
```json
{ "schema_version":"1.0", "ts":"2026-06-20T14:03:55Z",
  "data": { /* Signal object — 05 §3, incl. subscores, weights, gates */ } }
```

## 4. Control endpoints (scope: `control`)
All are `POST`, idempotent where noted, audited, and **enforce dry-run-by-default**.

| Method | Path | Body | Effect |
|--------|------|------|--------|
| POST | `/control/start` | `{ "profile": "conservative", "mode": "dry_run" }` | Start a session (mode defaults `dry_run`; `live` requires armed) |
| POST | `/control/stop` | `{}` | Stop the session gracefully |
| POST | `/control/kill` | `{ "confirm": "KILL" }` | **Kill:** block new entries + attempt safe close of open positions |
| POST | `/control/arm` | `{ "confirm": "ARM LIVE", "runbook_ack": true }` | Set `armed=true` for live (requires runbook ack) |
| POST | `/control/disarm` | `{}` | Set `armed=false` (back to paper-safe) |
| POST | `/control/profile` | `{ "profile": "aggressive" }` | Switch active profile (validated) |
| POST | `/control/config` | `{ "params": { "threshold_price": 0.72, ... } }` | Update params within `03` §7 ranges (server-validated) |

### Dry-run / arming rules (server-enforced)
- `mode` defaults to `"dry_run"`. A request for `mode:"live"` with `armed=false`
  → `403 not_armed`.
- `/control/arm` requires `confirm=="ARM LIVE"` **and** `runbook_ack==true`,
  else `400 validation`. Arming only flips a flag the adapter reads; it never
  receives keys.
- `/control/config` rejects out-of-range params with `400 validation`
  (`detail` lists offending fields). Caps cannot be set to disable themselves.
- `/control/kill` is **always processable** (rate-limit-exempt), even when other
  control calls are blocked; returns `202` with `{ "killed": true, "closed": n,
  "close_skipped": m }`.

### Example — `POST /control/kill`
```http
POST /api/v1/control/kill   Authorization: Bearer <control-token>
{ "confirm": "KILL" }
```
```json
{ "schema_version":"1.0", "ts":"2026-06-20T14:06:00Z",
  "data": { "killed": true, "blocking_new_entries": true,
            "positions_closed": 1, "positions_close_skipped": 0 } }
```

### Example — `POST /control/config` (rejected)
```json
{ "error": { "code":"validation",
  "message":"param out of range",
  "detail": { "threshold_price": "must be in [0.55,0.85]" } } }
```

## 5. WebSocket (live push)
- `wss://<host>/api/v1/stream?token=<read-token>` (or `Authorization` header on
  upgrade). Read-scope; **control is REST only** (no control over WS).
- Server pushes frames as state changes (and a heartbeat every ≤10s):
```json
{ "type": "signal",   "ts":"...", "data": { /* Signal */ } }
{ "type": "snapshot", "ts":"...", "data": { /* MarketSnapshot */ } }
{ "type": "decision", "ts":"...", "data": { /* Decision */ } }
{ "type": "risk",     "ts":"...", "data": { /* RiskState */ } }
{ "type": "status",   "ts":"...", "data": { /* BotStatus */ } }
{ "type": "trade",    "ts":"...", "data": { /* TradeResult (on settle) */ } }
{ "type": "alert",    "ts":"...", "data": { "kind":"dead_man|cap_reached|stop_loss|killed", "message":"..." } }
{ "type": "heartbeat","ts":"...", "data": { "age_sec": 2 } }
```
- The app subscribes for **Live/Positions/Risk**; falls back to REST polling
  (every `poll_sec`≈5s) if the socket drops. Reconnect with backoff; on reconnect
  it re-fetches `/status` + `/risk` to resync.

## 6. Alerts / push (drives `07` banners)
- The same `alert` payloads above are delivered via WS **and** (v1) mobile push:
  `dead_man` (process dead / `age_sec>30`), `cap_reached`, `stop_loss`, `killed`.
- Alerts never include secrets; addresses masked (`06`).

## 7. Read-vs-control summary
| Read (safe, `read` scope) | Control (`control` scope, audited, dry-run-aware) |
|---|---|
| status, snapshot, signal, decision, positions, trades, risk, equity, config, health, WS stream | start, stop, **kill**, arm, disarm, profile, config |

## 8. Versioning
- Path-versioned (`/api/v1`). Additive fields are non-breaking; payloads always
  carry `schema_version` from `05`. Breaking changes → `/api/v2`.
