"""Deterministic paper (dry-run) execution adapter — the DEFAULT.

Fully offline, standard-library only, **never** touches keys. Produces
deterministic simulated fills using the engine cost model from ``03 §8``
(slippage / gas / fees) and a seeded RNG for any fill jitter, so identical inputs
yield identical outputs (02 §2, 03 §9).

The canonical net P&L field is ``realized_cashflow_pnl_usdc`` (03 §8):

    realized_cashflow_pnl_usdc =
        settlement/exit cashflow − cost basis − slippage − gas − fees
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .adapter import (
    SCHEMA_VERSION,
    Balance,
    ExecutionAdapter,
    Order,
    Position,
    Quote,
    TradeResult,
)


# ---------------------------------------------------------------------------
# Cost model (03 §8) — defaults match the spec.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CostModel:
    """Engine cost model (03 §8). All defaults are the spec defaults."""

    tick: float = 0.01
    slip_ticks: float = 1.0  # worse fill than quoted ask (cross half-spread conservatively)
    gas_usdc: float = 0.02  # per on-chain action (open AND close are separate actions)
    fee_bps: float = 0.0  # Polymarket CLOB fee schedule on notional (default 0)

    def slippage_usdc(self, shares: int) -> float:
        """`shares × slip_ticks × tick` (03 §8)."""
        return shares * self.slip_ticks * self.tick

    def fees_usdc(self, notional_usdc: float) -> float:
        """`fee_bps` applied to notional (03 §8)."""
        return notional_usdc * (self.fee_bps / 10_000.0)


def _now_iso(ts: Optional[float] = None) -> str:
    t = time.time() if ts is None else ts
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _round6(x: float) -> float:
    """USDC is 6dp-tolerated (05 §0); round for stable, comparable records."""
    return round(x + 0.0, 6)


class PaperExecutionAdapter(ExecutionAdapter):
    """Deterministic simulated-fill adapter. Offline, no keys, dry-run only.

    Determinism: a single seeded :class:`random.Random` drives any jitter; the
    same ``seed`` + same decisions ⇒ byte-identical results. By default jitter is
    **off** (``jitter_ticks=0``) so paper P&L is a pure function of inputs and the
    cost model, matching the backtest contract (03 §9).
    """

    mode = "dry_run"
    armed = False

    def __init__(
        self,
        *,
        profile: str = "conservative",
        cost_model: Optional[CostModel] = None,
        stop_loss_pct: float = 0.25,
        equity_usd: Optional[float] = 100.0,
        seed: int = 1337,
        jitter_ticks: int = 0,
        stake_usd: float = 5.0,
        threshold_price: float = 0.70,
    ) -> None:
        self.profile = profile
        self.cost = cost_model or CostModel()
        self.stop_loss_pct = stop_loss_pct
        self.equity_usd = equity_usd
        self.stake_usd = stake_usd
        self.threshold_price = threshold_price
        self.jitter_ticks = jitter_ticks
        self._seed = seed
        self._rng = random.Random(seed)
        self._order_counter = 0
        # Cache decision context per order_id so close_position can attach
        # btc_move/skew/seconds_left_at_entry to the canonical TradeResult.
        self._ctx: dict[str, dict[str, Any]] = {}

    # -- helpers ------------------------------------------------------------
    def reset(self) -> None:
        """Reset RNG + counters for reproducible test runs."""
        self._rng = random.Random(self._seed)
        self._order_counter = 0
        self._ctx.clear()

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"ord_paper_{self._order_counter:06d}"

    def _jitter(self) -> float:
        """Deterministic, seeded fill jitter in USDC-price units (default 0)."""
        if self.jitter_ticks <= 0:
            return 0.0
        # Symmetric integer tick jitter, seeded ⇒ reproducible.
        ticks = self._rng.randint(-self.jitter_ticks, self.jitter_ticks)
        return ticks * self.cost.tick

    @staticmethod
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    # -- ExecutionAdapter ---------------------------------------------------
    def quote(self, market: Any) -> Quote:
        """Build a :class:`Quote` from a slug or a ``MarketSnapshot``-like object."""
        if isinstance(market, str):
            return Quote(
                schema_version=SCHEMA_VERSION,
                ts=_now_iso(),
                market_slug=market,
                source="paper",
            )
        return Quote(
            schema_version=SCHEMA_VERSION,
            ts=self._get(market, "ts", _now_iso()),
            market_slug=self._get(market, "market_slug", "unknown"),
            seconds_left=self._get(market, "seconds_left"),
            clob_up_ask=self._get(market, "clob_up_ask"),
            clob_down_ask=self._get(market, "clob_down_ask"),
            clob_up_bid=self._get(market, "clob_up_bid"),
            clob_down_bid=self._get(market, "clob_down_bid"),
            min_spread=self._get(market, "min_spread"),
            top_ask_notional_usd=self._get(market, "top_ask_notional_usd"),
            top_bid_notional_usd=self._get(market, "top_bid_notional_usd"),
            age_sec=self._get(market, "age_sec"),
            source="paper",
        )

    def open_position(self, decision: Any) -> Order:
        """Simulate an ``enter`` Decision → :class:`Order`/:class:`Position` (05 §5)."""
        action = self._get(decision, "action", "enter")
        if action != "enter":
            raise ValueError(f"open_position expects action='enter', got {action!r}")

        side = self._get(decision, "side")
        limit_price = float(self._get(decision, "limit_price"))
        shares = int(self._get(decision, "shares"))
        market_slug = self._get(decision, "market_slug", "unknown")
        seconds_left = self._get(decision, "signal_seconds_left",
                                 self._get(decision, "seconds_left_at_entry"))

        # Deterministic fill: ask + seeded jitter (default 0), clamped to [0,1].
        fill_price = min(1.0, max(0.0, limit_price + self._jitter()))
        cost_basis = _round6(shares * fill_price)

        order_id = self._next_order_id()
        order = Order(
            schema_version=SCHEMA_VERSION,
            order_id=order_id,
            ts=_now_iso(),
            market_slug=market_slug,
            side=side,
            entry_price=_round6(fill_price),
            shares=shares,
            cost_usdc=cost_basis,
            open_tx=None,  # dry-run: no on-chain tx (05 §5)
            mode="dry_run",
            status="open",
            stop_loss_price=_round6(fill_price * (1.0 - self.stop_loss_pct)),
            seconds_left_at_entry=seconds_left,
            profile=self.profile,
        )
        # Stash decision context for the eventual close record.
        self._ctx[order_id] = {
            "btc_move_usd": self._get(decision, "btc_move_usd"),
            "skew": self._get(decision, "skew"),
            "stake_usd": self._get(decision, "size_usd", self.stake_usd),
            "threshold_price": self._get(decision, "threshold_price", self.threshold_price),
        }
        return order

    def close_position(
        self,
        position: Order,
        *,
        outcome: Optional[str] = None,
        exit_price: Optional[float] = None,
        close_reason: str = "settlement",
        close_skipped: bool = False,
    ) -> TradeResult:
        """Close/settle ``position`` → canonical :class:`TradeResult` (05 §6, 03 §8).

        Cashflow:
          - ``close_reason='settlement'``: binary payout — ``outcome='win'`` pays
            ``$1 × shares``; a loss pays ``$0``. (Default outcome inferred from
            whether the side is in the money is the caller's job; we accept it
            explicitly for determinism.)
          - exit (``stop_loss`` / ``time_exit`` / ``kill``): cashflow =
            ``shares × exit_price`` (top-bid), unless ``close_skipped`` (held to
            settlement because exit liquidity was absent — 03 §6).

        Net P&L (canonical):
            cashflow − cost_basis − slippage − gas − fees
        """
        ctx = self._ctx.get(position.order_id, {})
        shares = int(position.shares)
        cost_basis = float(position.cost_usdc)

        # --- determine gross cashflow from the close ---
        if close_skipped or close_reason == "settlement":
            # Held to settlement (or natural settlement): binary outcome.
            won = (outcome == "win")
            cashflow = float(shares) if won else 0.0
            close_status = "settled"
            # Only one on-chain action effectively occurred (open); a skipped
            # close incurs no close-side gas. Natural settlement: settle action.
            close_actions = 0 if close_skipped else 1
            close_tx = None  # dry-run
        else:
            # Active exit at top-bid (stop_loss | time_exit | kill).
            px = float(exit_price if exit_price is not None else position.entry_price)
            px = min(1.0, max(0.0, px))
            cashflow = _round6(shares * px)
            close_status = "closed"
            close_actions = 1
            close_tx = None  # dry-run

        # --- costs (03 §8) ---
        # Slippage applies on entry; on an active exit it applies again.
        slip = self.cost.slippage_usdc(shares)
        if close_status == "closed":
            slip += self.cost.slippage_usdc(shares)
        # Gas: open action + (close action if one occurred).
        gas = self.cost.gas_usdc * (1 + close_actions)
        # Fees on notional (entry notional + exit notional if exited).
        notional = cost_basis + (cashflow if close_status == "closed" else 0.0)
        fees = self.cost.fees_usdc(notional)

        slip = _round6(slip)
        gas = _round6(gas)
        fees = _round6(fees)

        net_pnl = _round6(cashflow - cost_basis - slip - gas - fees)

        if net_pnl > 0:
            result = "win"
        elif net_pnl < 0:
            result = "loss"
        else:
            result = "breakeven"

        tr = TradeResult(
            schema_version=SCHEMA_VERSION,
            ts=_now_iso(),
            profile=position.profile,
            result=result,
            side=position.side,
            market_slug=position.market_slug,
            entry_price=position.entry_price,
            shares=shares,
            cost_usdc=cost_basis,
            open_tx=position.open_tx,
            close_reason=close_reason,
            close_success=not close_skipped,
            close_status=close_status,
            close_skipped=close_skipped,
            close_tx=close_tx,
            realized_cashflow_pnl_usdc=net_pnl,
            btc_move_usd=ctx.get("btc_move_usd"),
            skew=ctx.get("skew"),
            seconds_left_at_entry=position.seconds_left_at_entry,
            threshold_price=ctx.get("threshold_price", self.threshold_price),
            stake_usd=ctx.get("stake_usd", self.stake_usd),
            fees_usdc=fees,
            slippage_usdc=slip,
            gas_usdc=gas,
            mode="dry_run",
        )
        self._ctx.pop(position.order_id, None)
        return tr

    def cancel(self, order_id: str) -> bool:
        """Cancel a simulated working order. Always succeeds in paper mode."""
        self._ctx.pop(order_id, None)
        return True

    def balance(self) -> Balance:
        """Simulated equity. No funder address (no wallet in paper mode)."""
        return Balance(
            schema_version=SCHEMA_VERSION,
            ts=_now_iso(),
            equity_usd=self.equity_usd,
            funder_address_masked=None,
            signature_type=None,
            currency="USDC",
        )
