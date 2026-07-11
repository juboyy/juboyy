"""
scan.py — the scan orchestration (pure given an injected analyzer).

`scan(candidates, analyzer, params)` runs the supplied analyzer over each
candidate, computes a deterministic `ConvexSignal`, keeps only the gate-passers,
ranks by `convex_score` descending, and returns a list of `WatchlistItem`.

Apart from the analyzer (which may itself do I/O if it is the optional
ClaudeAnalyzer), `scan` is pure and deterministic: same inputs + same analyzer
behavior => same output. With the heuristic analyzer the whole pipeline is fully
offline and deterministic.

`to_jsonl` is the only I/O helper here (string serialization).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List

from . import convexity
from .analyzer import ResolutionAnalyzer
from .contracts import ConvexSignal, OutcomeCandidate, WatchlistItem


@dataclass(frozen=True)
class ScanParams:
    """Tunable gate thresholds + cost inputs. Defaults documented in convexity.py."""

    max_longshot_price: float = convexity.DEFAULT_MAX_LONGSHOT_PRICE
    min_edge: float = convexity.DEFAULT_MIN_EDGE
    min_ambiguity: float = convexity.DEFAULT_MIN_AMBIGUITY
    min_ev_per_dollar: float = convexity.DEFAULT_MIN_EV_PER_DOLLAR
    min_liquidity_usd: float = convexity.DEFAULT_MIN_LIQUIDITY_USD
    fee_bps: float = convexity.DEFAULT_FEE_BPS
    slip: float = convexity.DEFAULT_SLIP


def evaluate(
    candidate: OutcomeCandidate,
    true_prob: float,
    ambiguity_score: float,
    params: ScanParams,
) -> ConvexSignal:
    """Compute the deterministic ConvexSignal + hard gates for one candidate.

    Hard gates (ALL must pass to flag):
      1. price <= max_longshot_price           (convex zone)
      2. edge  >= min_edge                      (true_prob - price)
      3. ev_per_dollar > min_ev_per_dollar      (positive after costs)
      4. ambiguity_score >= min_ambiguity       (resolution-edge cases only)
      5. top_ask_notional_usd >= min_liquidity_usd
    """
    price = candidate.price
    pm = convexity.payoff_multiple(price)
    e = convexity.edge(true_prob, price)
    ev = convexity.expected_value_per_dollar(price, true_prob, params.fee_bps, params.slip)
    score = convexity.convex_score(
        price,
        true_prob,
        ambiguity_score,
        max_longshot_price=params.max_longshot_price,
        fee_bps=params.fee_bps,
        slip=params.slip,
    )

    reasons: List[str] = []
    gate_price = price <= params.max_longshot_price
    gate_edge = e >= params.min_edge
    gate_ev = ev > params.min_ev_per_dollar
    gate_amb = ambiguity_score >= params.min_ambiguity
    gate_liq = candidate.top_ask_notional_usd >= params.min_liquidity_usd

    reasons.append(
        f"price<=max_longshot_price ({price}<={params.max_longshot_price}): {gate_price}"
    )
    reasons.append(f"edge>=min_edge ({round(e,4)}>={params.min_edge}): {gate_edge}")
    reasons.append(f"ev_per_dollar>min ({round(ev,4)}>{params.min_ev_per_dollar}): {gate_ev}")
    reasons.append(
        f"ambiguity>=min ({round(ambiguity_score,4)}>={params.min_ambiguity}): {gate_amb}"
    )
    reasons.append(
        f"liquidity>=floor ({candidate.top_ask_notional_usd}>={params.min_liquidity_usd}): {gate_liq}"
    )

    pass_gates = gate_price and gate_edge and gate_ev and gate_amb and gate_liq

    return ConvexSignal(
        payoff_multiple=round(pm, 6),
        edge=round(e, 6),
        ev_per_dollar=round(ev, 6),
        convex_score=round(score, 6),
        pass_gates=pass_gates,
        reasons=reasons,
    )


def scan(
    candidates: Iterable[OutcomeCandidate],
    analyzer: ResolutionAnalyzer,
    params: ScanParams = ScanParams(),
) -> List[WatchlistItem]:
    """Run the analyzer + scoring over candidates; keep gate-passers, rank desc.

    Pure given an injected analyzer with deterministic behavior. Ranking is by
    convex_score descending; ties are broken by edge descending, then by
    market_slug + outcome for a stable, deterministic order.
    """
    items: List[WatchlistItem] = []
    for cand in candidates:
        assessment = analyzer.assess(cand)
        signal = evaluate(
            cand,
            assessment.true_prob_estimate,
            assessment.ambiguity_score,
            params,
        )
        if signal.pass_gates:
            items.append(WatchlistItem(candidate=cand, assessment=assessment, signal=signal))

    items.sort(
        key=lambda it: (
            -it.signal.convex_score,
            -it.signal.edge,
            it.candidate.market_slug,
            it.candidate.outcome,
        )
    )
    return items


def to_jsonl(items: Iterable[WatchlistItem]) -> str:
    """Serialize watchlist items to newline-delimited JSON (one item per line)."""
    return "\n".join(json.dumps(it.to_dict(), sort_keys=True) for it in items)
