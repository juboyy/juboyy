"""HeuristicAnalyzer: default true_prob==price on neutral text; raised ambiguity
on vague resolution text."""

from __future__ import annotations

from scanner.analyzer import HeuristicAnalyzer, make_analyzer
from scanner.tests.fixtures import cheap_neutral, cheap_vague


def test_heuristic_neutral_no_edge():
    a = HeuristicAnalyzer()
    cand = cheap_neutral()
    assessment = a.assess(cand)
    # Default: NO edge — true_prob == price (respects the longshot reversal).
    assert assessment.true_prob_estimate == cand.price
    assert assessment.source == "heuristic"


def test_heuristic_vague_raises_ambiguity():
    a = HeuristicAnalyzer()
    neutral = a.assess(cheap_neutral())
    vague = a.assess(cheap_vague())
    # Vague text must score meaningfully higher ambiguity than neutral text.
    assert vague.ambiguity_score > neutral.ambiguity_score
    assert vague.ambiguity_score >= 0.4


def test_heuristic_nudges_only_on_strong_ambiguity():
    a = HeuristicAnalyzer()
    vague = cheap_vague()
    assessment = a.assess(vague)
    # Strong discretion clause present => true_prob nudged above price, but capped.
    assert assessment.true_prob_estimate > vague.price
    assert assessment.true_prob_estimate - vague.price <= 0.12 + 1e-9


def test_heuristic_ambiguity_in_unit_interval():
    a = HeuristicAnalyzer()
    for cand in (cheap_neutral(), cheap_vague()):
        s = a.assess(cand).ambiguity_score
        assert 0.0 <= s <= 1.0


def test_make_analyzer_heuristic_default():
    a = make_analyzer()
    assert isinstance(a, HeuristicAnalyzer)
    a2 = make_analyzer("heuristic")
    assert isinstance(a2, HeuristicAnalyzer)


def test_make_analyzer_unknown_raises():
    import pytest

    with pytest.raises(ValueError):
        make_analyzer("nope")
