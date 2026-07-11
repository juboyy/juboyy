"""
contracts.py — Canonical data contracts (`docs/05_DATA_CONTRACTS.md`).

Plain `@dataclass` containers for every shared object. Field names are
**normative** and match `dashboard/parser.py` verbatim where they overlap
(`clob_up_ask`, `seconds_left`, `realized_cashflow_pnl_usdc`, `loss_cap_used_pct`,
…). `None` means unknown/unavailable (never `0`). Money is USDC; prices/probs are
in [0,1]. Every top-level object carries `schema_version` (starts "1.0").

These are pure value objects: no I/O, no clock reads, no behaviour beyond
serialization helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    return d


@dataclass
class MarketSnapshot:
    """`05 §1` — raw point-in-time market state; input to the indicators."""

    ts: Optional[str] = None
    market_slug: Optional[str] = None
    seconds_left: Optional[int] = None
    clob_up_ask: Optional[float] = None
    clob_down_ask: Optional[float] = None
    clob_up_bid: Optional[float] = None
    clob_down_bid: Optional[float] = None
    gamma_up: Optional[float] = None
    gamma_down: Optional[float] = None
    min_spread: Optional[float] = None
    top_ask_notional_usd: Optional[float] = None
    top_bid_notional_usd: Optional[float] = None
    btc_price_open: Optional[float] = None
    btc_price_now: Optional[float] = None
    age_sec: Optional[int] = None
    source: str = "clob+gamma"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MarketSnapshot":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Features:
    """`05 §2` — output of `indicators.compute`."""

    ts: Optional[str] = None
    btc_move_usd: Optional[float] = None
    momentum_side: Optional[str] = None
    momentum_score: Optional[float] = None
    rv_usd: Optional[float] = None
    rv_score: Optional[float] = None
    skew_clob: Optional[float] = None
    skew_gamma: Optional[float] = None
    skew_side: Optional[str] = None
    skew_agree: Optional[bool] = None
    skew_score: Optional[float] = None
    spread_ok: Optional[bool] = None
    notional_ok: Optional[bool] = None
    liquidity_score: Optional[float] = None
    imbalance: Optional[float] = None
    imbalance_score: Optional[float] = None
    in_window: Optional[bool] = None
    time_decay_score: Optional[float] = None
    seconds_left: Optional[int] = None
    fresh: Optional[bool] = None
    process_ok: Optional[bool] = None
    dead_man_tripped: Optional[bool] = None
    health_score: Optional[float] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Signal:
    """`05 §3` — output of `signal.evaluate`; carries full scoring breakdown."""

    ts: Optional[str] = None
    market_slug: Optional[str] = None
    chosen_side: Optional[str] = None
    chosen_side_ask: Optional[float] = None
    total_score: Optional[float] = None
    enter_score_min: float = 0.60
    subscores: Dict[str, Any] = field(default_factory=dict)
    weights: Dict[str, Any] = field(default_factory=dict)
    gates: Dict[str, bool] = field(default_factory=dict)
    gates_passed: bool = False
    failed_gate: Optional[str] = None
    model_version: str = "rule-1.0"
    age_sec: Optional[int] = None
    source: str = "session_report"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Decision:
    """`05 §4` — output of `signal.decide` then `risk.apply`."""

    ts: Optional[str] = None
    market_slug: Optional[str] = None
    action: str = "skip"  # enter|hold|exit|hedge|skip
    side: Optional[str] = None
    limit_price: Optional[float] = None
    size_usd: Optional[float] = None
    shares: Optional[int] = None
    reason: Optional[str] = None
    hedge: Dict[str, Any] = field(
        default_factory=lambda: {"enabled": False, "side": None, "notional_usd": None}
    )
    risk_verdict: str = "allow"  # allow|veto|clamp
    risk_reason: Optional[str] = None
    mode: str = "dry_run"
    armed: bool = False
    signal_ref_ts: Optional[str] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Position:
    """`05 §5` — an open/attempted order and the resulting position."""

    order_id: Optional[str] = None
    ts: Optional[str] = None
    market_slug: Optional[str] = None
    side: Optional[str] = None
    entry_price: Optional[float] = None
    shares: Optional[int] = None
    cost_usdc: Optional[float] = None
    open_tx: Optional[str] = None
    mode: str = "dry_run"
    status: str = "open"  # open|closed|settled|failed
    stop_loss_price: Optional[float] = None
    seconds_left_at_entry: Optional[int] = None
    profile: Optional[str] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# `Order` is the same shape as a freshly opened `Position` per 05 §5.
Order = Position


@dataclass
class TradeResult:
    """`05 §6` — closed/settled trade; canonical record for `btc5m_events.jsonl`.

    Field names match `dashboard/parser.py::_normalize_trade`.
    """

    ts: Optional[str] = None
    profile: Optional[str] = None
    result: Optional[str] = None  # win|loss|breakeven
    side: Optional[str] = None
    market_slug: Optional[str] = None
    entry_price: Optional[float] = None
    shares: Optional[int] = None
    cost_usdc: Optional[float] = None
    open_tx: Optional[str] = None
    close_reason: Optional[str] = None  # settlement|stop_loss|time_exit|kill
    close_success: Optional[bool] = None
    close_status: Optional[str] = None
    close_skipped: Optional[bool] = None
    close_tx: Optional[str] = None
    realized_cashflow_pnl_usdc: Optional[float] = None
    btc_move_usd: Optional[float] = None
    skew: Optional[float] = None
    seconds_left_at_entry: Optional[int] = None
    threshold_price: Optional[float] = None
    stake_usd: Optional[float] = None
    fees_usdc: Optional[float] = None
    slippage_usdc: Optional[float] = None
    gas_usdc: Optional[float] = None
    mode: str = "dry_run"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskState:
    """`05 §7` — live risk/cap state. Cap/KPI names match `parser.summary()`."""

    ts: Optional[str] = None
    profile: Optional[str] = None
    mode: str = "dry_run"
    armed: bool = False
    killed: bool = False
    running: bool = True
    pnl_today: float = 0.0
    pnl_total: float = 0.0
    trades_today: int = 0
    trades_total: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: Optional[float] = None
    max_trades_per_day: Optional[int] = None
    trades_cap_used_pct: Optional[float] = None
    daily_loss_cap_usd: Optional[float] = None
    daily_loss_cap_pct: Optional[float] = None
    loss_cap_used_pct: Optional[float] = None
    best_trade: Optional[float] = None
    worst_trade: Optional[float] = None
    open_position: Optional[Dict[str, Any]] = None
    dead_man_tripped: bool = False
    # age of the latest snapshot in seconds; drives the dead-man check.
    age_sec: Optional[int] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Account:
    """`05 §8` — operator account/equity state + equity curve."""

    ts: Optional[str] = None
    equity_usd: Optional[float] = None
    funder_address_masked: Optional[str] = None
    signature_type: Optional[int] = None
    currency: str = "USDC"
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BotStatus:
    """`05 §9` — process/session status."""

    running: bool = False
    state: str = "PARADO"  # RODANDO|PARADO|STALE
    pid: Optional[int] = None
    profile: Optional[str] = None
    mode: str = "dry_run"
    armed: bool = False
    killed: bool = False
    started_at: Optional[str] = None
    uptime_sec: Optional[int] = None
    params: Dict[str, Any] = field(default_factory=dict)
    log_path: Optional[str] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
