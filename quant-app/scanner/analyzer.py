"""
analyzer.py — resolution analyzers (OFFLINE, advisory).

An analyzer reads an `OutcomeCandidate` and returns a `ResolutionAssessment`: a
true-probability estimate, an ambiguity score, and a rationale. Analyzers run
OFFLINE only and are never imported by the trade-decision runtime.

Two analyzers live here:

- `HeuristicAnalyzer` (default): pure, deterministic, stdlib-only. It scans the
  resolution text for ambiguity signals and, CRUCIALLY, defaults
  `true_prob_estimate = price` (NO edge) — respecting the favorite-longshot
  reversal. It only nudges true_prob above price when STRONG, specific ambiguity
  is detected, and the nudge is capped.

- `ClaudeAnalyzer` lives in `claude_analyzer.py` (optional, gated). The factory
  below can construct it lazily.
"""

from __future__ import annotations

import abc
from typing import Callable, Dict, List, Tuple

from .contracts import OutcomeCandidate, ResolutionAssessment


class ResolutionAnalyzer(abc.ABC):
    """Abstract base: assess how an outcome will RESOLVE (offline)."""

    @abc.abstractmethod
    def assess(self, candidate: OutcomeCandidate) -> ResolutionAssessment:
        """Return a ResolutionAssessment for `candidate`. Must be side-effect free
        with respect to the trade runtime (offline/advisory only)."""
        raise NotImplementedError


# --- Heuristic analyzer -------------------------------------------------------

# Vague / ambiguity-signalling phrases. Each contributes weight toward the
# ambiguity score. "Strong" signals (sole-discretion style) also unlock a small,
# capped true_prob nudge because they are the classic resolution-misread tells.
_WEAK_SIGNALS: Tuple[str, ...] = (
    "approximately",
    "around",
    "about ",
    "roughly",
    "official",
    "by end of",
    "as soon as",
    "generally",
    "in general",
    "expected to",
    "likely",
    "may ",
    "could ",
)

_STRONG_SIGNALS: Tuple[str, ...] = (
    "as determined by",
    "sole discretion",
    "sole judgment",
    "at its discretion",
    "subjective",
    "good faith",
    "reasonable judgment",
)

# Per-signal weights toward ambiguity_score.
_WEAK_WEIGHT = 0.12
_STRONG_WEIGHT = 0.30

# Structural ambiguity checks (missing source / timezone) add weight too.
_SOURCE_TERMS: Tuple[str, ...] = ("source", "according to", "per ", "resolves according")
_TIMEZONE_TERMS: Tuple[str, ...] = ("utc", "gmt", "est", "edt", "pst", "pt", "et ", "timezone", "time zone")

_MISSING_SOURCE_WEIGHT = 0.15
_MISSING_TIMEZONE_WEIGHT = 0.10

# Conflicting-clause heuristic: presence of "but"/"however"/"unless"/"except"
# alongside a deadline phrase suggests carve-outs the crowd may overlook.
_CONFLICT_TERMS: Tuple[str, ...] = ("however", "but ", "unless", "except", "provided that", "notwithstanding")
_CONFLICT_WEIGHT = 0.18

# Cap on how far a heuristic may nudge true_prob above price. Deliberately small:
# the heuristic has no real-world model, only a "the rules look misread-able"
# prior, so the nudge is a modest, capped expression of that — never a large
# claim. Nudges only fire on STRONG ambiguity.
_MAX_HEURISTIC_NUDGE = 0.12


def _count_hits(text: str, terms: Tuple[str, ...]) -> int:
    return sum(1 for t in terms if t in text)


class HeuristicAnalyzer(ResolutionAnalyzer):
    """Deterministic, offline analyzer.

    Behavior:

    - `ambiguity_score` is accumulated from weak/strong vague phrases, a missing
      explicit source, a missing timezone, and conflicting clauses; clamped to
      [0, 1].
    - `true_prob_estimate` DEFAULTS to the price (no edge). It is nudged above
      price ONLY when strong, specific ambiguity is present, scaled by how strong
      that ambiguity is, and capped at `_MAX_HEURISTIC_NUDGE`. The nudged value is
      clamped to [0, 1).
    - `source = "heuristic"`.
    """

    source = "heuristic"

    def __init__(self, max_nudge: float = _MAX_HEURISTIC_NUDGE) -> None:
        self.max_nudge = max_nudge

    def _ambiguity(self, text: str) -> Tuple[float, List[str]]:
        t = text.lower()
        reasons: List[str] = []
        score = 0.0

        weak = _count_hits(t, _WEAK_SIGNALS)
        if weak:
            score += weak * _WEAK_WEIGHT
            reasons.append(f"weak_vague_terms={weak}")

        strong = _count_hits(t, _STRONG_SIGNALS)
        if strong:
            score += strong * _STRONG_WEIGHT
            reasons.append(f"strong_discretion_terms={strong}")

        if _count_hits(t, _SOURCE_TERMS) == 0:
            score += _MISSING_SOURCE_WEIGHT
            reasons.append("missing_explicit_source")

        if _count_hits(t, _TIMEZONE_TERMS) == 0:
            score += _MISSING_TIMEZONE_WEIGHT
            reasons.append("missing_timezone")

        conflict = _count_hits(t, _CONFLICT_TERMS)
        if conflict:
            score += conflict * _CONFLICT_WEIGHT
            reasons.append(f"conflicting_clauses={conflict}")

        if score > 1.0:
            score = 1.0
        return score, reasons

    def assess(self, candidate: OutcomeCandidate) -> ResolutionAssessment:
        ambiguity, reasons = self._ambiguity(candidate.resolution_text)

        # DEFAULT: no edge — true_prob == price (respects the longshot reversal).
        true_prob = candidate.price

        # Nudge ONLY on strong, specific ambiguity. The nudge is proportional to
        # the strength signal count and capped.
        t = candidate.resolution_text.lower()
        strong = _count_hits(t, _STRONG_SIGNALS)
        if strong > 0 and ambiguity >= 0.4:
            # scale: each strong signal contributes, saturating at max_nudge.
            nudge = min(self.max_nudge, strong * (self.max_nudge / 2.0))
            true_prob = min(0.999, candidate.price + nudge)
            reasons.append(f"true_prob_nudged_by={round(true_prob - candidate.price, 4)}")
        else:
            reasons.append("true_prob=price (no specific edge; respecting longshot reversal)")

        rationale = "; ".join(reasons) if reasons else "no ambiguity signals detected"

        return ResolutionAssessment(
            true_prob_estimate=round(true_prob, 6),
            ambiguity_score=round(ambiguity, 6),
            rationale=rationale,
            source=self.source,
        )


# --- Factory ------------------------------------------------------------------

def make_analyzer(kind: str = "heuristic", **kwargs) -> ResolutionAnalyzer:
    """Construct an analyzer by kind.

    kind="heuristic" -> HeuristicAnalyzer (offline, no key, default).
    kind="claude"    -> ClaudeAnalyzer (lazy import; optional, gated). Any kwargs
                        (model, fallback_to_heuristic, ...) pass through.

    The ClaudeAnalyzer import is deferred so this module — and the heuristic
    path — works with no `anthropic` package installed.
    """
    k = kind.lower().strip()
    if k == "heuristic":
        return HeuristicAnalyzer(**kwargs)
    if k == "claude":
        from .claude_analyzer import ClaudeAnalyzer  # lazy: no SDK needed otherwise

        return ClaudeAnalyzer(**kwargs)
    raise ValueError(f"unknown analyzer kind: {kind!r} (expected 'heuristic' or 'claude')")
