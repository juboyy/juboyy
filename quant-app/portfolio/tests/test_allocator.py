"""CapitalAllocator splits bankroll by weights and respects per-strategy caps."""

import pytest

from portfolio.allocator import CapitalAllocator


def test_splits_by_normalized_weights():
    alloc = CapitalAllocator(1000.0, {"a": 3.0, "b": 1.0})
    assert alloc.budget_for("a") == 750.0
    assert alloc.budget_for("b") == 250.0


def test_weights_need_not_sum_to_one():
    # Weights {2, 2} normalize to even split regardless of magnitude.
    alloc = CapitalAllocator(100.0, {"a": 2.0, "b": 2.0})
    assert alloc.budget_for("a") == 50.0
    assert alloc.budget_for("b") == 50.0


def test_unknown_strategy_gets_zero():
    alloc = CapitalAllocator(100.0, {"a": 1.0})
    assert alloc.budget_for("nope") == 0.0


def test_respects_per_strategy_cap():
    alloc = CapitalAllocator(1000.0, {"a": 1.0, "b": 1.0}, caps={"a": 100.0})
    # raw budget would be 500 but cap clamps to 100.
    assert alloc.budget_for("a") == 100.0
    assert alloc.budget_for("b") == 500.0


def test_budgets_returns_all():
    alloc = CapitalAllocator(100.0, {"a": 1.0, "b": 1.0})
    assert alloc.budgets() == {"a": 50.0, "b": 50.0}


def test_rebalance_updates_weights_and_bankroll():
    alloc = CapitalAllocator(100.0, {"a": 1.0, "b": 1.0})
    alloc.rebalance(bankroll_usd=200.0, weights={"a": 3.0, "b": 1.0})
    assert alloc.budget_for("a") == 150.0
    assert alloc.budget_for("b") == 50.0


def test_zero_total_weight_yields_zero():
    alloc = CapitalAllocator(100.0, {"a": 0.0})
    assert alloc.budget_for("a") == 0.0


def test_negative_bankroll_rejected():
    with pytest.raises(ValueError):
        CapitalAllocator(-1.0, {"a": 1.0})
