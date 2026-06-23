"""supervisor/runner.py — the multi-strategy scheduler + router.

Composition:
  * a list of enabled :class:`~strategies.base.Strategy` instances,
  * a :class:`~portfolio.risk_portfolio.PortfolioRisk` veto layer,
  * a :class:`~portfolio.allocator.CapitalAllocator`,
  * a single execution adapter from :func:`crypto.factory.get_adapter`
    (Paper / dry-run by default),
  * a :class:`~runtime_paths.JsonlLogger` for the unified runtime log,
  * a :class:`~crypto.safety.DeadMansSwitch` heartbeat and a
    :class:`~crypto.safety.KillSwitch` global kill.

:meth:`tick` is pure-ish and deterministic given its inputs (clock value + a
``data`` provider): for each strategy whose cadence is due it builds a
:class:`StrategyContext`, calls ``propose``, runs each decision through
``PortfolioRisk.approve`` + the allocator budget, routes approved entries to the
adapter (paper), logs an event per decision, and returns a structured
:class:`TickReport`. :meth:`run` loops :meth:`tick` on an injectable clock.

No LLM, no network on the default (paper) path; no key material handled here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from crypto.factory import get_adapter
from crypto.safety import DeadMansSwitch, KillSwitch
from engine.config import Profile
from engine.contracts import Decision, MarketSnapshot

from portfolio.allocator import CapitalAllocator
from portfolio.risk_portfolio import PortfolioRisk, PortfolioState
from runtime_paths import JsonlLogger, RuntimePaths
from strategies.base import Strategy, StrategyContext


def _utc_iso(ts: Optional[float] = None) -> str:
    t = time.time() if ts is None else ts
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


@dataclass
class DecisionOutcome:
    """What happened to one proposed decision in a tick."""

    strategy: str
    action: str
    approved: bool
    reason: Optional[str] = None
    budget_usd: float = 0.0
    order_id: Optional[str] = None
    routed: bool = False


@dataclass
class TickReport:
    """Structured result of one :meth:`Supervisor.tick`."""

    now: float
    ran: List[str] = field(default_factory=list)        # strategies whose cadence was due
    skipped_cadence: List[str] = field(default_factory=list)
    outcomes: List[DecisionOutcome] = field(default_factory=list)
    killed: bool = False

    @property
    def routed_count(self) -> int:
        return sum(1 for o in self.outcomes if o.routed)

    @property
    def approved_count(self) -> int:
        return sum(1 for o in self.outcomes if o.approved)


# A data provider returns the per-tick market data for a strategy. It is injected
# so tests stay offline/deterministic.
DataProvider = Callable[[Strategy, float], Dict[str, Any]]


class Supervisor:
    """Schedule strategies, gate them through portfolio risk, route to the adapter."""

    def __init__(
        self,
        strategies: Sequence[Strategy],
        *,
        portfolio_risk: PortfolioRisk,
        allocator: CapitalAllocator,
        profile: Optional[Profile] = None,
        runtime_root: Optional[str] = None,
        mode: str = "paper",
        armed: bool = False,
        adapter: Optional[Any] = None,
        logger: Optional[JsonlLogger] = None,
        dead_man: Optional[DeadMansSwitch] = None,
        kill_switch: Optional[KillSwitch] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.strategies = list(strategies)
        self.risk = portfolio_risk
        self.allocator = allocator
        self.profile = profile or Profile()
        self.mode = mode
        self.armed = armed

        # Paper by default: get_adapter only goes live on (mode="live", armed=True).
        # Map the runtime word "paper" → the adapter's "dry_run" mode.
        adapter_mode = "live" if mode == "live" else "dry_run"
        self.adapter = adapter if adapter is not None else get_adapter(
            mode=adapter_mode, armed=armed, profile=self.profile.name
        )

        paths = RuntimePaths.under(runtime_root) if runtime_root is not None else RuntimePaths.under()
        self.logger = logger if logger is not None else JsonlLogger(paths)

        self.dead_man = dead_man if dead_man is not None else DeadMansSwitch()
        self.kill = kill_switch if kill_switch is not None else KillSwitch()
        self._clock = clock or time.time

        # Live portfolio accounting the veto layer reads.
        self.state = PortfolioState()
        # Per-strategy last-run wall time (for cadence scheduling).
        self._last_run: Dict[str, float] = {}

    # -- scheduling ---------------------------------------------------------
    def _is_due(self, strategy: Strategy, now: float) -> bool:
        last = self._last_run.get(strategy.name)
        if last is None:
            return True
        return (now - last) >= float(strategy.cadence_sec)

    def _build_context(
        self, strategy: Strategy, data: Dict[str, Any]
    ) -> StrategyContext:
        snapshot = data.get("snapshot")
        if not isinstance(snapshot, MarketSnapshot):
            raise ValueError(
                f"data provider for {strategy.name!r} must supply a MarketSnapshot under 'snapshot'"
            )
        return StrategyContext(
            snapshot=snapshot,
            profile=data.get("profile", self.profile),
            budget_usd=self.allocator.budget_for(strategy.name),
            mode=strategy.mode,
            history=data.get("history", []),
            features=data.get("features"),
            open_position=data.get("open_position"),
            kill_flag=self.kill.killed or self.risk.killed,
            btc_spot=data.get("btc_spot"),
        )

    # -- routing ------------------------------------------------------------
    def _route(self, strategy: Strategy, decision: Decision) -> Optional[str]:
        """Route an approved entry to the (paper) adapter; returns order_id or None."""
        if decision.action != "enter":
            # Exits/holds/hedges are recorded but not opened as new positions here
            # (PHASE 0 routes entries only; close handling lands in a later phase).
            return None
        if decision.shares is None or decision.limit_price is None:
            return None
        order = self.adapter.open_position(decision)
        # Track exposure so the concurrent-exposure cap binds across ticks.
        self.state.open_exposure_usd += float(decision.size_usd or 0.0)
        return getattr(order, "order_id", None)

    # -- one tick -----------------------------------------------------------
    def tick(self, now: Optional[float] = None, data: Optional[DataProvider] = None) -> TickReport:
        """Run one scheduling tick.

        ``now`` is the current wall time (injectable). ``data`` is a callable
        ``(strategy, now) -> dict`` returning that strategy's market data (must
        include a ``MarketSnapshot`` under ``"snapshot"``).
        """
        if now is None:
            now = self._clock()
        if data is None:
            raise ValueError("tick requires a data provider callable")

        self.dead_man.heartbeat(now)
        report = TickReport(now=now, killed=self.kill.killed or self.risk.killed)

        for strategy in self.strategies:
            if not self._is_due(strategy, now):
                report.skipped_cadence.append(strategy.name)
                continue

            self._last_run[strategy.name] = now
            report.ran.append(strategy.name)

            ctx = self._build_context(strategy, data(strategy, now))
            decisions = strategy.propose(ctx)

            for decision in decisions:
                allowance = self.risk.approve(strategy.name, decision, self.state)
                outcome = DecisionOutcome(
                    strategy=strategy.name,
                    action=getattr(decision, "action", "skip"),
                    approved=allowance.allowed,
                    reason=allowance.reason,
                    budget_usd=ctx.budget_usd,
                )

                if allowance.allowed:
                    order_id = self._route(strategy, decision)
                    outcome.order_id = order_id
                    outcome.routed = order_id is not None
                    if order_id is not None:
                        self.logger.order(
                            {
                                "ts": _utc_iso(now),
                                "strategy": strategy.name,
                                "order_id": order_id,
                                "action": decision.action,
                                "side": decision.side,
                                "size_usd": decision.size_usd,
                                "mode": self.adapter.mode,
                            }
                        )

                report.outcomes.append(outcome)
                self.logger.event(
                    {
                        "ts": _utc_iso(now),
                        "kind": "decision",
                        "strategy": strategy.name,
                        "action": outcome.action,
                        "approved": outcome.approved,
                        "reason": outcome.reason,
                        "routed": outcome.routed,
                        "order_id": outcome.order_id,
                        "budget_usd": outcome.budget_usd,
                    }
                )

        # Heartbeat / equity sample for liveness + the dashboard.
        self.logger.equity_sample(
            {
                "ts": _utc_iso(now),
                "open_exposure_usd": self.state.open_exposure_usd,
                "pnl_today": self.state.pnl_today,
                "dead_man_age_sec": self.dead_man.age_sec(now),
                "killed": report.killed,
            }
        )
        return report

    # -- the loop -----------------------------------------------------------
    def run(
        self,
        stop_event: Any,
        data: DataProvider,
        *,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        poll_sec: float = 1.0,
    ) -> int:
        """Loop :meth:`tick` until ``stop_event.is_set()`` or the kill fires.

        ``clock`` and ``sleep`` are injectable so tests drive the loop without
        real time. Returns the number of ticks executed.
        """
        clk = clock or self._clock
        slp = sleep or time.sleep
        ticks = 0
        while not stop_event.is_set():
            now = clk()
            self.dead_man.heartbeat(now)
            self.tick(now=now, data=data)
            ticks += 1
            if self.kill.killed or self.risk.killed:
                self.logger.command(
                    {"ts": _utc_iso(now), "kind": "kill", "reason": getattr(self.kill, "reason", None)}
                )
                break
            slp(poll_sec)
        return ticks
