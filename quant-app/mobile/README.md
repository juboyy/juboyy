# Quant Cockpit — Mobile App

Mobile cockpit (Expo / React Native + TypeScript) for the deterministic Polymarket
BTC 5-minute up/down trading bot. Watch the live signal, see every decision, control
caps, and **arm/kill** from a phone. Read-only by default; control actions are gated
(typed confirm + biometric).

Implements the normative specs in `../docs/`: `07_UX_UI.md` (design system / screens),
`08_API_SPEC.md` (REST + WS), `05_DATA_CONTRACTS.md` (types), `01_PRODUCT_SPEC.md` (scope).

## Stack

- **Expo SDK 51** + **Expo Router** (file-based, bottom tabs)
- **TypeScript** (strict)
- **TanStack Query** for data fetching / caching / polling
- **expo-secure-store** (bearer tokens) + **expo-local-authentication** (biometric
  gate for arm / kill)
- **react-native-svg** for the countdown ring + equity chart
- Dark trading theme; design tokens in `src/theme/`

## Run

```bash
cd quant-app/mobile
npm install
npx expo start
```

Then press `i` (iOS simulator), `a` (Android emulator), or scan the QR with Expo Go.

> A real device or emulator is required to actually launch the UI. **Live data also
> needs the backend API** (`08_API_SPEC.md`) reachable at the configured base URL.
> Out of the box the app runs against a **mock data layer** so every screen renders
> with no backend.

### Mock vs live

`app.json → expo.extra`:

```json
{ "useMock": true, "apiBaseUrl": "https://<host>/api/v1", "wsBaseUrl": "wss://<host>/api/v1" }
```

- `useMock: true` (default) — the whole app renders from `src/api/mock.ts` (realistic
  signal / trades / risk / equity, a live-counting countdown, kill/arm simulated).
- `useMock: false` — the typed REST/WS client (`src/api/client.ts`, `src/api/ws.ts`)
  talks to the backend. Set the base URL + bearer token in **More → Settings →
  Connection** (token is written to secure storage); "Test connection" hits `/health`.

## Typecheck

```bash
npx tsc --noEmit
```

Passes with zero errors (strict mode, including `noUncheckedIndexedAccess`).

## Project layout

```
app/                     # Expo Router routes
  _layout.tsx            # providers (QueryClient, safe-area), WS→cache bridge, stack
  (tabs)/
    _layout.tsx          # 5 bottom tabs: Live · Positions · History · Risk · More
    index.tsx            # Live: countdown, signal, score breakdown + gates ("why")
    positions.tsx        # open position(s)
    history.tsx          # trade table + result filter → detail
    risk.tsx             # loss/trades cap gauges, KPI grid, status, params
    more.tsx             # hub → Equity / Settings / About
  equity.tsx             # equity curve + drawdown, range toggles
  settings.tsx           # profile, params (validated), connection, arm-live flow
  about.tsx              # security / non-custodial posture
  trade/[id].tsx         # trade detail (cost breakdown, masked tx, mode)
src/
  theme/                 # design tokens from 07 §1 (colors, type scale, spacing)
  types/                 # TS types mirroring 05 data contracts
  api/                   # typed REST client, WS hook, TanStack Query hooks, mock layer
  components/            # KpiCard, Gauge, SignalPanel, TradeRow, KillButton,
                         # StatusBadge, EquitySparkline, CountdownRing, ConfirmSheet…
  lib/                   # formatting, biometric gate, global-state/banner derivation
```

## Safety model

- **Paper by default.** The header shows global `RODANDO/PARADO/STALE` + `PAPER/LIVE`
  badges. Live **Arm** is **disabled in MVP** (paper only) per `01`; the full flow
  (runbook ack → typed `ARM LIVE` → biometric → `POST /control/arm`) is implemented
  behind the `ARM_ENABLED` flag in `app/settings.tsx` for v1.
- **Kill switch** is a header control reachable from every screen (typed `KILL` +
  biometric → `POST /control/kill`); it is rate-limit-exempt and works even when
  quotes are stale.
- **Non-custodial.** No private keys ever touch the app; addresses are always masked.
```
