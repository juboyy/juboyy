# 07 — UX / UI Design System & Screen Specs

> Mobile-first cockpit (Expo / React Native). Dark trading theme. All data bound
> to `05_DATA_CONTRACTS.md` field names and served by `08_API_SPEC.md`. Read-only
> by default; control actions (arm/stop/kill) are explicit and gated (`06`).

## 1. Design tokens

### Color (dark trading theme)
| Token | Hex | Use |
|-------|-----|-----|
| `bg/base` | `#0B0E11` | app background |
| `bg/surface` | `#141A1F` | cards, sheets |
| `bg/elevated` | `#1C242B` | inputs, raised rows |
| `border/subtle` | `#263038` | dividers |
| `text/primary` | `#E8EDF2` | primary text |
| `text/secondary` | `#9AA7B2` | labels, captions |
| `text/muted` | `#5E6B76` | disabled/hints |
| `accent/up` (long/win) | `#1FBF75` | UP side, profit, RODANDO |
| `accent/down` (short/loss) | `#F0506E` | DOWN side, loss, PARADO |
| `accent/info` | `#3B82F6` | links, neutral highlights |
| `accent/warn` | `#F5A524` | stale, cap-near, caution |
| `accent/armed` | `#F0506E` | live-armed banner (danger) |
| `accent/paper` | `#3B82F6` | dry-run badge |

> Up/down use green/red but are **never** the only signal — always paired with a
> ▲/▼ glyph + label for color-blind accessibility (WCAG 1.4.1).

### Type scale (system font; SF Pro / Roboto)
| Token | Size/Line | Weight | Use |
|-------|-----------|--------|-----|
| `display` | 34/40 | 700 | countdown seconds, hero P&L |
| `title` | 22/28 | 600 | screen titles |
| `headline` | 17/24 | 600 | card titles |
| `body` | 15/22 | 400 | content |
| `caption` | 13/18 | 400 | labels |
| `mono` | 15/20 | 500 | prices, P&L, addresses (tabular) |

### Spacing & radius
- Base unit **4px**; scale `4/8/12/16/24/32`. Card padding `16`. Screen gutter `16`.
- Radius: `sm 8`, `md 12`, `lg 16`, `pill 999`. Min touch target **44×44**.
- Elevation via surface tokens (no heavy shadows on dark).

### Accessibility
- Contrast ≥ 4.5:1 for text; ≥ 3:1 for large/UI. Dynamic Type respected.
- Every status conveyed by **icon + text + color** (never color alone).
- All controls labeled for screen readers; kill/arm have explicit confirm + a11y
  announcements.

## 2. Component inventory
- **AppHeader** — title + global `StatusPill` (RODANDO/PARADO/STALE) + mode badge.
- **StatusPill** — `state` from `BotStatus` (green/red/amber + label).
- **ModeBadge** — `dry_run` (blue "PAPER") / `live` ("LIVE" red, armed).
- **CountdownRing** — circular `seconds_left`; band-colored when `in_window`.
- **SideTag** — ▲ UP / ▼ DOWN, colored.
- **SignalCard** — chosen side, `chosen_side_ask`, `total_score` vs
  `enter_score_min`, decision `action`, reason.
- **ScoreBreakdown** — per-`subscore` bars + weights + gate checklist (✓/✗).
- **GateList** — `gates` object rendered as pass/fail rows; failed gate emphasized.
- **PnLValue** — colored, mono, signed (`+2.03` / `-3.50`).
- **CapGauge** — progress bar for `loss_cap_used_pct` / `trades_cap_used_pct`
  (amber ≥70%, red ≥100%).
- **PositionRow / TradeRow** — `Position`/`TradeResult` summary.
- **EquityChart** — line of `equity_curve[].cum_pnl`.
- **ProfileSelector** — conservative/aggressive segmented control.
- **ParamField** — labeled numeric input with min/max validation (`03` §7 ranges).
- **PrimaryButton / DangerButton** — actions; Danger for kill/arm.
- **ConfirmSheet** — bottom sheet w/ typed confirmation + biometric for control.
- **Banner** — armed/stale/dead-man/error states.
- **EmptyState / ErrorState / Skeleton** — shared non-happy states.

## 3. Navigation model
**Bottom tab bar (5 tabs)** + a persistent **AppHeader**; the **Kill switch** is a
header-level danger control reachable from every screen.
```
Tabs:  [ Live ]  [ Positions ]  [ History ]  [ Risk ]  [ More ]
Header: ◀ title …………………… [StatusPill][ModeBadge][�⛔ Kill]
"More" → Equity · Settings/Profiles · About/Security
Modals: ConfirmSheet (arm/stop/kill), ParamEdit, ProfileSwitch
```
- **Live** is the default tab. Kill is always one tap from anywhere (header).
- Equity is reachable from Live (hero tap) and from More.

