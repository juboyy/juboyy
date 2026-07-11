"""
contracts.py — dataclasses for the convexity / resolution-edge scanner.

Standard library only. These are plain, frozen-where-sensible data carriers
shared across the scanner. They contain NO logic and NO I/O.

Glossary
--------
OutcomeCandidate   : a single Polymarket outcome we might bet on, plus the raw
                     resolution text and a little liquidity context.
ResolutionAssessment : an analyzer's (heuristic or LLM) OFFLINE read of how the
                     outcome will actually settle — a true-probability estimate,
                     an ambiguity score, and a rationale.
ConvexSignal       : the deterministic scoring of a candidate given an
                     assessment — payoff multiple, edge, EV/dollar, a bounded
                     convex_score, and whether all hard gates passed.
WatchlistItem      : the three combined, for output.

This module is part of an OFFLINE, ADVISORY-ONLY research tool. Nothing here is
imported by the trade-decision runtime. See README.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass(frozen=True)
class OutcomeCandidate:
    """A single Polymarket outcome under consideration.

    Attributes
    ----------
    market_slug : human/url identifier of the market.
    outcome : the specific outcome label (e.g. "Yes", "Candidate A").
    price : current ask price in [0, 1] — the cost per $1 of payoff.
    resolution_text : the market's resolution criteria, verbatim. This is what
        an analyzer reads to decide whether the crowd may have misread the rules.
    end_iso : ISO-8601 end/resolution timestamp (string; not parsed here).
    top_ask_notional_usd : USD notional available at the top of the ask book —
        a coarse liquidity gate input.
    """

    market_slug: str
    outcome: str
    price: float
    resolution_text: str
    end_iso: str
    top_ask_notional_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolutionAssessment:
    """An OFFLINE analyzer's read of how an outcome will resolve.

    Attributes
    ----------
    true_prob_estimate : estimated probability the outcome resolves YES, in
        [0, 1], based on the resolution rules + widely-known facts. By DEFAULT an
        analyzer returns this equal to the price (no edge) — respecting the
        favorite-longshot reversal. It is nudged above price ONLY when a specific
        resolution-reading edge is detected.
    ambiguity_score : in [0, 1]; how ambiguous / misread-able the resolution
        criteria are. High ambiguity is a prerequisite for a resolution edge.
    rationale : short free-text justification.
    source : provenance of the assessment, e.g. "heuristic" or "claude:<model>".
    """

    true_prob_estimate: float
    ambiguity_score: float
    rationale: str
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConvexSignal:
    """Deterministic scoring of a candidate given an assessment.

    Attributes
    ----------
    payoff_multiple : gross 1/price (capped/handled for price<=0 in convexity.py).
    edge : true_prob_estimate - price.
    ev_per_dollar : expected value per $1 staked, net of fees + slippage costs.
    convex_score : in [0, 1]; rewards low price (convexity) AND positive edge AND
        analyzer confidence. ~0 when edge <= 0 (the anti-longshot-trap guarantee).
    pass_gates : True only if EVERY hard gate passed.
    reasons : human-readable list explaining gate pass/fail and scoring.
    """

    payoff_multiple: float
    edge: float
    ev_per_dollar: float
    convex_score: float
    pass_gates: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchlistItem:
    """A scored candidate: the candidate, its assessment, and its signal."""

    candidate: OutcomeCandidate
    assessment: ResolutionAssessment
    signal: ConvexSignal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "assessment": self.assessment.to_dict(),
            "signal": self.signal.to_dict(),
        }
