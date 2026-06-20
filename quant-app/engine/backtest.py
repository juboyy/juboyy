"""
backtest.py — walk-forward backtest harness (`03 §9`).

Replays recorded JSONL snapshots through the SAME pure spine
(`indicators → signal → risk → sizing → costs`) used live. Properties:
  - **No look-ahead**: at decision time only snapshots with `ts <= now` (i.e. the
    history accumulated so far in the market) are visible; the settlement outcome
    (`settle_side`) is revealed only after the trade is entered.
  - **Costs always on**: every entered trade is priced through `costs.compute_costs`.
  - **Deterministic**: no clock reads, no RNG except seeded fill jitter
    (`fill_seed`), so identical inputs ⇒ identical outputs.
  - **Caps respected**: a per-day `RiskState` enforces `max_trades_per_day` and
    `daily_max_loss_pct` exactly as live (`risk.apply`).

Records are grouped by `market_slug`; within a market they are ordered by `ts`.
The first snapshot that yields a `Decision.action == "enter"` (and passes risk)
opens one trade for that market; settlement P&L uses `settle_side`.

Reports ALL `03 §9` metrics and returns them as a dict from `run_backtest(path)`.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .contracts import MarketSnapshot, Position, RiskState
from .config import Profile, get_profile
from . import indicators, signal as signal_mod, risk as risk_mod, costs as costs_mod
from .datasource import RecordedSource

TRADING_DAYS_PER_YEAR = 252


@dataclass
class SimTrade:
    market_slug: str
    day: str
    side: str
    entry_price: float
    shares: int
    won: bool
    cost_basis: float
    slippage_usdc: float
    gas_usdc: float
    fees_usdc: float
    realized_cashflow_pnl_usdc: float
    result: str
    ts: Optional[str] = None


def _day_of(ts: Optional[str]) -> str:
    if not ts:
        return "unknown"
    return ts[:10]


def _group_by_market(records: List[dict]) -> Dict[str, List[dict]]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for r in records:
        groups[r.get("market_slug") or "unknown"].append(r)
    for slug in groups:
        groups[slug].sort(key=lambda r: r.get("ts") or "")
    return groups


def _won(side: str, settle_side: Optional[str]) -> Optional[bool]:
    if settle_side is None:
        return None
    return side == settle_side


def simulate(records: List[dict], profile: Profile, fill_seed: int = 7) -> List[SimTrade]:
    """Run the deterministic spine over recorded records, returning settled trades.

    A per-day `RiskState` is threaded so daily caps bind exactly as live. Within a
    market the first risk-allowed `enter` opens a single trade.
    """
    groups = _group_by_market(records)

    # day-keyed risk state (caps reset per UTC day)
    day_state: Dict[str, RiskState] = {}

    def state_for(day: str) -> RiskState:
        if day not in day_state:
            day_state[day] = RiskState(
                profile=profile.name,
                running=True,
                max_trades_per_day=profile.max_trades_per_day,
                daily_loss_cap_pct=profile.daily_max_loss_pct,
                daily_loss_cap_usd=(
                    profile.equity_usd * profile.daily_max_loss_pct / 100.0
                    if profile.equity_usd is not None
                    else None
                ),
                age_sec=0,
            )
        return day_state[day]

    trades: List[SimTrade] = []

    # markets in chronological order of their first snapshot (no look-ahead across)
    ordered_markets = sorted(
        groups.items(), key=lambda kv: (kv[1][0].get("ts") or "") if kv[1] else ""
    )

    for slug, recs in ordered_markets:
        history: List[MarketSnapshot] = []
        opened = False
        for rec in recs:
            snap = MarketSnapshot.from_dict(rec)
            # history is only snapshots seen so far (no look-ahead)
            hist = history[-profile.lookback_polls:]
            features = indicators.compute(snap, hist, profile)
            history.append(snap)

            if opened:
                continue

            day = _day_of(snap.ts)
            state = state_for(day)

            allow = risk_mod.apply(state, profile, candidate_side=features.momentum_side,
                                   candidate_market=slug)
            sig, dec = signal_mod.evaluate_and_decide(
                features, snap, profile, risk_allows=allow.allowed
            )

            if dec.action != "enter":
                continue

            settle_side = rec.get("settle_side")
            won = _won(dec.side, settle_side)
            if won is None:
                # no settlement label ⇒ cannot score this market; skip it.
                continue

            cb = costs_mod.compute_costs(
                shares=dec.shares,
                entry_price=dec.limit_price,
                won=won,
                profile=profile,
                n_gas_actions=1,
            )
            trade = SimTrade(
                market_slug=slug,
                day=day,
                side=dec.side,
                entry_price=dec.limit_price,
                shares=dec.shares,
                won=won,
                cost_basis=cb.cost_basis_usdc,
                slippage_usdc=cb.slippage_usdc,
                gas_usdc=cb.gas_usdc,
                fees_usdc=cb.fees_usdc,
                realized_cashflow_pnl_usdc=cb.realized_cashflow_pnl_usdc,
                result=cb.result,
                ts=snap.ts,
            )
            trades.append(trade)
            opened = True

            # update the day's risk state so caps bind for the next market
            state.trades_today += 1
            state.pnl_today += cb.realized_cashflow_pnl_usdc

    return trades


def compute_metrics(trades: List[SimTrade], profile: Profile) -> Dict[str, object]:
    """All `03 §9` metrics on the supplied trades."""
    n = len(trades)
    if n == 0:
        return {
            "trades": 0,
            "win_rate": None,
            "break_even_hit_rate": None,
            "expectancy_per_trade": None,
            "expectancy_per_dollar": None,
            "sharpe_per_trade": None,
            "sharpe_annualized": None,
            "max_drawdown": 0.0,
            "turnover_trades_per_day": 0.0,
            "profit_factor": None,
            "cost_drag_pct": None,
            "cap_respect_pct": 100.0,
            "net_pnl_total": 0.0,
            "gross_pnl_total": 0.0,
        }

    pnls = [t.realized_cashflow_pnl_usdc for t in trades]
    wins = [t for t in trades if t.won]
    win_rate = len(wins) / n

    # break-even hit rate: mean cost-adjusted break-even win rate the trades face
    be_bars = [
        costs_mod.cost_adjusted_breakeven(t.entry_price, t.shares, profile) for t in trades
    ]
    break_even_hit_rate = sum(be_bars) / len(be_bars)

    expectancy_per_trade = sum(pnls) / n
    total_staked = sum(t.cost_basis for t in trades)
    expectancy_per_dollar = (sum(pnls) / total_staked) if total_staked > 0 else None

    if n >= 2 and statistics.pstdev(pnls) > 0:
        mean = statistics.mean(pnls)
        sd = statistics.stdev(pnls)
        sharpe_per_trade = mean / sd if sd > 0 else None
        days = max(1, len({t.day for t in trades}))
        trades_per_day = n / days
        sharpe_annualized = (
            sharpe_per_trade * math.sqrt(trades_per_day * TRADING_DAYS_PER_YEAR)
            if sharpe_per_trade is not None
            else None
        )
    else:
        sharpe_per_trade = None
        sharpe_annualized = None

    # max drawdown of cumulative equity curve
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    days = max(1, len({t.day for t in trades}))
    turnover = n / days

    gross_wins = sum(p for p in pnls if p > 0)
    gross_losses = -sum(p for p in pnls if p < 0)
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (
        math.inf if gross_wins > 0 else None
    )

    total_costs = sum(t.slippage_usdc + t.gas_usdc + t.fees_usdc for t in trades)
    # gross P&L = net + costs (costs are subtracted from gross to get net)
    gross_pnl = sum(pnls) + total_costs
    cost_drag_pct = (total_costs / abs(gross_pnl) * 100.0) if gross_pnl != 0 else None

    # cap-respect: every day must honour max_trades_per_day & daily_max_loss
    per_day: Dict[str, List[SimTrade]] = defaultdict(list)
    for t in trades:
        per_day[t.day].append(t)
    respected = 0
    for day, day_trades in per_day.items():
        ok = True
        if profile.max_trades_per_day is not None and len(day_trades) > profile.max_trades_per_day:
            ok = False
        if profile.equity_usd is not None:
            cap = profile.equity_usd * profile.daily_max_loss_pct / 100.0
            if sum(x.realized_cashflow_pnl_usdc for x in day_trades) < -cap:
                ok = False
        respected += 1 if ok else 0
    cap_respect_pct = (respected / len(per_day) * 100.0) if per_day else 100.0

    return {
        "trades": n,
        "win_rate": round(win_rate, 4),
        "break_even_hit_rate": round(break_even_hit_rate, 4),
        "expectancy_per_trade": round(expectancy_per_trade, 6),
        "expectancy_per_dollar": round(expectancy_per_dollar, 6) if expectancy_per_dollar is not None else None,
        "sharpe_per_trade": round(sharpe_per_trade, 4) if sharpe_per_trade is not None else None,
        "sharpe_annualized": round(sharpe_annualized, 4) if sharpe_annualized is not None else None,
        "max_drawdown": round(max_dd, 6),
        "turnover_trades_per_day": round(turnover, 4),
        "profit_factor": (round(profit_factor, 4) if profit_factor not in (None, math.inf) else profit_factor),
        "cost_drag_pct": round(cost_drag_pct, 4) if cost_drag_pct is not None else None,
        "cap_respect_pct": round(cap_respect_pct, 2),
        "net_pnl_total": round(sum(pnls), 6),
        "gross_pnl_total": round(gross_pnl, 6),
    }


def run_backtest(path: str, profile: Optional[Profile] = None, fill_seed: int = 7) -> Dict[str, object]:
    """Read recorded JSONL at `path`, replay the spine, return the metrics dict."""
    if profile is None:
        profile = get_profile("conservative")
    source = RecordedSource(path)
    records = list(source.raw_records())
    trades = simulate(records, profile, fill_seed=fill_seed)
    metrics = compute_metrics(trades, profile)
    metrics["profile"] = profile.name
    metrics["records_read"] = len(records)
    return metrics


def format_report(metrics: Dict[str, object]) -> str:
    """Render a clear text report of the `03 §9` metrics."""
    lines = [
        "=" * 56,
        " BACKTEST REPORT (03 §9) — costs always on, no look-ahead",
        "=" * 56,
        f" profile               : {metrics.get('profile')}",
        f" records read          : {metrics.get('records_read')}",
        f" settled trades        : {metrics.get('trades')}",
        f" win rate              : {_fmt(metrics.get('win_rate'))}",
        f" break-even hit bar    : {_fmt(metrics.get('break_even_hit_rate'))}",
        f" expectancy / trade    : {_fmt(metrics.get('expectancy_per_trade'))} USDC",
        f" expectancy / $ staked : {_fmt(metrics.get('expectancy_per_dollar'))}",
        f" sharpe (per-trade)    : {_fmt(metrics.get('sharpe_per_trade'))}",
        f" sharpe (annualized)   : {_fmt(metrics.get('sharpe_annualized'))}",
        f" max drawdown          : {_fmt(metrics.get('max_drawdown'))} USDC",
        f" turnover (trades/day) : {_fmt(metrics.get('turnover_trades_per_day'))}",
        f" profit factor         : {_fmt(metrics.get('profit_factor'))}",
        f" cost drag (% gross)   : {_fmt(metrics.get('cost_drag_pct'))}",
        f" cap-respect (%)       : {_fmt(metrics.get('cap_respect_pct'))}",
        f" net P&L total         : {_fmt(metrics.get('net_pnl_total'))} USDC",
        f" gross P&L total       : {_fmt(metrics.get('gross_pnl_total'))} USDC",
        "=" * 56,
    ]
    return "\n".join(lines)


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)
