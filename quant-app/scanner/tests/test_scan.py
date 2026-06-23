"""scan(): only gate-passers appear, ranked correctly; a high-payoff zero-edge
candidate is excluded (anti-longshot-trap at the pipeline level)."""

from __future__ import annotations

import json

from scanner.contracts import OutcomeCandidate
from scanner.scan import ScanParams, scan, to_jsonl
from scanner.tests.fixtures import FakeAnalyzer


def _cand(slug, price, liq=500.0):
    return OutcomeCandidate(
        market_slug=slug,
        outcome="Yes",
        price=price,
        resolution_text="irrelevant — analyzer is injected",
        end_iso="2026-12-31T00:00:00Z",
        top_ask_notional_usd=liq,
    )


def test_zero_edge_high_payoff_excluded():
    # Very cheap (huge 1/price payoff) but true_prob == price => no edge.
    cand = _cand("trap", 0.02)
    analyzer = FakeAnalyzer({"trap": (0.02, 0.9, "no edge")})
    items = scan([cand], analyzer)
    assert items == []


def test_only_gate_passers_appear():
    passing = _cand("good", 0.05)
    # Edge but no ambiguity => ambiguity gate fails.
    no_amb = _cand("noamb", 0.05)
    # Edge + ambiguity but illiquid => liquidity gate fails.
    illiquid = _cand("illiquid", 0.05, liq=10.0)
    # Edge too small => edge gate fails.
    tiny_edge = _cand("tiny", 0.05)

    analyzer = FakeAnalyzer(
        {
            "good": (0.30, 0.8, "real edge"),
            "noamb": (0.30, 0.0, "edge no ambiguity"),
            "illiquid": (0.30, 0.8, "edge but illiquid"),
            "tiny": (0.10, 0.8, "edge below min"),  # edge 0.05 < 0.10
        }
    )
    items = scan([passing, no_amb, illiquid, tiny_edge], analyzer)
    slugs = [it.candidate.market_slug for it in items]
    assert slugs == ["good"]


def test_ranking_by_convex_score_desc():
    a = _cand("a", 0.05)  # cheaper => more convex
    b = _cand("b", 0.12)  # near zone ceiling
    analyzer = FakeAnalyzer(
        {
            "a": (0.30, 0.9, "strong"),
            "b": (0.30, 0.9, "strong but dearer"),
        }
    )
    items = scan([b, a], analyzer)  # input order reversed
    assert [it.candidate.market_slug for it in items] == ["a", "b"]
    assert items[0].signal.convex_score >= items[1].signal.convex_score


def test_to_jsonl_roundtrips():
    cand = _cand("good", 0.05)
    analyzer = FakeAnalyzer({"good": (0.30, 0.8, "real edge")})
    items = scan([cand], analyzer)
    out = to_jsonl(items)
    rows = [json.loads(line) for line in out.splitlines()]
    assert len(rows) == 1
    assert rows[0]["candidate"]["market_slug"] == "good"
    assert rows[0]["signal"]["pass_gates"] is True
    assert "true_prob_estimate" in rows[0]["assessment"]


def test_custom_params_tighten_gates():
    cand = _cand("edge", 0.10)
    analyzer = FakeAnalyzer({"edge": (0.22, 0.8, "edge 0.12")})
    # Default min_edge 0.10 => passes.
    assert len(scan([cand], analyzer)) == 1
    # Tighten min_edge to 0.15 => excluded.
    strict = ScanParams(min_edge=0.15)
    assert scan([cand], analyzer, strict) == []
