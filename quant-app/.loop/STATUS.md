# Loop Status

Updated each iteration. Gate = ✅ green / 🟡 in progress / ⬜ not started / 🔒 gated on owner.

| # | Workstream | Gate | Notes |
|---|-----------|------|-------|
| 1 | Specification | ✅ | 8 docs, internally consistent |
| 2 | Quant strategy | ✅ | `03_QUANT_STRATEGY.md` → implemented in `engine/` |
| 3 | Indicators / intelligence | ✅ | 7 pure indicators in `engine/indicators/`, unit-tested |
| 4 | Deterministic engine | ✅ | `engine/` — **70 pytest green**; signal/risk/sizing/costs/backtest/capture |
| 5 | Security | ✅ | `06_SECURITY.md` + bot audit; enforced in `crypto/safety.py` |
| 6 | UX / UI | ✅ | `07_UX_UI.md` → tokens + components in `mobile/` |
| 7 | Product | ✅ | `01_PRODUCT_SPEC.md` |
| 8 | Mobile app | ✅ | `mobile/` Expo/RN+TS — **tsc --noEmit clean**, mock layer renders all screens |
| 9 | Crypto | ✅ | `crypto/` — **42 pytest green**; paper default, live gated |

**Baseline verification:** engine 70 + crypto 42 = **112 Python tests passing**;
mobile `npx tsc --noEmit` exit 0. All committed to `claude/quant-app-loop`.

## Open decisions surfaced to owner (grill)
- **BTC spot source** for the `momentum` indicator (`04 §1`) — the current bot
  only logs CLOB/gamma, no spot. Engine builds a **pluggable spot-source
  interface**; a concrete live feed is **gated on owner**.
- **Validation-first vs build-first ordering** — backtest needs ≥60d recorded
  data (`03 §9`). Mitigation: engine includes the **data-capture recorder +
  backtest harness** so validation infra exists regardless; live arming gated.

## Iteration log

- **Iter 0** — scaffolding + orchestration created; spec workstream kicked off.
- **Iter 1** — all 8 specs complete & consistent. Build phase launched: engine,
  mobile, crypto agents in parallel. Folded the grill's validation-first concern
  into the engine mandate (capture + backtest + pluggable spot source).
- **Iter 2** — all 9 gates GREEN. engine (70) + crypto (42) tests pass; mobile
  typechecks clean. Fixed a footgun: renamed `signal.py`→`signal_engine.py`
  (stdlib shadow). Baseline complete.
- **Iter 3** — backend API (36 tests) + read-only public feeds/capture (23 tests).
  Full suite: 171 passing. Backend boot + auth smoke verified locally.
- **Iter 4 (deploy prep)** — `deploy/` Dockerfile + compose (backend API +
  dashboard) and `mobile/vercel.json` (static web demo). Honest split: control
  plane = container only (stateful + WebSocket); Vercel = read-only demo. Actual
  external deploy gated on owner (this sandbox has no outbound network / Docker).

## Gated on owner (cannot be closed without you)
- **BTC spot feed** for `momentum` (`04 §1`) — interface built; concrete live
  source is gated. Engine/backtest run on recorded/mock data meanwhile.
- **Backtest data** — `engine/capture.py` records snapshots; needs ≥60d of real
  data (`03 §9`) before any live go/no-go.
- **Backend API server** (`08_API_SPEC.md`) — specced; mobile runs on its mock
  layer. Wiring engine→HTTP API is the next iteration.
- **Live trading** — real funds, Polymarket creds, app-store builds: all gated
  behind `SAFE_OPERATION.md` + explicit arming.
