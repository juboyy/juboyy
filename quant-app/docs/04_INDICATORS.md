# 04 — Indicators / Intelligence Specification

> A **deterministic, pure-function** indicator/feature library. Each indicator is
> a function of a `MarketSnapshot` (+ short history) with a fixed formula and
> bounded output. The Signal Engine combines them with a **transparent weighted
> score + hard gates** — not an ML black box. (A v2 optional offline model,
> deterministic at inference, is noted in §8.)
>
> Inputs reference canonical fields in `05_DATA_CONTRACTS.md`. No LLM, ever, in
> this library.

## 0. Conventions
- All functions live in `engine/indicators/` and are **pure**: same input ⇒ same
  output, no I/O, no clock reads (time comes in as `seconds_left`/`ts`).
- `null`/missing input ⇒ the indicator returns `null` and the **staleness gate**
  (§7) handles it; the Signal Engine treats `null` subscores as failing gates.
- Outputs that feed the score are **normalized to [0,1]** (or [-1,1] where signed,
  then mapped). "Side" is `UP`/`DOWN`/`null`.
- History window `H` = last `lookback_polls` snapshots (default 24 ≈ 2 min at
  `poll_sec=5`), passed explicitly; functions never read global state.

## 1. BTC interval momentum / move — `momentum`
- **Inputs:** `btc_price_open` (BTC spot at this market's open), `btc_price_now`
  (latest spot), params `btc_move_usd_min` (70), `btc_move_usd_max_reference`
  (100).
- **Formula:**
  - `btc_move_usd = btc_price_now − btc_price_open`
  - `side = UP if btc_move_usd > 0 else (DOWN if btc_move_usd < 0 else null)`
  - `momentum_score = clamp( (|btc_move_usd| − btc_move_usd_min) /
    (btc_move_usd_max_reference − btc_move_usd_min), 0, 1 )`
    (0 at the $70 floor, 1 at/above the $100 reference; below floor → 0 ⇒ gate
    fails).
- **Outputs:** `btc_move_usd` (USD, signed), `momentum_side` (UP/DOWN/null),
  `momentum_score` ∈ [0,1].
- **Role:** hard gate (`|btc_move_usd| ≥ btc_move_usd_min`) + primary subscore +
  sets the candidate **side**.

## 2. Realized volatility — `realized_vol`
- **Inputs:** history `H` of `btc_price_now` (≥ 8 points), param `rv_window` (24),
  `rv_cap_usd` (150).
- **Formula:**
  - per-poll returns `r_i = btc_price_i − btc_price_{i-1}` (USD)
  - `rv_usd = stdev(r_i) × sqrt(N_polls_per_interval)` (interval-scaled σ in USD)
  - `rv_score = clamp(rv_usd / rv_cap_usd, 0, 1)`
- **Outputs:** `rv_usd` (USD), `rv_score` ∈ [0,1].
- **Role:** *context, not directional.* Used to **discount** confidence when vol
  is high (a $70 move means less in a high-σ regime). Enters the score as a
  **penalty**: `vol_adj = 1 − w_vol·rv_score` (see §6). Also surfaced on Live UI.

## 3. Market skew — `skew`
Two independent estimates; both reported, combined for robustness.
- **Inputs:** `clob_up_ask`, `clob_down_ask`, `gamma_up`, `gamma_down`.
- **Formulas:**
  - **CLOB skew** (matches dashboard parser):
    `skew_clob = max(clob_up_ask, clob_down_ask) /
    (clob_up_ask + clob_down_ask)` ∈ [0.5, 1].
    `skew_clob_side = UP if clob_up_ask ≥ clob_down_ask else DOWN`.
  - **Gamma skew:** `skew_gamma = max(gamma_up, gamma_down) /
    (gamma_up + gamma_down)`; `skew_gamma_side` analogously.
  - **Combined:** `skew_side = skew_clob_side` (CLOB is the tradable book; gamma
    confirms). `skew_agree = (skew_clob_side == skew_gamma_side)`.
  - `skew_score = clamp( (skew_clob − 0.5) / (skew_score_cap − 0.5), 0, 1 )`,
    `skew_score_cap` default 0.95 (skew at/above 0.95 → score 1).
- **Outputs:** `skew_clob` ∈ [0.5,1], `skew_gamma` ∈ [0.5,1], `skew_side`,
  `skew_agree` (bool), `skew_score` ∈ [0,1].
- **Role:** the chosen side must equal `skew_side` (the "stronger side"); subscore
  + agreement bonus. Extreme `skew_clob ≥ hedge.trigger_side_price_gte` arms
  hedging (`03` §5).

## 4. Spread / liquidity quality — `liquidity`
- **Inputs:** `min_spread`, `top_ask_notional_usd` (top-of-book notional on the
  chosen side), params `skip_if_spread_gt` (0.03), `skip_if_top_ask_notional_usd_lt`
  (30), `spread_ref` (0.005), `notional_ref` (100).
- **Formula:**
  - **gates:** `spread_ok = min_spread ≤ skip_if_spread_gt`;
    `notional_ok = top_ask_notional_usd ≥ skip_if_top_ask_notional_usd_lt`.
  - `spread_score = clamp( (skip_if_spread_gt − min_spread) /
    (skip_if_spread_gt − spread_ref), 0, 1 )`
  - `depth_score = clamp( top_ask_notional_usd / notional_ref, 0, 1 )`
  - `liquidity_score = 0.5·spread_score + 0.5·depth_score`
- **Outputs:** `spread_ok`, `notional_ok` (bools), `liquidity_score` ∈ [0,1].
- **Role:** hard gates (both must pass) + subscore. Drives expected slippage in
  the cost model (`03` §8).

## 5. Order-book imbalance — `imbalance`
- **Inputs:** chosen-side `bid_notional_usd`, `ask_notional_usd` at top levels
  (when available); fallback uses `clob_up_ask`/`clob_down_ask` only.
- **Formula:**
  - `imbalance = (bid_notional_usd − ask_notional_usd) /
    (bid_notional_usd + ask_notional_usd)` ∈ [−1, 1] (buy pressure positive).
  - `imbalance_score = clamp( (imbalance + 1) / 2, 0, 1 )` mapped so >0.5 favors
    holding the long side.
  - **side check:** imbalance is only a *confirmation* — if `imbalance` opposes
    the candidate side strongly (`< imbalance_veto`, default −0.6) ⇒ subscore 0.
- **Outputs:** `imbalance` ∈ [−1,1], `imbalance_score` ∈ [0,1].
- **Role:** confirmation subscore; strong opposing imbalance suppresses entry.
  When depth data is unavailable, `imbalance_score = 0.5` (neutral) and weight is
  effectively low.

## 6. Time-to-close decay — `time_decay`
- **Inputs:** `seconds_left`, params `min_entry_seconds_left` (60),
  `entry_window_target_sec` (120), `entry_window_tolerance_sec` (30).
- **Formula:**
  - **window gate:** `in_window = min_entry_seconds_left ≤ seconds_left ≤
    (entry_window_target_sec + entry_window_tolerance_sec)` ⇒ `[60,150]`.
  - `time_decay_score`: peaks near the target (≈120s) where there's enough move
    but little reversal time. Triangular kernel:
    `time_decay_score = clamp( 1 − |seconds_left − entry_window_target_sec| /
    entry_window_tolerance_sec, 0, 1 )` (1 at 120s, →0 at 90s/150s edges; outside
    window the gate fails regardless).
- **Outputs:** `in_window` (bool), `time_decay_score` ∈ [0,1], `seconds_left`.
- **Role:** hard gate (`in_window`) + subscore weighting freshness of the move
  against reversal risk. Drives the Live countdown UI.

## 7. Staleness / heartbeat health — `staleness`
- **Inputs:** `age_sec` (snapshot age), `running` (process alive), params
  `skip_if_quote_stale_sec_gt` (8), `dead_man_sec` (30).
- **Formula:**
  - `fresh = age_sec ≤ skip_if_quote_stale_sec_gt`
  - `process_ok = running == true`
  - `dead_man_tripped = (age_sec > dead_man_sec) or (not running)`
  - `health_score = 1.0 if (fresh and process_ok) else 0.0`
- **Outputs:** `fresh`, `process_ok`, `dead_man_tripped` (bools),
  `health_score` ∈ {0,1}.
- **Role:** **master gate.** If `health_score == 0`, the engine emits no `enter`
  and the API surfaces `PARADO`/stale; `dead_man_tripped` fires the alert (`02`
  §6, `07` armed/error states).

## 8. Deterministic decision: scoring + gates (Signal Engine)

The Signal Engine in `engine/signal/` combines indicators into a **`Signal`** and
then a **`Decision`** with a fixed, auditable rule — reconstructable on screen.

### Step 1 — Hard gates (all must pass, else `Decision = skip`)
```
staleness.fresh AND staleness.process_ok            # health
time_decay.in_window                                # 60 ≤ seconds_left ≤ 150
|momentum.btc_move_usd| ≥ btc_move_usd_min          # momentum present
liquidity.spread_ok AND liquidity.notional_ok       # tradable book
momentum.momentum_side == skew.skew_side            # momentum & skew agree
chosen_side_ask ≥ threshold_price (0.70)
chosen_side_ask ≤ max_entry_ask   (0.92)
risk.allows (caps, kill, no conflicting position)   # 03 §6, risk.apply
```

### Step 2 — Weighted composite score (only if gates pass)
```
raw =  w_mom · momentum.momentum_score          (w_mom  = 0.35)
     + w_skew· skew.skew_score                  (w_skew = 0.25)
     + w_liq · liquidity.liquidity_score        (w_liq  = 0.15)
     + w_imb · imbalance.imbalance_score         (w_imb  = 0.10)
     + w_time· time_decay.time_decay_score      (w_time = 0.15)
vol_adj   = 1 − w_vol · realized_vol.rv_score    (w_vol  = 0.20)
total_score = clamp( raw · vol_adj, 0, 1 )
+ agreement_bonus = +0.05 if skew.skew_agree else 0   (added pre-clamp)
```
Weights sum to 1.0 over the additive terms; `vol_adj` is a multiplicative
penalty; `agreement_bonus` is a small additive nudge. **All weights/params are
config, versioned with the profile.**

### Step 3 — Decision
```
if not all gates:                      Decision = skip   (reason = first failed gate)
elif total_score ≥ enter_score_min:    Decision = enter  (side = chosen_side,
                                                          limit_price = chosen_side_ask,
                                                          size per 03 §4)
else:                                  Decision = hold    (reason = score_below_min)

# overlays (independent of the enter path):
if open_position and stop_loss_hit:    Decision = exit   (reason = stop_loss)
if open_position and seconds_left ≤ exit_before_sec:  Decision = exit (reason = time_exit)
if enter and skew.skew_clob ≥ hedge.trigger_side_price_gte
        and seconds_left ≤ hedge.trigger_seconds_left_lte:  attach hedge leg (03 §5)
if kill_flag:                          Decision = exit-all / block-enter
```

The `Signal` object carries **every subscore and the failed/passed gate list**, so
the Live screen can show *why* (`05` Signal/Decision contracts; `07` Live screen).

### Default weights & params (versioned with profile)
| Param | Default | Range |
|-------|---------|-------|
| `w_mom` | 0.35 | 0–1 |
| `w_skew` | 0.25 | 0–1 |
| `w_liq` | 0.15 | 0–1 |
| `w_imb` | 0.10 | 0–1 |
| `w_time` | 0.15 | 0–1 |
| `w_vol` (penalty) | 0.20 | 0–0.5 |
| `agreement_bonus` | 0.05 | 0–0.2 |
| `enter_score_min` | 0.60 | 0.45–0.80 |
| `lookback_polls` | 24 | 8–60 |
| `rv_cap_usd` | 150 | 50–500 |
| `skew_score_cap` | 0.95 | 0.80–0.99 |
| `imbalance_veto` | −0.6 | −1–0 |

## 9. v2 — optional offline model (deterministic at inference)
- **Allowed only as a drop-in replacement for the §8 *scoring* step**, never the
  gates (gates stay hard-coded, deterministic).
- **Constraints:** trained **offline** on backtest data; weights **frozen +
  versioned** (`model_version` in the Signal contract); inference is a pure
  function (e.g., logistic regression / GBT) producing the **same `total_score`
  for the same `Features`**. No network, no LLM, no online learning at runtime.
- **Promotion:** must run in **shadow mode** (compute alongside the rule score,
  log both) and beat the rule baseline on the §9-of-`03` test gate before it can
  drive decisions. Operator toggles it per profile; default off.
