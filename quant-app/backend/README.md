# backend — HTTP/WS API server

Zero-dependency (Python standard library only) backend that bridges the
deterministic **engine** to the **mobile app** and **dashboard**. It implements
the contract in [`docs/08_API_SPEC.md`](../docs/08_API_SPEC.md) with the payload
shapes from [`docs/05_DATA_CONTRACTS.md`](../docs/05_DATA_CONTRACTS.md), so the
mobile client (`mobile/src/api/`) can flip from mock to live with **no type
changes**.

Built on the same `http.server` / `ThreadingHTTPServer` pattern as
`dashboard/app.py`, and reuses `dashboard/parser.py`'s runtime-reading approach
plus the engine's `datasource.RecordedSource` / `MockSource`.

## Run

From `quant-app/`:

```bash
python -m backend.server
# btc5m backend API  ->  http://127.0.0.1:8788/api/v1
```

With no `BTC5M_RUNTIME` set (or an empty runtime dir), the server serves a
deterministic `MockSource` so the app renders end-to-end. Point it at real
runtime artifacts to serve live data:

```bash
BTC5M_RUNTIME=/path/to/runtime BTC5M_API_TOKEN=secret python -m backend.server
```

### Environment

| Var | Purpose | Default |
|-----|---------|---------|
| `BTC5M_API_TOKEN` | Bearer token for `read` scope (and `control` if no control token) | unset → read GETs open on **localhost only**; control disabled |
| `BTC5M_API_CONTROL_TOKEN` | Separate token for `control` scope (POST) | falls back to `BTC5M_API_TOKEN` |
| `BTC5M_RUNTIME` | Runtime dir (snapshots, trades, equity) | unset → `MockSource` |
| `BTC5M_PROFILE` | Active profile (`conservative`/`aggressive`) | `conservative` |
| `BTC5M_EQUITY_USD` | Bankroll for equity/risk caps | unset |
| `BTC5M_FUNDER_ADDRESS` | Funder address (returned **masked** only) | unset |
| `BTC5M_SIGNATURE_TYPE` | `PM_SIGNATURE_TYPE` echo (2 = proxy) | unset |
| `HOST` / `PORT` | Bind address | `127.0.0.1` / `8788` |

**Security / non-custodial:** the backend never reads or logs `PM_PRIVATE_KEY`,
API secrets, or any seed material. Funder addresses are masked
(`crypto.safety.mask_address`). No secrets are logged.

## Endpoints (base `/api/v1`)

All responses use the envelope `{ "schema_version", "ts", "data" }` (08 §1).
Errors are `{ "error": { "code", "message", "detail" } }`.

### Read (scope `read` — token required unless localhost with no token configured)

| Method | Path | `data` |
|--------|------|--------|
| GET | `/status` | `BotStatus` (05 §9) |
| GET | `/snapshot` | `MarketSnapshot` (05 §1) |
| GET | `/signal` | `Signal` (05 §3) — full score/gate breakdown |
| GET | `/decision` | `Decision` (05 §4) |
| GET | `/positions` | `Position[]` (05 §5) |
| GET | `/trades?limit&before` | `TradeResult[]` (05 §6) |
| GET | `/trades/{order_id}` | `TradeResult` (matched by `open_tx`/`close_tx`) |
| GET | `/risk` | `RiskState` (05 §7) |
| GET | `/equity?range=session\|7d\|30d\|all` | `Account` + `equity_curve` (05 §8) |
| GET | `/config` | `{ profile, params, ranges }` (mobile `ConfigResponse`) |
| GET | `/health` | `{ ok, state, age_sec, dead_man_tripped }` |
| WS | `/stream?token=<read-token>` | live frames (see below) |

### Control (scope `control` — token **always** required; audited; dry-run-aware)

| Method | Path | Body | Notes |
|--------|------|------|-------|
| POST | `/control/start` | `{ profile, mode }` | `mode` defaults `dry_run`; `live` requires armed → else `403 not_armed` |
| POST | `/control/stop` | `{}` | graceful stop |
| POST | `/control/kill` | `{ "confirm": "KILL" }` | **always processable**, returns `202` |
| POST | `/control/arm` | `{ "confirm": "ARM LIVE", "runbook_ack": true }` | both required → else `400 validation` |
| POST | `/control/disarm` | `{}` | back to paper-safe |
| POST | `/control/profile` | `{ "profile": "aggressive" }` | validated |
| POST | `/control/config` | `{ "params": { ... } }` | range-validated (03 §7); caps can't disable themselves |

**Dry-run by default / read-only:** control actions only flip in-process flags
and append to an auditable `runtime/commands.jsonl`. They **never place real
orders.** Any execution routes through `crypto.factory.get_adapter`, which returns
the offline `PaperExecutionAdapter` unless explicitly `mode="live"` **and**
`armed=True` (and the live adapter's own env-cred gate passes). The kill switch and
dead-man state come from `crypto/safety.py` and `engine/risk.py`.

## WebSocket (08 §5)

`GET /api/v1/stream` with `Upgrade: websocket` and a read token (query `?token=`
or `Authorization` header). The server pushes JSON frames on state change plus a
heartbeat every ≤10s:

```json
{ "type": "signal|snapshot|decision|risk|status|heartbeat", "ts": "...", "data": { } }
```

This matches `mobile/src/api/ws.ts`. If the socket is heavy/unavailable, the
mobile hook falls back to **REST polling** (~5s) against the same read endpoints —
no extra server work needed.

## Tests

```bash
cd quant-app && python -m pytest backend -q
```

Covers: every endpoint returns the right `05` shape; auth enforced on control
endpoints; dry-run/arming never bypassed; `/control/config` range validation; the
non-custodial invariant (no private key in any payload; funder address masked).

## Files

- `server.py` — `ThreadingHTTPServer` routing + WebSocket/polling.
- `api.py` — handlers, auth (bearer/scopes), envelope + error mapping.
- `engine_bridge.py` — adapts engine + runtime artifacts to `05`/`08` JSON; holds
  in-process control state (kill switch / arming) and writes the command file.
- `tests/` — pytest suite.
