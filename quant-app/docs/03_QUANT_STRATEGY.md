# 03 — Quant Strategy Specification

> The strategy is **deterministic momentum follow-through into the 5-minute
> close** on Polymarket BTC up/down markets. This document is the normative
> source for entry/exit/sizing/hedging rules, parameters, and the backtest
> protocol. Indicator math is in `04_INDICATORS.md`; field names in `05`.

## 1. Market & mechanics
- **Venue:** Polymarket BTC 5-minute up/down prediction markets (binary). Each
  market resolves at a fixed close `T_close`; "UP" pays $1 if BTC at close ≥ BTC
  at open, else "DOWN" pays $1. Shares trade in [0,1] (≈ probability).
- **We trade the CLOB** via `py_clob_client` (POLYGON). Cost basis = best-ask
  price × shares. Settlement is binary at `T_close`.
- **Time variable:** `seconds_left = T_close - now`.

## 2. Edge hypothesis (honest)

**Claim.** In the final ~2 minutes before close, an already-established BTC move
within the interval has **path-dependent persistence**: a $70–$100 move with
little time left is unlikely to fully reverse, so the in-the-money side's true
settle probability can exceed its CLOB ask. We buy that side when the market has
**not yet** fully priced the persistence (ask ≤ a threshold that still leaves
edge), preferring the side the **market skew** already supports.

**Why it *could* be +EV.**
- Short horizon ⇒ less time for mean-reversion to undo the move.
- Microstructure lag: CLOB asks can trail a fast spot move by seconds.
- We only act when momentum *and* skew agree (two weak signals → one stronger).

**Where it breaks (the honest risks).**
- **Cost wall.** Buying at ask `p` needs win rate `w > p / (payout_after_fees)`.
  At `p = 0.70` with binary $1 payout and zero fees, break-even `w = p = 0.70`;
  with fees+slippage+gas the effective break-even is **~71–73%**. *We must clear
  that after costs or the strategy is negative — full stop.*
- **Reversal tail.** BTC can whip in the last seconds (news, liquidations); a
  $70 move is not safe. Losers pay the full premium.
- **Adverse selection.** If the ask is cheap, it may be cheap *because* informed
  flow expects reversal. Skew agreement mitigates but doesn't eliminate this.
- **Liquidity/slippage.** Thin top-of-book near close ⇒ fills worse than quoted;
  exits may be impossible (we may have to hold to settlement).
- **Resolution/operational risk.** Oracle/resolution disputes, stale quotes,
  process death with an open position.

**Stance.** Treat positive backtest results as *hypotheses to be killed*, not
proof. Default to **paper**. Go live only at minimum size after the backtest +
forward paper clear the cost-adjusted break-even with margin.

## 3. Entry rules (deterministic)

All thresholds reference parameters in §7 and indicators in `04`.

**Pre-conditions (all must hold, else `skip`):**
1. **Entry window:** `min_entry_seconds_left (60) ≤ seconds_left ≤
   entry_window_target (120) + tolerance (30)` ⇒ effective window
   `60 ≤ seconds_left ≤ 150`. (Matches dashboard `in_entry_window`.)
2. **Freshness:** snapshot `age_sec ≤ skip_if_quote_stale_sec_gt (8)`.
3. **Spread quality:** `min_spread ≤ skip_if_spread_gt (0.03)`.
4. **Liquidity:** top-ask notional `≥ skip_if_top_ask_notional_usd_lt (30)`.
5. **Risk allows:** not killed, caps not hit, no conflicting open position
   (see `risk.apply`, §6).

**Direction & trigger:**
6. **Momentum confirmation:** `|btc_move_usd|` over the interval is within the
   active band — default `btc_move_usd_min (70) ≤ |btc_move_usd|`
   (`btc_move_usd_max_reference = 100` is a reference, not a hard cap; see
   `momentum_score` in `04`). The momentum **side** = `UP` if `btc_move_usd > 0`
   else `DOWN`.
7. **Skew agreement:** the **stronger side** by CLOB ask = `argmax(clob_up_ask,
   clob_down_ask)`; require it to **agree** with the momentum side. If they
   disagree → `skip` (no trade) unless extreme-hedge logic in §5 applies.
