"""Convexity math: payoff_multiple, ev, edge, convex_score monotonicity, and the
core anti-longshot-trap guarantee (edge<=0 => score ~0)."""

from __future__ import annotations

import math

from scanner import convexity as cx


def test_payoff_multiple():
    assert cx.payoff_multiple(0.10) == 10.0
    assert cx.payoff_multiple(0.25) == 4.0
    assert cx.payoff_multiple(1.0) == 1.0
    # Degenerate / non-positive price => 0 (no leverage).
    assert cx.payoff_multiple(0.0) == 0.0
    assert cx.payoff_multiple(-0.5) == 0.0


def test_net_payoff_multiple_is_below_gross():
    gross = cx.payoff_multiple(0.10)
    net = cx.net_payoff_multiple(0.10, fee_bps=0.0, slip=0.005)
    assert net < gross
    # (1 - 0.005) / 0.10
    assert math.isclose(net, 0.995 / 0.10, rel_tol=1e-9)


def test_edge():
    assert math.isclose(cx.edge(0.30, 0.10), 0.20, rel_tol=1e-9)
    assert math.isclose(cx.edge(0.10, 0.10), 0.0, abs_tol=1e-12)
    assert cx.edge(0.05, 0.10) < 0


def test_expected_value_per_dollar_no_edge_is_negative_after_costs():
    # true_prob == price => gross EV == 0, so after costs it must be negative.
    ev = cx.expected_value_per_dollar(0.10, 0.10, fee_bps=0.0, slip=0.005)
    assert ev < 0
    assert math.isclose(ev, -0.005, abs_tol=1e-9)


def test_expected_value_per_dollar_positive_edge():
    # true_prob 0.30 at price 0.10 => gross = 0.30*10 - 1 = 2.0
    ev = cx.expected_value_per_dollar(0.10, 0.30, fee_bps=0.0, slip=0.005)
    assert math.isclose(ev, 2.0 - 0.005, rel_tol=1e-9)


def test_expected_value_per_dollar_degenerate_price():
    ev = cx.expected_value_per_dollar(0.0, 0.5)
    assert ev <= -1.0


def test_convex_score_zero_when_no_edge():
    # The anti-longshot-trap guarantee: cheap outcome, true_prob == price.
    assert cx.convex_score(0.05, 0.05, ambiguity_score=1.0) == 0.0
    # Negative edge also zero.
    assert cx.convex_score(0.05, 0.02, ambiguity_score=1.0) == 0.0


def test_convex_score_in_unit_interval():
    s = cx.convex_score(0.05, 0.30, ambiguity_score=0.8)
    assert 0.0 <= s <= 1.0


def test_convex_score_monotonic_in_true_prob():
    # More edge (higher true_prob) => higher (or equal) score.
    lo = cx.convex_score(0.10, 0.20, ambiguity_score=0.8)
    hi = cx.convex_score(0.10, 0.30, ambiguity_score=0.8)
    assert hi >= lo
    assert hi > 0


def test_convex_score_monotonic_in_convexity():
    # Lower price (more convex) at the same edge => higher (or equal) score.
    # Hold edge constant at 0.12: price 0.10 -> tp 0.22 ; price 0.05 -> tp 0.17.
    cheaper = cx.convex_score(0.05, 0.17, ambiguity_score=0.8)
    dearer = cx.convex_score(0.10, 0.22, ambiguity_score=0.8)
    assert cheaper >= dearer


def test_convex_score_monotonic_in_ambiguity():
    lo = cx.convex_score(0.05, 0.30, ambiguity_score=0.4)
    hi = cx.convex_score(0.05, 0.30, ambiguity_score=0.9)
    assert hi >= lo


def test_convex_score_zero_when_costs_eat_edge():
    # Tiny edge that EV-after-costs cannot clear should not score.
    # price 0.10, true_prob 0.1004 => gross EV = 0.1004*10 - 1 = 0.004;
    # with slip 0.005 => ev < 0 => score must be 0.
    score = cx.convex_score(0.10, 0.1004, ambiguity_score=1.0, slip=0.005)
    assert score == 0.0
