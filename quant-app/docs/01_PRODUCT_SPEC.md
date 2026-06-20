# 01 — Product Specification

> Single source of truth for product scope. Downstream system/strategy/API/UX
> specs (`02`–`08`) implement this. Mobile-first, non-custodial, no-LLM-in-runtime.

## 0. One-line vision

A **mobile cockpit for a deterministic, momentum-follow-through bot** that trades
Polymarket BTC 5-minute up/down markets — letting a solo quant operator watch the
live signal, see every decision, control caps, and **arm/kill** execution from a
phone, while the strategy itself runs as pure, testable, LLM-free code.

## 1. Product pillars

1. **Deterministic & auditable.** Every entry/exit/hedge is explainable from
   numbers shown on screen. No black box, no LLM in the loop.
2. **Safe by default.** Dry-run/paper is the default mode. Live execution is
   gated behind an explicit arm flag, a typed confirmation, and the runbook in
   `dashboard/docs/SAFE_OPERATION.md`.
3. **Non-custodial.** Keys live only in the operator's execution environment.
   The mobile app and backend API **never** hold or transmit private keys.
4. **Mobile-first observability + control.** The phone is the primary surface:
   live signal, positions, risk gauges, equity, and a one-tap kill switch.

## 2. Personas

### Persona A — "Mara", the solo quant operator (primary)
- Runs the bot herself on a small VPS / home server. Comfortable with a terminal
  but wants to *monitor and control from her phone* during the day.
- Goals: catch malfunctions fast, stop a bad day early, verify the bot is doing
  exactly what the rules say, grow a small dedicated bankroll.
- Pains: a dead bot with an open position; silent cap breaches; not knowing
  *why* a trade fired; fat-fingering live mode.
- Risk posture: treats the bankroll as fully losable; obsessive about key safety.

### Persona B — "Dev", the strategy tinkerer (secondary)
- Same person in a different hat: backtests parameter changes offline, reads the
  indicator math, ships new profiles. Consumes specs `03`/`04`/`05` directly.

### Non-persona (explicitly out)
- A multi-tenant SaaS user, a custodial customer, or anyone whose keys we'd hold.
  We do **not** build for that.

## 3. Jobs-To-Be-Done

