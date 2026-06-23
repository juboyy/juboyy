"""
scanner — OFFLINE, ADVISORY convexity / resolution-edge scanner for Polymarket.

This package scans Polymarket outcomes for ASYMMETRIC (convex) +EV bets, guarding
against the favorite-longshot REVERSAL (cheap outcomes are −EV by default). It
flags an outcome ONLY when an analyzer supplies an estimated true probability
that beats the price by a margin, net of costs, AND the resolution criteria look
genuinely misread-able.

HARD INVARIANT: this module is OFFLINE and ADVISORY ONLY. It produces a
watchlist; it NEVER executes trades and is NEVER imported by the trade-decision
runtime. An LLM (Claude) may be used here for OFFLINE resolution-text analysis
only — it is not in the deterministic decision/execution loop, so the trade
engine's "no LLM in runtime" invariant is preserved.

The deterministic core (contracts, convexity, analyzer/HeuristicAnalyzer, scan)
imports and runs with NO third-party dependencies. The optional ClaudeAnalyzer
lazily imports `anthropic` only when constructed.
"""

from __future__ import annotations

from . import contracts, convexity, analyzer, scan
from .analyzer import HeuristicAnalyzer, ResolutionAnalyzer, make_analyzer
from .contracts import (
    ConvexSignal,
    OutcomeCandidate,
    ResolutionAssessment,
    WatchlistItem,
)
from .scan import ScanParams, evaluate, to_jsonl

__all__ = [
    "contracts",
    "convexity",
    "analyzer",
    "scan",
    "HeuristicAnalyzer",
    "ResolutionAnalyzer",
    "make_analyzer",
    "OutcomeCandidate",
    "ResolutionAssessment",
    "ConvexSignal",
    "WatchlistItem",
    "ScanParams",
    "evaluate",
    "to_jsonl",
]

__version__ = "1.0"
