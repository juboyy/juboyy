# BTC 5m · Polymarket — Operations Dashboard

A lightweight, **zero-dependency** monitoring dashboard for the
[`5min-btc-polymarket`](https://github.com/Novals83/5min-btc-polymarket)
momentum-trading bot (BTC 5-minute up/down markets on Polymarket).

It reads the bot's `runtime/` artifacts (status, logs, trade results) and
renders, with auto-refresh every 3s:

- **Bot status** — running/stopped, PID, profile, uptime, live params
- **Live signal** — BTC price & interval move, seconds-to-close, UP/DOWN skew,
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

### Files the dashboard reads

| File | Produced by | Used for |
|------|-------------|----------|
| `btc5m.meta.json`, `btc5m.pid` | `btc5m_ctl.sh start` | status / profile / params |
| `btc5m_<profile>_<UTC>.log`, `latest.log` | session runner | log tail + tail-JSON trade results |
| `btc5m_events.jsonl` *(optional)* | streaming hook | richer per-trade history |
| `btc5m_signal.json` *(optional)* | heartbeat hook | live signal panel |

The two optional files give the nicest experience. If they're absent, the
dashboard falls back to scanning the per-session `.log` files for the trade
JSON described in `btc5m_latest_report.py`.

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
