# Quant Trading App — Build Loop & Orchestration

A single iterative loop that drives the project across every workstream until
each is **covered and working** against an explicit Definition of Done (DoD).

## The loop

```
            ┌─────────────────────────────────────────────┐
            │ 1. SPEC    define/refine the workstream spec  │
            │ 2. BUILD   implement (delegated to helpers)   │
            │ 3. VERIFY  run tests / lint / boot the thing  │
            │ 4. GATE    DoD met?  ── no ──┐                │
            │      │ yes                    │ (re-enter)    │
            │      ▼                        └──────────────►│
            │ 5. INTEGRATE + commit                         │
            └─────────────────────────────────────────────┘
   Repeat per workstream until ALL gates are green → then notify the owner.
```

Each iteration is logged in `.loop/STATUS.md`. The owner is notified **only**
when every workstream's gate is green (or when a decision is truly blocked).

## Workstreams & Definition of Done

| # | Workstream | "Covered & working" means | Dir |
|---|-----------|----------------------------|-----|
| 1 | **Specification** | End-to-end product + system spec, data contracts, glossary, non-goals. | `docs/` |
| 2 | **Quant strategy** | Written strategy with entry/exit/sizing rules, edge hypothesis, params, and a backtest protocol. | `docs/` + `engine/` |
| 3 | **Indicators / intelligence** | Deterministic indicator library (momentum, skew, volatility, microstructure) with unit tests. | `engine/` |
| 4 | **Deterministic engine** | Signal + risk + execution-decision engine, **no LLM at runtime**, with passing pytest + a backtest harness producing metrics. | `engine/` |
| 5 | **Security** | Threat model, non-custodial key handling, guardrails, kill switch, secrets policy; ties to the existing audit. | `docs/` + `crypto/` |
| 6 | **UX / UI** | Design system + screen specs + flows for the mobile app. | `docs/` + `mobile/` |
| 7 | **Product** | PRD: personas, jobs-to-be-done, scope, metrics, roadmap. | `docs/` |
| 8 | **Mobile app** | Expo/React Native app that boots, renders the core screens, and consumes the API (mock + live). | `mobile/` |
| 9 | **Crypto** | Non-custodial wallet/execution adapter (Polymarket via py_clob_client) with dry-run default + safety guards. | `crypto/` |

## Global invariants (apply to all workstreams)

- **No LLM in the trading runtime.** Strategy/indicators/execution are pure,
  deterministic, testable code. LLMs may assist *development*, never *decisions*.
- **Dry-run by default.** Live execution is gated behind an explicit flag and the
  safety runbook (`dashboard/docs/SAFE_OPERATION.md`).
- **Non-custodial.** Private keys never leave the operator's environment and are
  never logged, committed, or sent anywhere.
- **Reproducible.** Pinned deps; deterministic seeds in backtests; tests are the
  source of truth for "working".

## Definition of "done for this session"

A working, tested baseline of all 9 workstreams committed to this branch:
specs written, the deterministic engine + indicators green under pytest, the
mobile app scaffolded and booting against mock data, and the crypto adapter in
dry-run. Production concerns that require the owner (real funds, real accounts,
app-store deployment, live keys) are flagged as **gated**, not silently skipped.
