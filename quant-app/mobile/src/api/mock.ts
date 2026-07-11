/**
 * Mock data layer (08 read shapes / 05 contracts).
 *
 * Lets the whole app render WITHOUT a backend. Returns realistic, internally
 * consistent objects and advances a small simulation (countdown, signal flips,
 * trade settles) so the Live/Positions/Risk/History screens look alive.
 *
 * Switched on by `config.useMock` (app.json `expo.extra.useMock`).
 */

import type {
  Account,
  Alert,
  BotStatus,
  ConfigResponse,
  ControlAck,
  Decision,
  Health,
  KillResult,
  MarketSnapshot,
  Position,
  RiskState,
  Signal,
  TradeResult,
} from '@/types';

const nowIso = (offsetSec = 0): string =>
  new Date(Date.now() + offsetSec * 1000).toISOString();

// --- Mutable simulation state (module singleton) ---------------------------
interface SimState {
  startedAt: number;
  killed: boolean;
  armed: boolean;
  mode: 'dry_run' | 'live';
  profile: 'conservative' | 'aggressive';
}

const sim: SimState = {
  startedAt: Date.now() - 2105 * 1000,
  killed: false,
  armed: false,
  mode: 'dry_run',
  profile: 'conservative',
};

/** A 5-minute market slug whose close time cycles, so seconds_left counts down. */
function currentMarket(): { slug: string; secondsLeft: number } {
  const cycle = 300; // 5 minutes
  const epoch = Math.floor(Date.now() / 1000);
  const secondsLeft = cycle - (epoch % cycle);
  const closeEpoch = epoch + secondsLeft;
  const closeDate = new Date(closeEpoch * 1000);
  const yyyy = closeDate.getUTCFullYear();
  const mm = String(closeDate.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(closeDate.getUTCDate()).padStart(2, '0');
  const hh = String(closeDate.getUTCHours()).padStart(2, '0');
  const min = String(closeDate.getUTCMinutes()).padStart(2, '0');
  return { slug: `btc-updown-${yyyy}-${mm}-${dd}-${hh}${min}`, secondsLeft };
}

// --- Snapshot --------------------------------------------------------------
export function mockSnapshot(): MarketSnapshot {
  const { slug, secondsLeft } = currentMarket();
  const upAsk = 0.71;
  return {
    schema_version: '1.0',
    ts: nowIso(),
    market_slug: slug,
    seconds_left: secondsLeft,
    clob_up_ask: upAsk,
    clob_down_ask: 0.3,
    clob_up_bid: 0.69,
    clob_down_bid: 0.28,
    gamma_up: 0.68,
    gamma_down: 0.32,
    min_spread: 0.02,
    top_ask_notional_usd: 64.0,
    top_bid_notional_usd: 51.0,
    btc_price_open: 64850.0,
    btc_price_now: 64928.0,
    age_sec: 3,
    source: 'clob+gamma',
  };
}

// --- Signal ----------------------------------------------------------------
export function mockSignal(): Signal {
  const { slug, secondsLeft } = currentMarket();
  const inWindow = secondsLeft >= 60 && secondsLeft <= 150;
  // Flip between an ENTER-worthy and a SKIP signal across cycles for variety.
  const enterish = inWindow;
  const totalScore = enterish ? 0.64 : 0.52;
  const enterMin = 0.6;
  const passed = totalScore >= enterMin && inWindow;
  return {
    schema_version: '1.0',
    ts: nowIso(),
    market_slug: slug,
    chosen_side: 'up',
    chosen_side_ask: 0.71,
    total_score: totalScore,
    enter_score_min: enterMin,
    subscores: {
      momentum_score: enterish ? 0.27 : 0.12,
      skew_score: 0.45,
      liquidity_score: 0.71,
      imbalance_score: 0.565,
      time_decay_score: inWindow ? 0.93 : 0.4,
      rv_penalty: 0.054,
      agreement_bonus: 0.05,
    },
    weights: {
      w_mom: 0.35,
      w_skew: 0.25,
      w_liq: 0.15,
      w_imb: 0.1,
      w_time: 0.15,
      w_vol: 0.2,
    },
    gates: {
      health: true,
      in_window: inWindow,
      momentum_present: enterish,
      spread_ok: true,
      notional_ok: true,
      skew_agreement: true,
      ask_ge_threshold: true,
      ask_le_max: true,
      risk_allows: !sim.killed,
    },
    gates_passed: passed,
    failed_gate: passed ? null : !inWindow ? 'in_window' : 'momentum_present',
    model_version: 'rule-1.0',
    age_sec: 3,
    source: 'session_report',
  };
}

// --- Decision --------------------------------------------------------------
export function mockDecision(): Decision {
  const sig = mockSignal();
  const action = sig.gates_passed ? 'enter' : 'skip';
  return {
    schema_version: '1.0',
    ts: nowIso(),
    market_slug: sig.market_slug,
    action,
    side: sig.chosen_side,
    limit_price: sig.chosen_side_ask,
    size_usd: 5.0,
    shares: 7,
    reason: sig.gates_passed
      ? `score_${sig.total_score.toFixed(2)}_ge_min_${sig.enter_score_min.toFixed(2)}`
      : `gate_${sig.failed_gate ?? 'unknown'}`,
    hedge: { enabled: false, side: null, notional_usd: null },
    risk_verdict: sim.killed ? 'veto' : 'allow',
    risk_reason: sim.killed ? 'killed' : null,
    mode: sim.mode,
    armed: sim.armed,
    signal_ref_ts: sig.ts,
  };
}

// --- Positions -------------------------------------------------------------
const openPosition: Position = {
  schema_version: '1.0',
  order_id: 'ord_01HZX4QK3M7N2P',
  ts: nowIso(-180),
  market_slug: currentMarket().slug,
  side: 'up',
  entry_price: 0.71,
  shares: 7,
  cost_usdc: 4.97,
  open_tx: null,
  mode: 'dry_run',
  status: 'open',
  stop_loss_price: 0.5325,
  seconds_left_at_entry: 116,
  profile: 'conservative',
};

export function mockPositions(): Position[] {
  if (sim.killed) return [];
  return [{ ...openPosition, market_slug: currentMarket().slug }];
}

// --- Trades ----------------------------------------------------------------
const TRADES: TradeResult[] = [
  {
    schema_version: '1.0',
    ts: nowIso(-300),
    profile: 'conservative',
    result: 'win',
    side: 'up',
    market_slug: 'btc-updown-2026-06-20-1405',
    entry_price: 0.71,
    shares: 7,
    cost_usdc: 4.97,
    open_tx: '0xabc1234def5678abc1234def5678abc1234def56',
    close_reason: 'settlement',
    close_success: true,
    close_status: 'settled',
    close_skipped: false,
    close_tx: '0xdef5678abc1234def5678abc1234def5678abc12',
    realized_cashflow_pnl_usdc: 2.03,
    btc_move_usd: 78.0,
    skew: 0.703,
    seconds_left_at_entry: 116,
    threshold_price: 0.7,
    stake_usd: 5,
    fees_usdc: 0.0,
    slippage_usdc: 0.07,
    gas_usdc: 0.04,
    mode: 'dry_run',
  },
  {
    schema_version: '1.0',
    ts: nowIso(-900),
    profile: 'conservative',
    result: 'loss',
    side: 'down',
    market_slug: 'btc-updown-2026-06-20-1350',
    entry_price: 0.68,
    shares: 7,
    cost_usdc: 4.76,
    open_tx: '0x1111aaaa2222bbbb3333cccc4444dddd5555eeee',
    close_reason: 'stop_loss',
    close_success: true,
    close_status: 'closed',
    close_skipped: false,
    close_tx: '0x6666ffff7777aaaa8888bbbb9999cccc0000dddd',
    realized_cashflow_pnl_usdc: -3.5,
    btc_move_usd: -41.0,
    skew: 0.66,
    seconds_left_at_entry: 122,
    threshold_price: 0.7,
    stake_usd: 5,
    fees_usdc: 0.0,
    slippage_usdc: 0.09,
    gas_usdc: 0.04,
    mode: 'dry_run',
  },
  {
    schema_version: '1.0',
    ts: nowIso(-1500),
    profile: 'aggressive',
    result: 'win',
    side: 'up',
    market_slug: 'btc-updown-2026-06-20-1340',
    entry_price: 0.73,
    shares: 9,
    cost_usdc: 6.57,
    open_tx: '0x2222bbbb3333cccc4444dddd5555eeee6666ffff',
    close_reason: 'time_exit',
    close_success: true,
    close_status: 'closed',
    close_skipped: false,
    close_tx: '0x7777aaaa8888bbbb9999cccc0000dddd1111eeee',
    realized_cashflow_pnl_usdc: 2.9,
    btc_move_usd: 112.0,
    skew: 0.74,
    seconds_left_at_entry: 134,
    threshold_price: 0.72,
    stake_usd: 7,
    fees_usdc: 0.0,
    slippage_usdc: 0.11,
    gas_usdc: 0.05,
    mode: 'dry_run',
  },
  {
    schema_version: '1.0',
    ts: nowIso(-2400),
    profile: 'conservative',
    result: 'breakeven',
    side: 'up',
    market_slug: 'btc-updown-2026-06-20-1325',
    entry_price: 0.7,
    shares: 7,
    cost_usdc: 4.9,
    open_tx: '0x3333cccc4444dddd5555eeee6666ffff7777aaaa',
    close_reason: 'settlement',
    close_success: true,
    close_status: 'settled',
    close_skipped: false,
    close_tx: '0x8888bbbb9999cccc0000dddd1111eeee2222ffff',
    realized_cashflow_pnl_usdc: 0.0,
    btc_move_usd: 5.0,
    skew: 0.7,
    seconds_left_at_entry: 110,
    threshold_price: 0.7,
    stake_usd: 5,
    fees_usdc: 0.0,
    slippage_usdc: 0.08,
    gas_usdc: 0.04,
    mode: 'dry_run',
  },
];

export function mockTrades(limit = 200): TradeResult[] {
  return TRADES.slice(0, limit);
}

export function mockTrade(orderIdOrIndex: string): TradeResult | undefined {
  // Trades have no order_id field in the contract; key history rows by open_tx.
  return TRADES.find((t) => t.open_tx === orderIdOrIndex) ?? TRADES[0];
}

// --- Risk ------------------------------------------------------------------
export function mockRisk(): RiskState {
  return {
    schema_version: '1.0',
    ts: nowIso(),
    profile: sim.profile,
    mode: sim.mode,
    armed: sim.armed,
    killed: sim.killed,
    running: !sim.killed,
    pnl_today: -0.4,
    pnl_total: 12.1,
    trades_today: 4,
    trades_total: 37,
    wins: 24,
    losses: 11,
    win_rate: 68.6,
    max_trades_per_day: 12,
    trades_cap_used_pct: 33.3,
    daily_loss_cap_usd: 9.6,
    daily_loss_cap_pct: 10,
    loss_cap_used_pct: 4.2,
    best_trade: 2.9,
    worst_trade: -3.5,
    open_position: sim.killed ? null : { ...openPosition, market_slug: currentMarket().slug },
    dead_man_tripped: false,
  };
}

// --- Equity ----------------------------------------------------------------
export function mockEquity(): Account {
  const base = Date.now() - 30 * 60 * 1000;
  const points = [
    { dt: 0, pnl: 0.0, cum: 0.0 },
    { dt: 5, pnl: 2.1, cum: 2.1 },
    { dt: 10, pnl: -3.5, cum: -1.4 },
    { dt: 15, pnl: 2.9, cum: 1.5 },
    { dt: 20, pnl: 0.0, cum: 1.5 },
    { dt: 25, pnl: 2.03, cum: 3.53 },
    { dt: 30, pnl: 8.57, cum: 12.1 },
  ];
  return {
    schema_version: '1.0',
    ts: nowIso(),
    equity_usd: 96.0,
    funder_address_masked: '0x1234…ab12',
    signature_type: 2,
    currency: 'USDC',
    equity_curve: points.map((p) => ({
      ts: new Date(base + p.dt * 60 * 1000).toISOString(),
      cum_pnl: p.cum,
      pnl: p.pnl,
    })),
  };
}

// --- Status / Health -------------------------------------------------------
export function mockStatus(): BotStatus {
  return {
    schema_version: '1.0',
    running: !sim.killed,
    state: sim.killed ? 'PARADO' : 'RODANDO',
    pid: sim.killed ? null : 4821,
    profile: sim.profile,
    mode: sim.mode,
    armed: sim.armed,
    killed: sim.killed,
    started_at: new Date(sim.startedAt).toISOString(),
    uptime_sec: Math.floor((Date.now() - sim.startedAt) / 1000),
    params: {
      threshold: 0.7,
      stake_usd: 5,
      stop_loss_pct: 0.25,
      exit_before_sec: 20,
      min_entry_seconds_left: 60,
      poll_sec: 5,
      execute: false,
    },
    log_path: '/workspace/runtime/btc5m_conservative_20260620T133000.log',
  };
}

export function mockHealth(): Health {
  return {
    ok: !sim.killed,
    state: sim.killed ? 'PARADO' : 'RODANDO',
    age_sec: 3,
    dead_man_tripped: false,
  };
}

// --- Config ----------------------------------------------------------------
export function mockConfig(): ConfigResponse {
  return {
    schema_version: '1.0',
    ts: nowIso(),
    profile: sim.profile,
    params: {
      threshold_price: 0.7,
      stake_usd: 5,
      max_notional_usd: 25,
      daily_max_loss_pct: 10,
      max_trades_per_day: 12,
      stop_loss_pct: 0.25,
      exit_before_sec: 20,
      hedge_enabled: 0,
      hedge_notional_usd: 0,
    },
    ranges: {
      threshold_price: { min: 0.55, max: 0.85, step: 0.01 },
      stake_usd: { min: 1, max: 50, step: 1 },
      max_notional_usd: { min: 5, max: 200, step: 1 },
      daily_max_loss_pct: { min: 1, max: 50, step: 1 },
      max_trades_per_day: { min: 1, max: 100, step: 1 },
      stop_loss_pct: { min: 0.05, max: 0.9, step: 0.01 },
      exit_before_sec: { min: 5, max: 120, step: 1 },
      hedge_enabled: { min: 0, max: 1, step: 1 },
      hedge_notional_usd: { min: 0, max: 100, step: 1 },
    },
  };
}

// --- Control (mutate sim) --------------------------------------------------
export function mockKill(): KillResult {
  const hadOpen = !sim.killed;
  sim.killed = true;
  return {
    killed: true,
    blocking_new_entries: true,
    positions_closed: hadOpen ? 1 : 0,
    positions_close_skipped: 0,
  };
}

export function mockArm(): ControlAck {
  sim.armed = true;
  sim.mode = 'live';
  return { ok: true, armed: true, mode: 'live' };
}

export function mockDisarm(): ControlAck {
  sim.armed = false;
  sim.mode = 'dry_run';
  return { ok: true, armed: false, mode: 'dry_run' };
}

export function mockSetProfile(profile: 'conservative' | 'aggressive'): ControlAck {
  sim.profile = profile;
  return { ok: true, profile };
}

export function mockStart(profile: 'conservative' | 'aggressive'): ControlAck {
  sim.killed = false;
  sim.profile = profile;
  return { ok: true, profile, mode: sim.mode };
}

export function mockStop(): ControlAck {
  return { ok: true };
}

export function mockConfigUpdate(): ControlAck {
  return { ok: true };
}

// --- Mock alert stream (used by the WS hook in mock mode) ------------------
export const mockAlerts: Alert[] = [];