## 4. Global states (apply to all screens)
| State | Trigger | Treatment |
|-------|---------|-----------|
| loading | first fetch | Skeletons; never block the Kill control |
| empty | no trades/positions | EmptyState with guidance microcopy |
| error | API unreachable | ErrorState + "Retry"; show last-known cached values, stamped stale |
| stale | `age_sec > 8` or `state=STALE` | Amber banner "Quotes stale — entries paused" |
| armed | `mode=live && armed` | Red persistent banner "LIVE — armed" + extra confirm on actions |
| dead-man | `dead_man_tripped` | Red banner "Bot not responding — open position may be unmanaged" + push |

## 5. Screen specs

### 5.1 Live (signal + countdown) — `GET /signal`, `/snapshot`, WS
- **Hero:** `CountdownRing(seconds_left)` with `market_slug`; band highlights
  `in_window` (60–150s).
- **SignalCard:** `SideTag(chosen_side)`, `chosen_side_ask` (mono),
  `total_score` vs `enter_score_min` (progress), decision `action` (ENTER/HOLD/
  SKIP/EXIT) + `reason`.
- **ScoreBreakdown:** bars for momentum/skew/liquidity/imbalance/time, the
  `rv_penalty`, `agreement_bonus`; **GateList** below (each `gates` entry ✓/✗,
  `failed_gate` highlighted) — this is the "why" surface.
- **Market chips:** `btc_move_usd`, `skew_clob`, `min_spread`,
  `top_ask_notional_usd`, `rv_usd`.
- **States:** stale→amber + "entries paused"; PARADO→grey + "bot stopped".
- **Microcopy:** ENTER → "Conditions met — would enter UP @ 0.71 (paper)".
  SKIP → "No trade: {failed_gate} (e.g. momentum below \$70)".

### 5.2 Positions — `GET /positions`
- List of open `Position` rows: `SideTag`, `entry_price`, `shares`,
  `cost_usdc`, live mark, unrealized P&L, `stop_loss_price`, `seconds_left`.
- Open-position banner mirrors `RiskState.open_position`.
- Empty: "No open positions." Error/stale handled globally.
- (No manual close in MVP; exits are engine-driven. Kill in header forces exit.)

### 5.3 Trade History — `GET /trades`
- Reverse-chronological `TradeResult` rows: time, `SideTag`, `result`
  (win/loss), `PnLValue(realized_cashflow_pnl_usdc)`, `market_slug`.
- Tap → detail: `entry_price`, `shares`, `cost_usdc`, `close_reason`,
  `btc_move_usd`, `skew`, `seconds_left_at_entry`, cost breakdown
  (`fees/slippage/gas_usdc`), `open_tx`/`close_tx` (masked, copyable), `mode`.
- Filters: profile, result, date. Export (CSV) action.
- Empty: "No trades yet — running in paper mode."

### 5.4 Risk / Limits — `GET /risk`
- **CapGauge** ×2: `loss_cap_used_pct` (vs `daily_loss_cap_usd`/`_pct`),
  `trades_cap_used_pct` (vs `max_trades_per_day`).
- KPI grid: `pnl_today`, `pnl_total`, `win_rate`, `wins`/`losses`,
  `best_trade`/`worst_trade`.
- Status row: `profile`, `mode`, `armed`, `killed`, `dead_man_tripped`.
- When a cap is at 100%: red banner "Daily cap reached — new entries blocked."

### 5.5 Equity — `GET /equity`
- **EquityChart** of `equity_curve[].cum_pnl` over time; hero `pnl_total` +
  `equity_usd`. Range toggles (session / 7d / 30d / all).
- Drawdown shading from peak. Empty: "Equity curve builds as trades settle."

### 5.6 Settings / Profiles — `GET /config`, `POST /control/profile`
- **ProfileSelector** (conservative/aggressive) → `POST /control/profile`
  (control-scope; confirm sheet).
- **ParamField** list bound to `03` §7 params with **min/max validation**
  (threshold, stake_usd, max_notional_usd, daily_max_loss_pct,
  max_trades_per_day, stop_loss_pct, exit_before_sec, hedge.*). Out-of-range
  blocked client-side and server-side.
- **Connection:** API base URL + token (secure storage), test-connection.
- **Mode & Arm:** `ModeBadge`; **Arm Live** is here, behind:
  1) toggle to live → 2) runbook checklist acknowledgement → 3) typed
  "ARM LIVE" → 4) biometric → `POST /control/arm`. Disarm is one tap.
  In MVP, Arm is **disabled** (paper only) with explainer.
- Microcopy on arm: "Live mode places real orders with real funds. Caps and kill
  switch remain active. You accept the risk (see Security)."

### 5.7 Kill switch — header control → `POST /control/kill`
- Always-visible header ⛔. Tap → **ConfirmSheet**: "Kill now? Blocks new entries
  and attempts to close open positions." → biometric → fire.
- Result toast: "Kill sent — new entries blocked." On failure to close:
  red banner "Could not close position — check host." (per `06` IR).
- Kill path is rate-limit-exempt and works even in error/stale states.

## 6. Microcopy principles
- Plain, numeric, honest. Always state **mode** ("(paper)") on action copy.
- Never imply profit; surface break-even context where relevant ("entry 0.71 needs
  ~71% win rate after costs").
- Errors say what happened + the next action ("API unreachable — showing last
  data from 14:05. Retry?").
