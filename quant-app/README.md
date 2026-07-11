# Quant Trading App — 5min BTC / Polymarket

A deterministic, mobile-first quant trading system for Polymarket BTC 5-minute
up/down markets. Built via an iterative loop across 9 workstreams
(see `ORCHESTRATION.md` and `.loop/STATUS.md`).

> **Invariants:** no LLM in the trading runtime · dry-run/paper by default ·
> non-custodial (keys never leave the operator's environment).

## Layout

| Path | What | Status |
|------|------|--------|
| `docs/` | The 8 normative specs (product, system, **quant strategy**, indicators, data contracts, security, UX/UI, API). | source of truth |
| `engine/` | Deterministic Python engine: 7 pure indicators, signal engine (gates → score → decision), risk, sizing, cost model, **walk-forward backtest**, data-capture recorder, CLI. | ✅ 70 tests |
| `crypto/` | Execution adapters: deterministic **paper** adapter (default) + **gated** live Polymarket adapter; arming / kill / dead-man switch; non-custodial key handling. | ✅ 42 tests |
| `mobile/` | Expo / React Native + TypeScript app: Live · Positions · History · Risk · More, kill switch, PAPER/LIVE arming, mock layer renders with no backend. | ✅ tsc clean |

## Quick start

```bash
# Engine — run the deterministic decision + backtest
cd quant-app/engine && pip install pytest && python -m pytest -q
python -m engine.cli backtest engine/tests/fixtures/backtest_small.jsonl --json   # from quant-app/

# Crypto — paper adapter (dry-run) tests
cd quant-app/crypto && python -m pytest -q

# Mobile — renders on its mock layer (no backend needed)
cd quant-app/mobile && npm install && npx expo start
```

## How it fits together

```
 Polymarket CLOB + BTC spot ─▶ datasource ─▶ engine (pure: indicators→signal→risk→sizing)
                                                   │  Decision
                                                   ▼
                                       crypto adapter (paper default / live gated)
                                                   │  TradeResult
                                                   ▼
                                runtime/*.jsonl ─▶ backend API ─▶ mobile app + dashboard
```

The backend HTTP/WS API (`docs/08_API_SPEC.md`) is specced; the mobile app
currently runs on its built-in mock layer. Wiring the engine to a live API is the
next iteration.

## Honest status (read this before trading anything)

Per `docs/03_QUANT_STRATEGY.md`, entering at a 0.70 ask requires a **>~71–73%**
real win rate after costs to be +EV. That is **unproven** and **not yet testable**
with available data. The system is therefore **paper-by-default**: collect data
with `engine/capture.py`, validate on the walk-forward backtest (`03 §9`), and
only then consider arming live — behind `../dashboard/docs/SAFE_OPERATION.md`.
This repo is operational/educational infrastructure, not financial advice.