8. **Price threshold:** the chosen side's `clob_*_ask ≥ threshold_price (0.70)`
   AND `≤ max_entry_ask (0.92)` (don't pay near-certainty for ~no edge).
9. **Composite score gate:** the deterministic `signal.total_score`
   (`04` §6) `≥ enter_score_min (0.60)`.

If 1–9 hold → **Decision = enter**, `side = momentum/skew side`,
`limit_price = clob_side_ask` (marketable limit), `size` per §4.

> Note on the original bot: it uses "best-ask threshold 0.70; choose stronger
> side over threshold." We preserve that as the **price gate (8)** and **stronger
> side (7)**, and add the explicit momentum+score gates so the decision is fully
> reconstructable on screen.

## 4. Position sizing

- **Base stake:** `stake_usd` (default 5) per trade.
- **Notional cap:** `max_notional_usd` (conservative 8 / aggressive 15) — order
  cost may not exceed this.
- **Per-trade risk cap:** `risk_per_trade_pct_equity` (8% / 15%) of `equity_usd`,
  when equity is known; the binding size is `min(stake_usd-implied,
  max_notional_usd, risk_pct × equity)`.
- **Shares:** `shares = floor( min(stake_usd, max_notional_usd) / limit_price )`.

### Kelly / risk-of-ruin note
- For a binary buy at ask `p` with win prob `w`, profit-if-win `b = (1-p)/p`
  (odds), loss-if-lose = 1 (full premium). Kelly fraction
  `f* = (w·b − (1−w)) / b = w − (1−w)/b`.
  At `p=0.70 (b≈0.4286)`, `w=0.72`: `f* = 0.72 − 0.28/0.4286 ≈ 0.72 − 0.653 =
  0.067` ⇒ **~6.7% of bankroll** at *full* Kelly — and only marginally positive.
- **We run fractional Kelly (≤ ¼ Kelly)** and the *fixed-stake* caps above, which
  are far below full Kelly, precisely because `w` is uncertain and over-betting a
  thin edge ⇒ ruin. If `w ≤ p` after costs, `f* ≤ 0` ⇒ **do not trade.**
- **Risk-of-ruin:** with daily caps `daily_max_loss_pct` (10%/15%) and
  `max_trades_per_day` (12/20), worst modeled daily loss is bounded; the bankroll
  is sized as fully-losable (per `SAFE_OPERATION.md` §0).

## 5. Hedging rules
Mirrors `config_defaults.json`:
- **Enabled** per profile (`hedge.enabled = true`).
- **Trigger:** when the chosen side's price is extreme
  (`clob_side_ask ≥ trigger_side_price_gte`: 0.95 conservative / 0.93 aggressive)
  **and** `seconds_left ≤ trigger_seconds_left_lte` (45 / 50), place a small
  **opposite-side** hedge of `hedge_notional_usd` in
  `[hedge_notional_usd_min, hedge_notional_usd_max]` (1–2 / 1–3 USDC).
- **Rationale:** at extreme skew the upside is tiny and a last-second reversal is
  the dominant risk; a cheap opposite leg caps the loss tail. Hedge is **never**
  larger than the main leg and is itself subject to liquidity/spread gates.

## 6. Exit rules (deterministic)
- **Stop-loss:** if the position's mark `current_ask_side` falls
  `≥ stop_loss_pct_from_entry` (0.25 / 0.30) below `entry_price`, **exit** at
  market (subject to liquidity). `Decision = exit, reason = stop_loss`.
- **Time exit:** at `seconds_left ≤ exit_before_sec (20)`, **exit** any open
  position not intended to be held to settlement (avoids unhedged settlement
  risk and lets the next market be considered). `reason = time_exit`.
- **Settlement hold:** if exit liquidity is absent (top-bid notional below floor)
  the position is **held to settlement**; P&L = binary outcome. This is flagged
  in the trade result (`closed.close_skipped = true`).
- **Kill:** a kill flag forces `exit` attempts on all positions and blocks new
  entries (best-effort safe close; if impossible, alert + hold).

## 7. Parameters (defaults + ranges)

| Param | Default (cons / aggr) | Range | Source |
|-------|----------------------|-------|--------|
| `entry_window_target_sec` | 120 | 90–150 | strategy_reference |
| `entry_window_tolerance_sec` | 30 | 0–45 | strategy_reference |
| `min_entry_seconds_left` | 60 | 30–90 | session_timing |
| `exit_before_sec` | 20 | 5–45 | session_timing |
| `btc_move_usd_min` | 70 | 40–150 | strategy_reference |
| `btc_move_usd_max_reference` | 100 | 80–250 | strategy_reference |
| `threshold_price` | 0.70 | 0.55–0.85 | signal |
| `max_entry_ask` | 0.92 | 0.80–0.97 | new (cost-edge cap) |
| `enter_score_min` | 0.60 | 0.45–0.80 | new (composite gate) |
| `stake_usd` | 5 / 5 | 1–50 | sizing |
| `max_notional_usd` | 8 / 15 | 1–100 | sizing |
| `risk_per_trade_pct_equity` | 8 / 15 | 1–25 | sizing |
| `daily_max_loss_pct` | 10 / 15 | 1–50 | sizing |
| `max_trades_per_day` | 12 / 20 | 1–100 | sizing |
| `stop_loss_pct_from_entry` | 0.25 / 0.30 | 0.05–0.50 | stop_loss |
| `hedge.enabled` | true | bool | hedge |
| `hedge.trigger_side_price_gte` | 0.95 / 0.93 | 0.85–0.99 | hedge |
| `hedge.trigger_seconds_left_lte` | 45 / 50 | 10–90 | hedge |
| `hedge.hedge_notional_usd_min/max` | 1–2 / 1–3 | 0.5–10 | hedge |
| `skip_if_quote_stale_sec_gt` | 8 | 2–30 | execution_safety |
| `skip_if_spread_gt` | 0.03 | 0.005–0.10 | execution_safety |
| `skip_if_top_ask_notional_usd_lt` | 30 | 5–200 | execution_safety |
| `poll_sec` | 5 | 1–15 | runtime |

> Defaults are taken from `dashboard/config_defaults.json`; `max_entry_ask`,
> `enter_score_min`, and the composite score are **additions** for an auditable
> decision. The bot's existing behavior is the special case
> `max_entry_ask→1.0`, `enter_score_min→0`.

## 8. Cost model (must be applied everywhere)
For each simulated/real trade:
- **Slippage:** `slippage_usdc = shares × slip_ticks × tick`, default
  `slip_ticks = 1`, `tick = 0.01` (worse fill than quoted ask; configurable per
  liquidity). Conservatively assume we cross half the spread.
- **Gas:** `gas_usdc` per on-chain action (open and close). Default model:
  `gas_usdc = 0.02` per action (Polygon; configurable). Dry-run uses the same
  model so paper P&L is comparable.
- **Trading fees:** Polymarket CLOB fee schedule `fee_bps` applied to notional
  (default `fee_bps = 0`; set to live schedule before any live conclusion).
- **Net P&L (canonical):** `realized_cashflow_pnl_usdc` = settlement/exit cashflow
  − cost basis − slippage − gas − fees. This is the field stored in
  `btc5m_events.jsonl` and read by the dashboard.

## 9. Backtest protocol (rigorous)

### Data
- **Source:** recorded `MarketSnapshot` series (CLOB asks, gamma, `min_spread`,
  `seconds_left`, slug) + aligned **BTC spot** at ≥ `poll_sec` resolution, per
  5-min market, ideally tick-for-tick around the close window. Persisted from the
  bot's own heartbeats and/or a historical pull.
- **Coverage:** ≥ 60 calendar days spanning multiple volatility regimes (low,
  trending, choppy/whipsaw). Note regime per market for stratified metrics.

### Split & methodology
- **Walk-forward / out-of-sample.** Train/tune on the *earliest* 60% (parameter
  selection only), validate on the next 20%, **lock parameters**, then report on
  the final 20% **test** set untouched during tuning. No peeking.
- **No look-ahead:** at decision time only data with `ts ≤ now` is visible;
  settlement is revealed only after `T_close`.
- **Deterministic seeds** for any simulated fill jitter; identical inputs ⇒
  identical outputs (same pure spine as live, `02` §2).
- **Costs always on:** apply §8 to every trade; report gross and net.

### Metrics (report all, on the test set)
| Metric | Definition |
|--------|-----------|
| **Win rate** `w` | wins / settled trades |
| **Break-even hit rate** | mean entry `p` adjusted for costs; the bar `w` must clear |
| **Expectancy** | mean `realized_cashflow_pnl_usdc` per trade (and per $ staked) |
| **Sharpe** | mean(per-trade net) / std(per-trade net) × √(trades/yr); also daily Sharpe |
| **Max drawdown** | peak-to-trough of the cumulative `cum_pnl` equity curve |
| **Turnover** | trades/day; notional traded vs bankroll |
| **Profit factor** | gross wins / gross losses |
| **Slippage/gas/fee drag** | total cost as % of gross P&L |
| **Cap-respect** | days honoring `max_trades_per_day` & `daily_max_loss_pct` (must be 100%) |

### Acceptance gate (go/no-go to paper→live)
- Net expectancy per trade **> 0** on the **test** set, **after** §8 costs.
- `w` **exceeds** the cost-adjusted break-even (~71–73% at 0.70 entry) with a
  confidence interval that excludes the break-even bar.
- Max drawdown ≤ configured bankroll cap; cap-respect = 100%.
- Result replicated in **forward paper** (`mode=dry_run`) over a fresh window
  before any live arming. **If any fails → do not go live.**
