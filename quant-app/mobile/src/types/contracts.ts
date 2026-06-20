/**
 * TypeScript types mirroring `docs/05_DATA_CONTRACTS.md`.
 *
 * Field names are NORMATIVE: they are returned verbatim by the backend API
 * (`08_API_SPEC.md`) and bound directly in the UI (`07_UX_UI.md`). Do not rename.
 *
 * Conventions (05 §0):
 * - Times are ISO-8601 UTC strings.
 * - Money is USDC as numbers; prices/probabilities are numbers in [0,1].
 * - `null` means unknown/unavailable (never `0` to mean missing).
 * - Enums are lowercase strings.
 */

export type Iso = string;

export type Side = 'up' | 'down';
export type Profile = 'conservative' | 'aggressive';
export type Mode = 'dry_run' | 'live';

/** Derived process state (05 §9). RODANDO=running+fresh, PARADO=dead, STALE=alive-but-stale. */
export type BotState = 'RODANDO' | 'PARADO' | 'STALE';

// ---------------------------------------------------------------------------
// 1. MarketSnapshot
// ---------------------------------------------------------------------------
export interface MarketSnapshot {
  schema_version: string;
  ts: Iso;
  market_slug: string;
  seconds_left: number;
  clob_up_ask: number | null;
  clob_down_ask: number | null;
  clob_up_bid: number | null;
  clob_down_bid: number | null;
  gamma_up: number | null;
  gamma_down: number | null;
  min_spread: number | null;
  top_ask_notional_usd: number | null;
  top_bid_notional_usd: number | null;
  btc_price_open: number | null;
  btc_price_now: number | null;
  age_sec: number | null;
  source: string;
}

// ---------------------------------------------------------------------------
// 2. Features
// ---------------------------------------------------------------------------
export interface Features {
  schema_version: string;
  ts: Iso;
  btc_move_usd: number;
  momentum_side: Side;
  momentum_score: number;
  rv_usd: number;
  rv_score: number;
  skew_clob: number;
  skew_gamma: number;
  skew_side: Side;
  skew_agree: boolean;
  skew_score: number;
  spread_ok: boolean;
  notional_ok: boolean;
  liquidity_score: number;
  imbalance: number;
  imbalance_score: number;
  in_window: boolean;
  time_decay_score: number;
  seconds_left: number;
  fresh: boolean;
  process_ok: boolean;
  dead_man_tripped: boolean;
  health_score: number;
}

// ---------------------------------------------------------------------------
// 3. Signal
// ---------------------------------------------------------------------------
export interface SignalSubscores {
  momentum_score: number;
  skew_score: number;
  liquidity_score: number;
  imbalance_score: number;
  time_decay_score: number;
  rv_penalty: number;
  agreement_bonus: number;
}

export interface SignalWeights {
  w_mom: number;
  w_skew: number;
  w_liq: number;
  w_imb: number;
  w_time: number;
  w_vol: number;
}

/** Each hard gate result (05 §3). Keys are stable; `failed_gate` references one. */
export interface SignalGates {
  health: boolean;
  in_window: boolean;
  momentum_present: boolean;
  spread_ok: boolean;
  notional_ok: boolean;
  skew_agreement: boolean;
  ask_ge_threshold: boolean;
  ask_le_max: boolean;
  risk_allows: boolean;
}

export type GateKey = keyof SignalGates;

export interface Signal {
  schema_version: string;
  ts: Iso;
  market_slug: string;
  chosen_side: Side | null;
  chosen_side_ask: number;
  total_score: number;
  enter_score_min: number;
  subscores: SignalSubscores;
  weights: SignalWeights;
  gates: SignalGates;
  gates_passed: boolean;
  failed_gate: GateKey | null;
  model_version: string;
  age_sec: number;
  source: string;
}

// ---------------------------------------------------------------------------
// 4. Decision
// ---------------------------------------------------------------------------
export type DecisionAction = 'enter' | 'hold' | 'exit' | 'hedge' | 'skip';
export type RiskVerdict = 'allow' | 'veto' | 'clamp';

export interface DecisionHedge {
  enabled: boolean;
  side: Side | null;
  notional_usd: number | null;
}

export interface Decision {
  schema_version: string;
  ts: Iso;
  market_slug: string;
  action: DecisionAction;
  side: Side | null;
  limit_price: number | null;
  size_usd: number;
  shares: number;
  reason: string;
  hedge: DecisionHedge;
  risk_verdict: RiskVerdict;
  risk_reason: string | null;
  mode: Mode;
  armed: boolean;
  signal_ref_ts: Iso;
}

// ---------------------------------------------------------------------------
// 5. Order / Position
// ---------------------------------------------------------------------------
export type PositionStatus = 'open' | 'closed' | 'settled' | 'failed';

