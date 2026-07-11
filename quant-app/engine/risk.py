"""
risk.py — Risk Manager (`03 §6`, `05 RiskState`).

Pure functions over a `RiskState` + `Profile`. Enforces:
  - daily caps: `max_trades_per_day`, `daily_max_loss_pct` (via `daily_loss_cap_usd`)
  - kill flag (blocks new entries, forces exits)
  - dead-man: `age_sec > dead_man_sec` or `not running`
  - no conflicting open position (a different-side / different-market open position)

`apply(state, profile, candidate_side, candidate_market)` returns an
`Allowance(allowed, reason)`. `apply_decision(decision, state, profile)` rewrites a
`Decision` in place per the spec overlays (veto new entries; force exits on kill).

No I/O, no clock reads: `age_sec`/`running` are carried on the `RiskState`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .contracts import Decision, RiskState
from .config import Profile


@dataclass(frozen=True)
class Allowance:
    allowed: bool
    reason: Optional[str] = None


def _dead_man_tripped(state: RiskState, profile: Profile) -> bool:
    if not state.running:
        return True
    if state.age_sec is not None and state.age_sec > profile.dead_man_sec:
        return True
    return bool(state.dead_man_tripped)


def apply(
    state: RiskState,
    profile: Profile,
    candidate_side: Optional[str] = None,
    candidate_market: Optional[str] = None,
) -> Allowance:
    """Decide whether a NEW entry is permitted. Order of checks is the audit order.

    Returns Allowance(allowed, reason). `reason` uses the `05` risk_reason
    vocabulary: killed | not_running | dead_man | stale | max_trades |
    daily_loss_cap | conflicting_position | not_armed.
    """
    if state.killed:
        return Allowance(False, "killed")

    if not state.running:
        return Allowance(False, "not_running")

    if _dead_man_tripped(state, profile):
        return Allowance(False, "dead_man")

    # daily trade-count cap
    cap_trades = profile.max_trades_per_day
    if cap_trades is not None and state.trades_today >= cap_trades:
        return Allowance(False, "max_trades")

    # daily loss cap (USD). Prefer an explicit cap on the state; else derive from
    # equity * pct. If neither is available the cap cannot bind.
    loss_cap = state.daily_loss_cap_usd
    if loss_cap is None and profile.equity_usd is not None:
        loss_cap = profile.equity_usd * profile.daily_max_loss_pct / 100.0
    if loss_cap is not None and state.pnl_today <= -abs(loss_cap):
        return Allowance(False, "daily_loss_cap")

    # no conflicting open position
    op = state.open_position
    if op:
        op_side = op.get("side") if isinstance(op, dict) else getattr(op, "side", None)
        op_market = (
            op.get("market_slug") if isinstance(op, dict) else getattr(op, "market_slug", None)
        )
        if candidate_market is not None and op_market is not None and op_market != candidate_market:
            return Allowance(False, "conflicting_position")
        if candidate_side is not None and op_side is not None and op_side != candidate_side:
            return Allowance(False, "conflicting_position")
        # same market + same side already open: still a conflict (no doubling here)
        return Allowance(False, "conflicting_position")

    return Allowance(True, None)


def apply_decision(decision: Decision, state: RiskState, profile: Profile) -> Decision:
    """Post-process a `Decision` through the Risk Manager (`02` spine arrow 4).

    - kill flag: force exit-all / block enter.
    - for `enter`: re-run `apply`; veto → action becomes `skip` with risk_reason.
    - mirrors armed/mode onto the decision.
    Mutates and returns the same `Decision`.
    """
    decision.mode = state.mode
    decision.armed = state.armed

    if state.killed:
        # kill forces exits on any open position, blocks new entries
        if state.open_position:
            decision.action = "exit"
            decision.reason = "kill"
        else:
            decision.action = "skip"
            decision.reason = "killed"
        decision.risk_verdict = "veto"
        decision.risk_reason = "killed"
        return decision

    if decision.action == "enter":
        allow = apply(state, profile, candidate_side=decision.side,
                      candidate_market=decision.market_slug)
        if not allow.allowed:
            decision.action = "skip"
            decision.risk_verdict = "veto"
            decision.risk_reason = allow.reason
            decision.reason = allow.reason
        else:
            decision.risk_verdict = "allow"
            decision.risk_reason = None
    else:
        # non-enter decisions (hold/exit/skip) pass through; record allow.
        decision.risk_verdict = "allow"
        decision.risk_reason = None

    return decision
