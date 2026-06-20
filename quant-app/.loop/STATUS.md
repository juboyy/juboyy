# Loop Status

Updated each iteration. Gate = ✅ green / 🟡 in progress / ⬜ not started / 🔒 gated on owner.

| # | Workstream | Gate | Notes |
|---|-----------|------|-------|
| 1 | Specification | ✅ | 8 docs written, internally consistent |
| 2 | Quant strategy | ✅ | `03_QUANT_STRATEGY.md` (spec); engine impl in progress |
| 3 | Indicators / intelligence | 🟡 | `04_INDICATORS.md` spec done; engine agent building |
| 4 | Deterministic engine | 🟡 | engine agent building (indicators+signal+risk+backtest+capture) |
| 5 | Security | ✅ | `06_SECURITY.md` + ties to completed bot audit; crypto agent enforces |
| 6 | UX / UI | ✅ | `07_UX_UI.md` design system + screens; mobile agent implementing |
| 7 | Product | ✅ | `01_PRODUCT_SPEC.md` |
| 8 | Mobile app | 🟡 | mobile agent scaffolding Expo/RN |
| 9 | Crypto | 🟡 | crypto agent building paper adapter (dry-run default) |

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