| # | When… | I want to… | So that… |
|---|-------|-----------|----------|
| J1 | a 5-min market nears close | see the live signal, countdown, skew, and the *would-be* decision | I trust (or veto) the bot in real time |
| J2 | the bot is running live | see open positions and realized P&L at a glance | I know my exposure without SSH |
| J3 | a day goes wrong | hit a kill switch from my phone | I stop the bleeding instantly |
| J4 | reviewing performance | scrub a trade history + equity curve with the inputs of each trade | I can tell edge from variance |
| J5 | tuning risk | adjust caps / switch profile (conservative↔aggressive) | I match risk to conviction |
| J6 | onboarding a new wallet | confirm dry-run, then deliberately arm live with confirmation | I never go live by accident |
| J7 | the process dies | get alerted (dead-man's switch) | an unmanaged open position can't sit unstopped |

## 4. Scope

### In-scope (the product)
- Mobile app (Expo / React Native, iOS + Android) consuming the backend API.
- Read-only backend API exposing snapshot/signal/decision/positions/trades/
  risk/equity (see `08_API_SPEC.md`), built on the existing dashboard's parser
  of the bot's runtime artifacts.
- Control API: `arm`/`disarm`, `start`/`stop`, `kill`, `set-profile` — all
  auth-gated, all respecting dry-run-by-default.
- Deterministic engine: indicator library, signal/scoring rule, risk manager,
  execution-decision module, backtest harness (`02`–`04`).
- Non-custodial execution adapter (Polymarket `py_clob_client`) in dry-run by
  default (`06`, `crypto/`).
- Alignment with the existing read-only dashboard, security audit, and runbook.

### Out-of-scope (non-goals)
- **No LLM/ML in the trading runtime** for MVP/v1. (An *offline-trained,
  deterministic-at-inference* model is a v2 candidate — see `04`.)
- **No custody.** We never store, transmit, or back up private keys or seed
  phrases on our servers or in the app's cloud.
- **No funds movement UI** (no deposits/withdrawals/bridging in-app). Funding the
  dedicated wallet is a manual, out-of-band operator action.
- **No multi-venue / multi-asset** for MVP — Polymarket BTC 5m up/down only.
- **No social / copy-trading / marketplace.**
- **No "auto-tune with AI"** of live parameters. Parameter changes are explicit.
- **No tax/accounting engine** (we expose raw trade data for export only).

## 5. Success metrics / KPIs

### Product KPIs
- **Time-to-kill:** median seconds from "operator decides to stop" → execution
  halted via app. Target **< 5 s**.
- **Decision transparency:** % of fired trades whose on-screen decision payload
  fully reconstructs the rule that fired. Target **100%** (it's deterministic).
- **Mean-time-to-detect malfunction (MTTD):** from process death / stale heartbeat
  to operator notified. Target **< 30 s** (dead-man's switch).
- **Live-by-accident incidents:** **0**. (Hard gate; any occurrence is a Sev-1.)

### Strategy/operational KPIs (surfaced, not promised)
- Net expectancy per trade after fees+slippage+gas (USDC).
- Rolling 7-/30-day win rate vs. the **break-even hit rate** implied by entry
  price (at 0.70 entry, break-even ≈ 71.4% before costs — see `03`).
- Max drawdown vs. configured daily/bankroll caps.
- Cap-respect rate: % of days where `max_trades_per_day` / `daily_max_loss_pct`
  were honored = **100%** (a breach is a bug).

> KPIs are **observability targets**, not profit guarantees. The product is
> honest that the edge may be small or negative; see `03_QUANT_STRATEGY.md`.

## 6. Phased roadmap

### MVP (paper-first cockpit)
- Backend API over the existing parser; mobile app with **Live**, **Positions**,
  **Trade History**, **Risk/Limits**, **Equity**, **Settings/Profiles**,
  **Kill switch** screens (read + control).
- Engine: indicator lib + deterministic scoring rule + risk manager, all under
  pytest; backtest harness producing metrics. **Dry-run only.**
- Security: token auth on the API, secrets policy, kill switch + dead-man's
  switch alert, aligned to `SECURITY_AUDIT.md`.
- DoD: app boots against mock + live read data; `arm` is disabled (paper only);
  all engine tests green; backtest report generated.

### v1 (gated live)
- Live execution path behind explicit **Arm Live** flow (typed confirmation +
  biometric gate). Real `py_clob_client` adapter wired, still defaulting to
  dry-run; live requires the runbook checklist acknowledged in-app.
- Push notifications for: cap reached, process dead, stop-loss fired, kill done.
- Profile editing with validated ranges; reconcile reported P&L vs on-chain.
- DoD: a full live session at minimum stake completes; kill switch verified live;
  caps demonstrably halt entries.

### v2 (intelligence + polish)
- Optional **offline-trained, deterministic-at-inference** scoring model (frozen
  weights, versioned, identical output for identical input — see `04`). Still no
  live LLM. Shadow-mode comparison against the rule-based score before promotion.
- Multi-profile A/B in paper; richer analytics (regime tagging, slippage
  attribution); configurable alert rules; widget/complication for countdown.
- DoD: model passes shadow-mode acceptance vs. rule baseline; analytics shipped.

## 7. Cross-references
- System: `02_SYSTEM_SPEC.md` · Strategy: `03_QUANT_STRATEGY.md` ·
  Indicators: `04_INDICATORS.md` · Data: `05_DATA_CONTRACTS.md` ·
  Security: `06_SECURITY.md` · UX: `07_UX_UI.md` · API: `08_API_SPEC.md`.
- Existing assets to honor: `dashboard/`, `dashboard/docs/SECURITY_AUDIT.md`,
  `dashboard/docs/SAFE_OPERATION.md`, `dashboard/config_defaults.json`.
