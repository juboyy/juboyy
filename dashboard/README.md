# BTC 5m · Polymarket — Operations Dashboard

A lightweight, **zero-dependency** monitoring dashboard for the
[`5min-btc-polymarket`](https://github.com/Novals83/5min-btc-polymarket)
momentum-trading bot (BTC 5-minute up/down markets on Polymarket).

It reads the bot's `runtime/` artifacts (status, logs, trade results) and
renders, with auto-refresh every 3s:

- **Bot status** — running/stopped, PID, profile, uptime, live params
- **Live signal** — UP/DOWN CLOB ask, seconds-to-close, skew, spread, gamma,
  and an "entry window active" indicator
- **KPIs** — P&L today / total, win rate, trades today, best/worst
- **Risk & limits** — daily loss-cap usage and trades/day usage gauges,
  current open position
- **Equity curve** — cumulative realized P&L (inline SVG, no libraries)
- **Trade history** — side, move, skew, entry, cost, P&L, status, market
- **Session log** — tail of the latest log file

> Read-only. The dashboard never places, modifies, or cancels orders — it only
> *observes* the bot's output files.

## Requirements

- Python **3.8+**. No third-party packages required.
- `PyYAML` is *optional* — if installed and you point `--config` at the real
  `btc_5m_profiles.yaml`, profile risk caps come straight from it. Otherwise the
  bundled `config_defaults.json` (mirroring the upstream profiles) is used.

## Quick start (demo)

```bash
cd dashboard
python app.py --demo
# open http://127.0.0.1:8787
```

`--demo` generates realistic synthetic runtime data so you can see the full UI
without a live bot.

## Connect it to the real bot

Point the dashboard at the bot's runtime directory and (optionally) its config:

```bash
python app.py \
  --runtime /path/to/5min-btc-polymarket/skills/btc-5m-live/runtime \
  --config  /path/to/5min-btc-polymarket/config/btc_5m_profiles.yaml \
  --host 0.0.0.0 --port 8787
```

Environment variables work too: `BTC5M_RUNTIME`, `BTC5M_CONFIG`, `PORT`, `HOST`.

## How the bot feeds the dashboard

The execution bot writes; the dashboard reads. **No bot modification is
required** — the dashboard understands the runner's native output directly.

### Files the dashboard reads

| File | Produced by | Used for |
|------|-------------|----------|
| `btc5m.meta.json`, `btc5m.pid` | `btc5m_ctl.sh start` | status / profile / params / uptime |
| `btc5m_<profile>_<UTC>.log` | session runner (one JSON report per 5m session) | trades, P&L, and the live-signal panel |
| `latest.log` | `btc5m_ctl.sh` | newest session / log tail |

Each 5-minute session ends with one JSON report (`started_at`, `params`,
`attempts[]`, `opened`, `closed`, `realized_cashflow_pnl_usdc`, `result`,
`finished_at`). The dashboard:

- builds the **trade history & P&L** from each session's `opened`/`closed`/`pnl`;
- derives the **live signal panel** (UP/DOWN CLOB ask, seconds-to-close, skew,
  spread, gamma) from the **latest** session's `attempts[]` heartbeats.

Because the runner only emits its report **at the end of each session**, the
signal panel reflects the *most recently completed* 5-minute session and labels
itself "fonte: última sessão concluída". For markets this short that's
effectively live (updates each session). The dashboard shows the heartbeat's
`seconds_left` and an "entry window active" flag when 60–150s remain.

### Optional: true real-time ticks (live hook)

For a second-by-second countdown *during* a session, have the runner also drop a
heartbeat snapshot each poll. Add ~3 lines to its monitoring loop:

```python
# inside the heartbeat loop of test_btc_5m_session_exit_sl.py
import json, os, time
with open(os.path.join(RUNTIME_DIR, "btc5m_signal.json"), "w") as fh:
    json.dump({
        "ts": ts_utc(), "slug": slug,
        "clob_up_ask": up_ask, "clob_down_ask": dn_ask,
        "gamma_up": g_up, "gamma_down": g_dn,
        "seconds_left": sec_left, "min_spread": min_spread,
    }, fh)
```

If `btc5m_signal.json` is present the dashboard uses it (labelled "fonte:
heartbeat ao vivo") and ignores the session-report fallback. A
`btc5m_events.jsonl` append-only file (one trade record per line) is likewise
honored if present, useful for durable history if you rotate old session logs.

## Docker

```bash
docker compose up --build      # serves on http://localhost:8787
```

Mount the bot's runtime directory to monitor a live session:

```yaml
# docker-compose.yml — uncomment the volume and set BTC5M_RUNTIME
```

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/state`  | status + signal + summary + trades + equity curve |
| `GET /api/logs`   | last ~160 log lines |
| `GET /api/config` | market, strategy reference, profiles, runtime dir |
| `GET /api/health` | liveness probe |

## Disclaimer

This is monitoring/visualization tooling for an automated trading strategy.
Trading involves risk of loss; nothing here is financial advice. Always run the
bot in dry-run first and respect the configured risk caps.

## Operating the bot safely

Before running the upstream execution bot with real funds, read:

- [`docs/SECURITY_AUDIT.md`](docs/SECURITY_AUDIT.md) — review of how the bot
  handles your wallet key, dependencies, and network.
- [`docs/SAFE_OPERATION.md`](docs/SAFE_OPERATION.md) — step-by-step runbook
  (dedicated wallet, dependency pinning, dry-run validation, kill switch).
- [`docs/env.example`](docs/env.example) — the exact env vars the runner reads.
- [`docs/requirements.pinned.txt`](docs/requirements.pinned.txt) — pinned
  dependency baseline (the upstream repo ships none).
