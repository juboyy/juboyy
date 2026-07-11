"""Shared test fixtures: sample candidates + a fake analyzer/client."""

from __future__ import annotations

from typing import List

from scanner.analyzer import ResolutionAnalyzer
from scanner.contracts import OutcomeCandidate, ResolutionAssessment


# Neutral resolution text: explicit source, explicit timezone, no vague terms,
# no discretion clauses, no conflicting clauses.
NEUTRAL_TEXT = (
    "This market resolves YES if the official UTC closing value reported by the "
    "exchange according to the published settlement feed is at or above 100."
)

# Vague resolution text: discretion + vagueness + conflict + missing source/tz.
VAGUE_TEXT = (
    "This market resolves YES approximately when the outcome is achieved, as "
    "determined by the team in its sole discretion, however subject to review."
)


def cheap_neutral() -> OutcomeCandidate:
    return OutcomeCandidate(
        market_slug="mkt-neutral",
        outcome="Yes",
        price=0.10,
        resolution_text=NEUTRAL_TEXT,
        end_iso="2026-12-31T00:00:00Z",
        top_ask_notional_usd=500.0,
    )


def cheap_vague() -> OutcomeCandidate:
    return OutcomeCandidate(
        market_slug="mkt-vague",
        outcome="Yes",
        price=0.08,
        resolution_text=VAGUE_TEXT,
        end_iso="2026-12-31T00:00:00Z",
        top_ask_notional_usd=500.0,
    )


class FakeAnalyzer(ResolutionAnalyzer):
    """Returns a fixed (true_prob, ambiguity) per market_slug for deterministic
    scan() tests. Defaults to no-edge (true_prob == price)."""

    def __init__(self, table: dict | None = None) -> None:
        # table: market_slug -> (true_prob, ambiguity, rationale)
        self.table = table or {}

    def assess(self, candidate: OutcomeCandidate) -> ResolutionAssessment:
        if candidate.market_slug in self.table:
            tp, amb, rat = self.table[candidate.market_slug]
        else:
            tp, amb, rat = candidate.price, 0.0, "no-edge default"
        return ResolutionAssessment(
            true_prob_estimate=tp,
            ambiguity_score=amb,
            rationale=rat,
            source="fake",
        )


class _FakeBlock:
    def __init__(self, input_dict: dict) -> None:
        self.type = "tool_use"
        self.input = input_dict


class _FakeResponse:
    def __init__(self, input_dict: dict) -> None:
        # Include a leading text block to ensure parsing skips non-tool_use blocks.
        text_block = type("T", (), {"type": "text", "text": "ignore me"})()
        self.content = [text_block, _FakeBlock(input_dict)]


class FakeMessages:
    """Records the create() kwargs and returns a canned tool_use response."""

    def __init__(self, input_dict: dict, recorder: list) -> None:
        self._input = input_dict
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.append(kwargs)
        return _FakeResponse(self._input)


class FakeAnthropicClient:
    """Stand-in for anthropic.Anthropic(); no network, no key needed."""

    def __init__(self, input_dict: dict) -> None:
        self.calls: list = []
        self.messages = FakeMessages(input_dict, self.calls)
