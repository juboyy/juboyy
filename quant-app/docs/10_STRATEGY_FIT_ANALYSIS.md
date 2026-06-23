# 10 — Strategy Fit Analysis (adherence to OUR resources & advantages)

> Question: of the Polymarket strategies, which have the most **adherence** to
> what *we actually have*? Scored against our real resources, not hype.

## Our resources & advantages (the honest inventory)

| We HAVE | We LACK |
|---------|---------|
| Deterministic engine (indicators, signal, risk, sizing, costs, backtest) | Sub-100ms execution / dedicated Polygon RPC / colocation |
| Read-only public feeds (gamma/CLOB/spot) + capture | An information edge over the market |
| Reverse-engineered **profit-desk data layer** (positions/activity/PnL by wallet) | Large capital (we're a small, paper-first operator) |
| Paper/gated non-custodial execution adapter | MEV protection / private order flow |
| **Claude available for *offline* analysis** (invariant: no LLM in decision runtime) | Speed. We will lose every millisecond race. |
| Discipline: cost model, risk caps, kill switch | — |

## The decisive market fact

Average arbitrage window compressed **12.3s (2024) → 2.7s (2026)**; **73% of arb
profit is captured by sub-100ms bots** on dedicated RPC nodes; **>30%** of active
wallets are bots; **~7.6%** of wallets are profitable. **Any strategy whose edge
is speed is a strategy we lose.** Our existing 5-min BTC latency-momentum bot
lives in *exactly* that arena — the most contested, latency-dominated one — where
our public-RPC retail setup has **no edge**. Keep it as paper/research; do not
expect it to win live.

## Fit matrix (● = strength of fit to US, 1–5)

| Strategy | Latency-safe | Low capital | Deterministic | Data ready | Edge durable | Claude-offline lever | **Fit** |
|----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Liquidity Rewards / passive MM near midpoint** | ●●●● | ●●● | ●●●●● | ●●●● | ●●●● | – | **HIGH** |
| **Resolution-edge / dispute screening** | ●●●●● | ●●●●● | ●●● | ●●● | ●●●● | ●●●●● | **HIGH** |
| **Smart-money signal on SLOW markets (politics)** | ●●●● | ●●●● | ●●●● | ●●●●● | ●●● | ●●● | **HIGH/MED** |
| NegRisk / cross-market arbitrage | ● | ●●●● | ●●●●● | ●●● | ● | – | LOW |
| 5-min BTC latency momentum *(current bot)* | ● | ●●● | ●●●●● | ●●●●● | ● | – | LOW |
| Naive copy-trading | ● | ●●● | ●●● | ●●●●● | ● | – | LOW |

## The three high-adherence plays

### 1. Liquidity Rewards / Maker Rebates — *monetize our discipline, not speed* ★ top pick
Polymarket **pays you to post limit orders near the midpoint** — the
**Liquidity Rewards Program** scores resting orders **every minute** and pays
daily; **orders need not be filled**. Plus **Maker Rebates** return **20–25% of
taker fees** to makers (daily, in pUSD). Eligible in Politics, Crypto, Sports,
etc.
- **Why it fits us:** per-minute scoring, **not** a sub-100ms race; the edge is a
  **protocol subsidy**, not a directional or informational call; quote placement
  is deterministic (our engine's home turf); modest capital; works across
  categories. We earn yield for *being disciplined liquidity*, which is exactly
  what our stack already is.
- **Risk:** inventory / adverse selection (you get filled when you're wrong).
  Manageable with our risk module (caps, skew-aware quoting, kill switch) and the
  cost model. This is the classic MM trade-off, not a speed disadvantage.

### 2. Resolution-edge / dispute screening — *the Claude-offline differentiator*
Most traders never read the **resolution criteria**; ambiguous rules + a ~24h
dispute window create a non-speed edge.
- **Why it fits us:** **not a latency race** (hours, not seconds); low capital;
  high edge; and it is the one place our **Claude-offline** advantage is decisive
  — Claude *screens* market descriptions/news to flag ambiguous or mispriced
  resolutions, producing a **watchlist**. Decisions/execution stay deterministic
  & human-gated, so the **no-LLM-in-runtime** invariant holds (analysis is
  offline, not in the trade loop).

### 3. Smart-money as a *signal* (not millisecond copy-trading)
Naive copy-trading is structurally broken for retail (you buy *above* the whale;
MEV front-runs you in ms; ~7.6–12.7% profitable). **But** we already built the
profit-desk data layer (positions/activity by wallet). On **slow markets
(politics)** where winners hold for days, following **verified long-term wallets
as a research signal** — not racing their fills — sidesteps the latency trap.
Low build effort (data layer done); pairs with #2.

## Recommendation

**Pivot the center of gravity** from the latency-losing 5-min BTC arena toward:
- **#1 Liquidity Rewards/MM** as the *yield engine* (deterministic, subsidized,
  our infra's strength), and
- **#2 + #3** as a *politics alpha layer* (Claude-offline resolution screening +
  smart-money signals) on slow markets where speed doesn't decide.

This matches our advantages (deterministic discipline + Claude-offline + the data
layer we built) and avoids the arena where we structurally lose.

### Build plan (reuse what exists)
| Play | Reuse | Add |
|------|-------|-----|
| Liquidity rewards MM | `engine/` (signal→risk→sizing→costs), `crypto/` adapter, `backend/` | `engine/strategies/market_maker.py` (quote-near-mid, inventory caps, reward-aware), reward-tracker in `feeds/` |
| Resolution screening | `feeds/` (gamma market descriptions), `backend/` | offline `tools/resolution_screener` (Claude analyzes descriptions → JSON watchlist; never in runtime) |
| Smart-money signal | profit-desk RE (`docs/09`), `feeds/` | `feeds/profit_desk.py` wallet client + a smart-money scorer feeding the watchlist |

## Honest caveats
- Liquidity rewards yields are real but **finite and competed**; model the reward
  pool share and adverse selection before sizing. Still the **least bad** edge for us.
- Resolution/dispute edge needs **judgment** — semi-automated, human-gated; not a
  push-button printer.
- None of this changes the base rate: most wallets lose. Paper-first, costs-on,
  walk-forward, then minimum size.
