"""Offline tests for the outcome_collector: pure mapping + collect->scan pipeline.

No network: the gamma payload comes from a saved fixture (pure parser test) and an
injected fake fetcher (pipeline test). The default OFFLINE HeuristicAnalyzer is
used — no LLM, no key.
"""

from __future__ import annotations

import json
from pathlib import Path

from scanner.analyzer import HeuristicAnalyzer

from feeds import outcome_collector as oc

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name):
    with open(FIXTURES / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# PURE parser: gamma JSON -> OutcomeCandidate
# ---------------------------------------------------------------------------

def test_parser_maps_cheap_outcomes_with_price_and_resolution_text():
    payload = _load("gamma_outcomes.json")
    cands = oc.gamma_events_to_candidates(payload)

    by_slug = {c.market_slug: c for c in cands}
    # cheap "Yes" outcomes are kept; the 0.80 favorite is excluded.
    assert "will-x-happen-2026" in by_slug
    assert "thin-longshot" in by_slug
    assert "favorite-market" not in by_slug

    cheap = by_slug["will-x-happen-2026"]
    assert cheap.outcome == "Yes"
    assert cheap.price == 0.07
    assert "sole discretion" in cheap.resolution_text
    assert cheap.end_iso == "2026-12-31T00:00:00Z"
    assert cheap.top_ask_notional_usd == 800.0


def test_parser_excludes_expensive_and_keeps_no_cheap_legs():
    payload = _load("gamma_outcomes.json")
    cands = oc.gamma_events_to_candidates(payload, max_price=0.15)
    # No outcome priced above 0.15 should appear (the 0.93/0.90/0.20/0.80 legs).
    assert all(c.price <= 0.15 for c in cands)
    assert all(c.outcome == "Yes" for c in cands)  # only the cheap legs


def test_parser_handles_garbage_payload():
    assert oc.gamma_events_to_candidates(None) == []
    assert oc.gamma_events_to_candidates("nonsense") == []
    assert oc.gamma_events_to_candidates([]) == []


# ---------------------------------------------------------------------------
# Pipeline: collect -> scan -> watchlist (offline, injected fetcher)
# ---------------------------------------------------------------------------

def test_pipeline_writes_valid_watchlist_offline(tmp_path):
    payload = _load("gamma_outcomes.json")

    summary = oc.collect(
        fetcher=lambda: payload,
        analyzer=HeuristicAnalyzer(),
        runtime_dir=str(tmp_path),
        write=True,
    )

    cand_path = tmp_path / "candidates.jsonl"
    watch_path = tmp_path / "watchlist.jsonl"
    assert cand_path.exists()
    assert watch_path.exists()

    # candidates.jsonl: each line is a valid OutcomeCandidate dict.
    cand_lines = [l for l in cand_path.read_text().splitlines() if l.strip()]
    assert summary["candidates"] == len(cand_lines) >= 2
    for line in cand_lines:
        obj = json.loads(line)
        assert set(obj) >= {"market_slug", "outcome", "price", "resolution_text"}
        assert obj["price"] <= 0.15

    # watchlist.jsonl: each line is a valid WatchlistItem with pass_gates True.
    watch_lines = [l for l in watch_path.read_text().splitlines() if l.strip()]
    assert summary["watchlist"] == len(watch_lines)
    assert summary["watchlist"] >= 1  # the ambiguous, liquid cheap market flags
    flagged_slugs = set()
    for line in watch_lines:
        obj = json.loads(line)
        assert obj["signal"]["pass_gates"] is True
        flagged_slugs.add(obj["candidate"]["market_slug"])
    # The ambiguous + liquid cheap market is flagged; the thin one (liquidity 5)
    # fails the liquidity gate and is NOT on the watchlist.
    assert "will-x-happen-2026" in flagged_slugs
    assert "thin-longshot" not in flagged_slugs


def test_pipeline_no_write_returns_counts(tmp_path):
    payload = _load("gamma_outcomes.json")
    summary = oc.collect(
        fetcher=lambda: payload,
        analyzer=HeuristicAnalyzer(),
        runtime_dir=str(tmp_path),
        write=False,
    )
    assert summary["candidates"] >= 2
    assert not (tmp_path / "candidates.jsonl").exists()
    assert not (tmp_path / "watchlist.jsonl").exists()


def test_pipeline_default_analyzer_is_heuristic_offline(tmp_path):
    payload = _load("gamma_outcomes.json")
    # No analyzer passed -> defaults to the offline HeuristicAnalyzer (no LLM).
    summary = oc.collect(fetcher=lambda: payload, runtime_dir=str(tmp_path), write=True)
    assert summary["watchlist"] >= 1


def test_empty_fetch_yields_empty_outputs(tmp_path):
    summary = oc.collect(fetcher=lambda: [], runtime_dir=str(tmp_path), write=True)
    assert summary["candidates"] == 0
    assert summary["watchlist"] == 0
    assert (tmp_path / "candidates.jsonl").read_text() == ""
    assert (tmp_path / "watchlist.jsonl").read_text() == ""