export interface Position {
  schema_version: string;
  order_id: string;
  ts: Iso;
  market_slug: string;
  side: Side;
  entry_price: number;
  shares: number;
  cost_usdc: number;
  open_tx: string | null;
  mode: Mode;
  status: PositionStatus;
  stop_loss_price: number;
  seconds_left_at_entry: number;
  profile: Profile;
}

// ---------------------------------------------------------------------------
// 6. TradeResult
// ---------------------------------------------------------------------------
export type TradeOutcome = 'win' | 'loss' | 'breakeven';
export type CloseReason = 'settlement' | 'stop_loss' | 'time_exit' | 'kill';
export type CloseStatus = 'settled' | 'closed' | 'failed' | 'skipped';

export interface TradeResult {
  schema_version: string;
  ts: Iso;
  profile: Profile;
  result: TradeOutcome;
  side: Side;
  market_slug: string;
  entry_price: number;
  shares: number;
  cost_usdc: number;
  open_tx: string | null;
  close_reason: CloseReason;
  close_success: boolean;
  close_status: CloseStatus;
  close_skipped: boolean;
  close_tx: string | null;
  realized_cashflow_pnl_usdc: number;
  btc_move_usd: number;
  skew: number;
  seconds_left_at_entry: number;
  threshold_price: number;
  stake_usd: number;
  fees_usdc: number;
  slippage_usdc: number;
  gas_usdc: number;
  mode: Mode;
}

// ---------------------------------------------------------------------------
// 7. RiskState
// ---------------------------------------------------------------------------
export interface RiskState {
  schema_version: string;
  ts: Iso;
  profile: Profile;
  mode: Mode;
  armed: boolean;
  killed: boolean;
  running: boolean;
  pnl_today: number;
  pnl_total: number;
  trades_today: number;
  trades_total: number;
  wins: number;
  losses: number;
  win_rate: number;
  max_trades_per_day: number;
  trades_cap_used_pct: number;
  daily_loss_cap_usd: number;
  daily_loss_cap_pct: number;
  loss_cap_used_pct: number;
  best_trade: number;
  worst_trade: number;
  open_position: Position | null;
  dead_man_tripped: boolean;
}

// ---------------------------------------------------------------------------
// 8. Account / Equity
// ---------------------------------------------------------------------------
export interface EquityPoint {
  ts: Iso;
  cum_pnl: number;
  pnl: number;
}

export interface Account {
  schema_version: string;
  ts: Iso;
  equity_usd: number | null;
  funder_address_masked: string;
  signature_type: number;
  currency: string;
  equity_curve: EquityPoint[];
}

// ---------------------------------------------------------------------------
// 9. BotStatus
// ---------------------------------------------------------------------------
export interface BotStatusParams {
  threshold: number;
  stake_usd: number;
  stop_loss_pct: number;
  exit_before_sec: number;
  min_entry_seconds_left: number;
  poll_sec: number;
  execute: boolean;
}

export interface BotStatus {
  schema_version: string;
  running: boolean;
  state: BotState;
  pid: number | null;
  profile: Profile;
  mode: Mode;
  armed: boolean;
  killed: boolean;
  started_at: Iso;
  uptime_sec: number;
  params: BotStatusParams;
  log_path: string;
}

// ---------------------------------------------------------------------------
// Health (08 §3) — lightweight liveness/dead-man probe.
// ---------------------------------------------------------------------------
export interface Health {
  ok: boolean;
  state: BotState;
  age_sec: number;
  dead_man_tripped: boolean;
}

// ---------------------------------------------------------------------------
// Config (08 §3 GET /config) — active profile, params + validation ranges (03 §7).
// ---------------------------------------------------------------------------
export interface ParamRange {
  min: number;
  max: number;
  step?: number;
}

export interface ConfigParams {
  threshold_price: number;
  stake_usd: number;
  max_notional_usd: number;
  daily_max_loss_pct: number;
  max_trades_per_day: number;
  stop_loss_pct: number;
  exit_before_sec: number;
  hedge_enabled: number; // 0/1 flag kept numeric for ParamField validation
  hedge_notional_usd: number;
}

export type ConfigParamKey = keyof ConfigParams;

export interface ConfigResponse {
  schema_version: string;
  ts: Iso;
  profile: Profile;
  params: ConfigParams;
  ranges: Record<ConfigParamKey, ParamRange>;
}

// ---------------------------------------------------------------------------
// Control responses (08 §4)
// ---------------------------------------------------------------------------
export interface KillResult {
  killed: boolean;
  blocking_new_entries: boolean;
  positions_closed: number;
  positions_close_skipped: number;
}

export interface ControlAck {
  ok: boolean;
  profile?: Profile;
  mode?: Mode;
  armed?: boolean;
  killed?: boolean;
}

// ---------------------------------------------------------------------------
// Alert (08 §6) — drives 07 banners + push.
// ---------------------------------------------------------------------------
export type AlertKind = 'dead_man' | 'cap_reached' | 'stop_loss' | 'killed';

export interface Alert {
  kind: AlertKind;
  message: string;
}
