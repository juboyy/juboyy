"""ResolutionEdgeStrategy reads a watchlist.jsonl and proposes a human-gated enter.

Offline + deterministic: the watchlist is built with the scanner's HeuristicAnalyzer
(no LLM, no network) and written to a temp file injected into the strategy. Asserts
sizing within budget, empty/low-score → [], and the approval_required human-gating.
"""

from __future__ import annotations

import json

from engine.config import Profile
from engine.contracts import MarketSnapshot

from scanner.analyzer import HeuristicAnalyzer
from scanner.contracts import OutcomeCandidate
from scanner.scan import ScanParams, scan, to_jsonl

from strategies.base import StrategyContext
from strategies.resolution_edge import ResolutionEdgeStrategy


# Resolution text engineered to pass the scanner's gates: strong discretion +
# conflicting clause => high ambiguity + a true_prob nudge above the cheap price.
_AMBIGUOUS_TEXT = (
    "Resolves YES if the outcome is achieved as determined by the committee in its "
    "sole discretion, however the deadline may be extended unless circumstances change."
)


def _gate_passing_candidate(price: float = 0.08) -> OutcomeCandidate:
    return OutcomeCandidate(
        market_slug="convex-market-1",
        outcome="Yes",
        price=price,
        resolution_text=_AMBIGUOUS_TEXT,
        end_iso="2026-07-01T00:00:00Z",
        top_ask_notional_usd=500.0,
    )


def _write_watchlist(tmp_path, candidates):
    items = scan(candidates, HeuristicAnalyzer(), ScanParams())
    path = tmp_path / "watchlist.jsonl"
    path.write_text(to_jsonl(items) + ("\n" if items else ""), encoding="utf-8")
    return path, items


def _snap():
    return MarketSnapshot(ts="2026-06-23T14:00:00Z", market_slug="convex-market-1")


def _ctx(budget=10.0, mode="paper"):
    return StrategyContext(
        snapshot=_snap(), profile=Profile(), budget_usd=budget, mode=mode
    )


def test_watchlist_has_a_gate_passing_item(tmp_path):
    # sanity: the engineered candidate actually passes the scanner gates.
    _path, items = _write_watchlist(tmp_path, [_gate_passing_candidate()])
    assert len(items) == 1
    assert items[0].signal.pass_gates is True


def test_proposes_one_decision_sized_within_budget(tmp_path):
    path, _items = _write_watchlist(tmp_path, [_gate_passing_candidate(price=0.08)])
    strat = ResolutionEdgeStrategy(watchlist_path=str(path))
    decisions = strat.propose(_ctx(budget=10.0, mode="paper"))

    assert len(decisions) == 1
    dec = decisions[0]
    assert dec.action == "enter"
    assert dec.market_slug == "convex-market-1"
    assert dec.side == "Yes"
    assert dec.limit_price == 0.08
    # shares = floor(10 / 0.08) = 125 ; cost = 125 * 0.08 = 10.0 <= budget
    assert dec.shares == 125
    assert dec.size_usd <= 10.0 + 1e-9
    # paper mode auto-routes: not approval-gated.
    assert dec.approval_required is False
    assert dec.risk_verdict == "allow"


def test_live_mode_marks_approval_required(tmp_path):
    path, _ = _write_watchlist(tmp_path, [_gate_passing_candidate()])
    strat = ResolutionEdgeStrategy(watchlist_path=str(path), mode="live")
    decisions = strat.propose(_ctx(budget=10.0, mode="live"))

    assert len(decisions) == 1
    dec = decisions[0]
    assert dec.approval_required is True
    assert dec.risk_verdict == "veto"
    assert dec.risk_reason == "approval_required"
    assert "APPROVAL REQUIRED" in (dec.reason or "")


def test_empty_watchlist_returns_no_decisions(tmp_path):
    path = tmp_path / "watchlist.jsonl"
    path.write_text("", encoding="utf-8")
    strat = ResolutionEdgeStrategy(watchlist_path=str(path))
    assert strat.propose(_ctx()) == []


def test_missing_watchlist_file_returns_empty(tmp_path):
    strat = ResolutionEdgeStrategy(watchlist_path=str(tmp_path / "nope.jsonl"))
    assert strat.propose(_ctx()) == []


def test_low_score_floor_filters_out(tmp_path):
    path, items = _write_watchlist(tmp_path, [_gate_passing_candidate()])
    score = items[0].signal.convex_score
    # floor just above the only item's score => filtered out.
    strat = ResolutionEdgeStrategy(watchlist_path=str(path), min_convex_score=score + 0.01)
    assert strat.propose(_ctx()) == []


def test_non_gate_passing_lines_ignored(tmp_path):
    # A hand-written watchlist line whose signal.pass_gates is False must be skipped.
    path = tmp_path / "watchlist.jsonl"
    rec = {
        "candidate": {"market_slug": "m", "outcome": "Yes", "price": 0.05,
                      "resolution_text": "x", "end_iso": "", "top_ask_notional_usd": 1.0},
        "assessment": {"true_prob_estimate": 0.05, "ambiguity_score": 0.0,
                       "rationale": "x", "source": "heuristic"},
        "signal": {"payoff_multiple": 20.0, "edge": 0.0, "ev_per_dollar": -0.1,
                   "convex_score": 0.0, "pass_gates": False, "reasons": []},
    }
    path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    strat = ResolutionEdgeStrategy(watchlist_path=str(path))
    assert strat.propose(_ctx()) == []


def test_data_needs_is_empty_and_slow_cadence():
    strat = ResolutionEdgeStrategy()
    assert strat.data_needs() == set()
    assert strat.cadence_sec == 300.0
    assert strat.mode == "paper"
