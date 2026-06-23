"""Supervisor.tick: propose -> approve -> route to PAPER adapter -> event recorded;
and a global kill blocks routing. All offline, deterministic, injected clock +
temp runtime dir, no network.
"""

import json
from typing import Dict, List

from engine.config import Profile
from engine.contracts import Decision, MarketSnapshot

from portfolio.allocator import CapitalAllocator
from portfolio.risk_portfolio import PortfolioRisk
from runtime_paths import JsonlLogger, RuntimePaths
from strategies.base import Strategy, StrategyContext
from supervisor.runner import Supervisor


class _OneEnterStrategy(Strategy):
    """Deterministic stub that proposes exactly one well-formed enter Decision."""

    name = "stub_enter"
    cadence_sec = 5.0
    mode = "paper"

    def propose(self, ctx: StrategyContext) -> List[Decision]:
        return [
            Decision(
                action="enter",
                side="up",
                market_slug="btc-5m",
                limit_price=0.75,
                size_usd=5.0,
                shares=6,
            )
        ]


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(ts="2026-06-23T14:00:00Z", market_slug="btc-5m", seconds_left=120)


def _data_provider(strategy, now) -> Dict:
    return {"snapshot": _snapshot(), "history": []}


def _make_supervisor(tmp_path, **kw):
    paths = RuntimePaths.under(str(tmp_path))
    logger = JsonlLogger(paths)
    risk = kw.pop("risk", PortfolioRisk(global_daily_loss_cap_usd=100.0))
    alloc = kw.pop("alloc", CapitalAllocator(100.0, {"stub_enter": 1.0}))
    sup = Supervisor(
        [_OneEnterStrategy()],
        portfolio_risk=risk,
        allocator=alloc,
        profile=Profile(),
        logger=logger,
        clock=lambda: 1000.0,
        **kw,
    )
    return sup, paths, logger


def _read_jsonl(path) -> List[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_tick_approves_routes_to_paper_and_records_event(tmp_path):
    sup, paths, logger = _make_supervisor(tmp_path)

    # Default adapter must be the offline paper adapter (dry-run, not armed).
    assert sup.adapter.mode == "dry_run"
    assert sup.adapter.is_live() is False

    report = sup.tick(now=1000.0, data=_data_provider)
    logger.close()

    assert report.ran == ["stub_enter"]
    assert report.approved_count == 1
    assert report.routed_count == 1
    outcome = report.outcomes[0]
    assert outcome.approved is True
    assert outcome.routed is True
    assert outcome.order_id is not None
    assert outcome.order_id.startswith("ord_paper_")

    events = _read_jsonl(paths.events)
    assert any(e.get("kind") == "decision" and e.get("routed") is True for e in events)
    orders = _read_jsonl(paths.orders)
    assert len(orders) == 1
    assert orders[0]["mode"] == "dry_run"
    assert orders[0]["strategy"] == "stub_enter"


def test_global_kill_blocks_routing(tmp_path):
    risk = PortfolioRisk(global_daily_loss_cap_usd=100.0)
    risk.kill("operator")
    sup, paths, logger = _make_supervisor(tmp_path, risk=risk)

    report = sup.tick(now=1000.0, data=_data_provider)
    logger.close()

    assert report.killed is True
    assert report.approved_count == 0
    assert report.routed_count == 0
    outcome = report.outcomes[0]
    assert outcome.approved is False
    assert outcome.reason == "global_kill"

    orders = _read_jsonl(paths.orders)
    assert orders == []  # nothing routed under kill


def test_cadence_skips_when_not_due(tmp_path):
    sup, paths, logger = _make_supervisor(tmp_path)

    r1 = sup.tick(now=1000.0, data=_data_provider)
    assert r1.ran == ["stub_enter"]

    # 2 seconds later, cadence (5s) not yet elapsed => skipped.
    r2 = sup.tick(now=1002.0, data=_data_provider)
    logger.close()
    assert r2.ran == []
    assert r2.skipped_cadence == ["stub_enter"]


def test_run_loop_stops_on_event_and_uses_injected_clock(tmp_path):
    sup, paths, logger = _make_supervisor(tmp_path)

    class _Stop:
        def __init__(self, after):
            self.after = after
            self.n = 0

        def is_set(self):
            self.n += 1
            return self.n > self.after

    ticks = sup.run(
        _Stop(after=3),
        _data_provider,
        clock=lambda: 2000.0,
        sleep=lambda s: None,
    )
    logger.close()
    assert ticks == 3
