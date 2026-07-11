"""Abstract execution-adapter interface + canonical data shapes.

The shapes here are the ``05_DATA_CONTRACTS.md`` ``Order`` / ``Position`` /
``TradeResult`` records, expressed as stdlib dataclasses. Field names are
**normative** and match ``dashboard/parser.py::_normalize_trade``.

This module is standard-library only and holds no keys. Concrete adapters
(:mod:`crypto.paper`, :mod:`crypto.polymarket`) implement
:class:`ExecutionAdapter`.
"""

from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = "1.0"

# Strategy-side enums (05 §0).
Side = str  # "up" | "down"
Mode = str  # "dry_run" | "live"
Profile = str  # "conservative" | "aggressive"


# ---------------------------------------------------------------------------
# Data contracts (05 §1, §5, §6)
# ---------------------------------------------------------------------------
@dataclass
class Quote:
    """Snapshot-derived quote for one market (subset of ``MarketSnapshot``, 05 §1)."""

    schema_version: str
    ts: str
    market_slug: str
    seconds_left: Optional[int] = None
    clob_up_ask: Optional[float] = None
    clob_down_ask: Optional[float] = None
    clob_up_bid: Optional[float] = None
    clob_down_bid: Optional[float] = None
    min_spread: Optional[float] = None
    top_ask_notional_usd: Optional[float] = None
    top_bid_notional_usd: Optional[float] = None
    age_sec: Optional[int] = None
    source: str = "paper"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Order:
    """Open or attempted order + resulting position (05 §5).

    ``status`` ∈ {"open","closed","settled","failed"}. ``open_tx`` is ``None`` in
    dry-run. Used both as the ``Order`` and ``Position`` contract.
    """

    schema_version: str
    order_id: str
    ts: str
    market_slug: str
    side: Side
    entry_price: float
    shares: int
    cost_usdc: float
    open_tx: Optional[str]
    mode: Mode
    status: str
    stop_loss_price: float
    seconds_left_at_entry: Optional[int]
    profile: Profile

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# A Position is structurally identical to an Order in this contract (05 §5).
Position = Order


@dataclass
class TradeResult:
    """Closed/settled trade — canonical record (05 §6).

    ``realized_cashflow_pnl_usdc`` is the **net** P&L after costs (03 §8):
    ``settlement/exit cashflow − cost basis − slippage − gas − fees``. This is the
    field appended to ``btc5m_events.jsonl`` and read by the dashboard.
    """

    schema_version: str
    ts: str
    profile: Profile
    result: str  # "win" | "loss" | "breakeven"
    side: Side
    market_slug: str
    entry_price: float
    shares: int
    cost_usdc: float
    open_tx: Optional[str]
    close_reason: str  # settlement | stop_loss | time_exit | kill
    close_success: bool
    close_status: str  # "settled" | "closed" | "failed"
    close_skipped: bool
    close_tx: Optional[str]
    realized_cashflow_pnl_usdc: float
    btc_move_usd: Optional[float]
    skew: Optional[float]
    seconds_left_at_entry: Optional[int]
    threshold_price: Optional[float]
    stake_usd: Optional[float]
    fees_usdc: float
    slippage_usdc: float
    gas_usdc: float
    mode: Mode

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Balance:
    """Operator account/equity snapshot (05 §8). Never contains the private key."""

    schema_version: str
    ts: str
    equity_usd: Optional[float]
    funder_address_masked: Optional[str]
    signature_type: Optional[int]
    currency: str = "USDC"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Abstract interface (02 §2: execution.act is the only side-effecting boundary)
# ---------------------------------------------------------------------------
class ExecutionAdapter(abc.ABC):
    """Abstract execution adapter.

    Concrete implementations: :class:`crypto.paper.PaperExecutionAdapter` (default,
    offline, no keys) and :class:`crypto.polymarket.PolymarketExecutionAdapter`
    (live, gated). The adapter is the *only* component that may hold key material.
    """

    #: Subclasses set these; the base interface is mode-aware so callers can
    #: assert dry-run vs live without touching implementation details.
    mode: Mode = "dry_run"
    armed: bool = False

    @abc.abstractmethod
    def quote(self, market: Any) -> Quote:
        """Return a :class:`Quote` for ``market`` (a slug or ``MarketSnapshot``)."""

    @abc.abstractmethod
    def open_position(self, decision: Any) -> Order:
        """Act on an ``enter`` :class:`Decision` (05 §4) → :class:`Order`/:class:`Position`."""

    @abc.abstractmethod
    def close_position(self, position: Order) -> TradeResult:
        """Close/settle ``position`` → canonical :class:`TradeResult` (05 §6)."""

    @abc.abstractmethod
    def cancel(self, order_id: str) -> bool:
        """Best-effort cancel of a working order. Returns True if cancelled."""

    @abc.abstractmethod
    def balance(self) -> Balance:
        """Return account/equity state (05 §8). Never returns key material."""

    # ---- shared, non-abstract helpers -------------------------------------
    def is_live(self) -> bool:
        """True only when this adapter is configured for *live* armed execution."""
        return self.mode == "live" and bool(self.armed)
