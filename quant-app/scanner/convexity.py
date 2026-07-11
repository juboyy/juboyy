"""
convexity.py — PURE, deterministic convexity math for the scanner.

No I/O, no clock reads, no network, no randomness. Standard library only.

The convexity thesis
--------------------
On Polymarket there is a documented favorite-longshot REVERSAL: cheap,
low-probability outcomes (price <= ~0.30) are systematically OVERpriced because
retail overpays for tails. So a cheap outcome is −EV BY DEFAULT — a high payoff
multiple (1/price) is NOT a reason to bet. The ONLY way a cheap outcome is +EV is
a SPECIFIC edge, most reliably a resolution-rule edge: the crowd misread the
resolution criteria, so the true settle probability exceeds the price.

This module therefore never rewards "high payoff multiple" on its own. It rewards
a positive `edge` (true_prob - price) that survives costs, and it amplifies that
edge by the convexity (1/price) only once the edge is established. When edge <= 0
the convex_score collapses to ~0 and the gates fail — the cheap outcome is NOT
flagged. That is the core anti-longshot-trap guarantee.

Cost model
----------
We replicate (minimally, stdlib-only) the slippage + fee idea from
``engine/costs.py`` so the deterministic core needs no engine import. For a $1
binary buy at `price`:

    fee_cost  = fee_bps / 10_000          (fraction of $1 notional)
    slip_cost = slip                      (fraction of $1 notional, e.g. 0.005)
    total_cost_fraction = fee_cost + slip_cost

The EV of staking $1 to buy at `price` and receiving $1 on a YES resolution is:

    gross_ev_per_dollar = true_prob * (1 / price) - 1
    ev_per_dollar       = gross_ev_per_dollar - total_cost_fraction

(The cost is charged as a fraction of the $1 staked — the round-trip frictions a
real fill at this price incurs.)
"""

from __future__ import annotations

# --- Documented gate defaults -------------------------------------------------
# Every default is documented here and re-stated in README.md.
#
# max_longshot_price : 0.15 — the "convex zone". Only outcomes priced at or below
#   this are eligible. Above it we are no longer in the cheap/convex regime where
#   a resolution edge produces large asymmetric payoff, and the longshot reversal
#   premium we are exploiting is concentrated in the cheap tail.
# min_edge : 0.10 — required (true_prob - price). A cheap outcome must beat its
#   price by at least 10 probability points for us to overcome the reversal's
#   −EV default plus model uncertainty.
# min_ambiguity : 0.4 — only resolution-edge cases qualify. Edge with no
#   ambiguity in the resolution text is suspect (likely model error, not a real
#   crowd misread), so we require the analyzer to also flag the rules as
#   meaningfully misread-able.
# min_ev_per_dollar : 0.0 — EV after costs must be strictly positive.
# min_liquidity_usd : 50.0 — top-of-ask notional floor; below this a fill is not
#   actionable even as a watchlist item.
# default_fee_bps : 0.0 — Polymarket has no maker/taker fee by default.
# default_slip : 0.005 — 0.5% slippage haircut on the $1 stake.
DEFAULT_MAX_LONGSHOT_PRICE = 0.15
DEFAULT_MIN_EDGE = 0.10
DEFAULT_MIN_AMBIGUITY = 0.4
DEFAULT_MIN_EV_PER_DOLLAR = 0.0
DEFAULT_MIN_LIQUIDITY_USD = 50.0
DEFAULT_FEE_BPS = 0.0
DEFAULT_SLIP = 0.005


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def payoff_multiple(price: float) -> float:
    """Gross payoff multiple of a $1 binary buy at `price` = 1/price.

    Returns 0.0 for non-positive prices (degenerate; no real payoff leverage to
    speak of). For price >= 1 the multiple is <= 1 (no convexity).
    """
    if price <= 0.0:
        return 0.0
    return 1.0 / price


def cost_fraction(fee_bps: float = DEFAULT_FEE_BPS, slip: float = DEFAULT_SLIP) -> float:
    """Total round-trip cost as a fraction of the $1 staked.

    Mirrors the slippage + fee idea from engine/costs.py (slippage + fees), but
    expressed per-dollar so it composes directly with ev_per_dollar.
    """
    return (fee_bps / 10_000.0) + slip


def net_payoff_multiple(
    price: float,
    fee_bps: float = DEFAULT_FEE_BPS,
    slip: float = DEFAULT_SLIP,
) -> float:
    """Payoff multiple net of the cost haircut on the $1 stake.

    The gross multiple pays 1/price on a win; the cost is a fraction of the stake
    that is lost regardless, so the cost-adjusted multiple is
    (1 - cost_fraction) / price.
    """
    if price <= 0.0:
        return 0.0
    return (1.0 - cost_fraction(fee_bps, slip)) / price


def edge(true_prob: float, price: float) -> float:
    """Probability edge = true_prob - price (can be negative)."""
    return true_prob - price


def expected_value_per_dollar(
    price: float,
    true_prob: float,
    fee_bps: float = DEFAULT_FEE_BPS,
    slip: float = DEFAULT_SLIP,
) -> float:
    """EV per $1 staked for a binary buy at `price` paying $1 on YES, net of costs.

    gross = true_prob * (1/price) - 1
    ev    = gross - cost_fraction(fee_bps, slip)

    A degenerate price <= 0 yields -1.0 - cost (no payoff possible / total loss).
    """
    if price <= 0.0:
        return -1.0 - cost_fraction(fee_bps, slip)
    gross = true_prob * (1.0 / price) - 1.0
    return gross - cost_fraction(fee_bps, slip)


def convex_score(
    price: float,
    true_prob: float,
    ambiguity_score: float,
    *,
    max_longshot_price: float = DEFAULT_MAX_LONGSHOT_PRICE,
    fee_bps: float = DEFAULT_FEE_BPS,
    slip: float = DEFAULT_SLIP,
) -> float:
    """A bounded score in [0, 1] rewarding convexity AND edge AND confidence.

    Design (and the anti-longshot-trap guarantee):

    - If edge <= 0, return 0.0. A cheap outcome with true_prob == price (the
      DEFAULT analyzer behavior) scores exactly 0 and will never be flagged.
    - Otherwise combine three multiplicative factors, each in [0, 1]:

        edge_factor      = min(1, edge / max_longshot_price)
            normalizes the edge against the convex-zone width; a full-zone edge
            saturates.
        convex_factor    = min(1, max_longshot_price / price)
            rewards lower price (more convexity); == 1 at the zone ceiling and
            grows no further (capped) for cheaper prices.
        ambiguity_factor = clamp(ambiguity_score)
            requires the analyzer's confidence that the rules are misread-able.

    Multiplicative means a zero in any factor zeroes the score — edge, convexity,
    and a resolution-ambiguity basis must ALL be present. Monotonic: increasing
    true_prob (more edge), decreasing price (more convexity), or increasing
    ambiguity each weakly increases the score.

    The score is gated to 0 when ev_per_dollar after costs is not positive, so a
    nominal edge that costs eat away does not score.
    """
    e = edge(true_prob, price)
    if e <= 0.0:
        return 0.0
    if expected_value_per_dollar(price, true_prob, fee_bps, slip) <= 0.0:
        return 0.0
    if price <= 0.0:
        return 0.0
    if max_longshot_price <= 0.0:
        return 0.0

    edge_factor = _clamp(e / max_longshot_price)
    convex_factor = _clamp(max_longshot_price / price)
    ambiguity_factor = _clamp(ambiguity_score)

    return _clamp(edge_factor * convex_factor * ambiguity_factor)
