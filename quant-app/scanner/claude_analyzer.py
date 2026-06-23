"""
claude_analyzer.py — OPTIONAL, gated LLM resolution analyzer.

OFFLINE / ADVISORY ONLY. This analyzer uses the official Anthropic Python SDK to
read a Polymarket outcome's resolution criteria and return a structured
assessment. It is a research tool: it is NEVER imported by the trade-decision
runtime, and Claude is therefore NOT in the deterministic decision/execution
loop. The trade engine's "no LLM in runtime" invariant is preserved.

Determinism / safety properties:

- The `anthropic` SDK is imported LAZILY (inside the constructor / method), so
  importing this module — and the whole `scanner` package — works with no SDK
  installed.
- If the SDK or API key is missing, behavior is operator-configurable: either
  raise a clear error, or fall back to the offline HeuristicAnalyzer.
- The API key is NEVER logged. The prompt is built from public market fields
  only (question, outcome, price, resolution text) — no secrets.
- The prompt instructs the model to DEFAULT true_prob to the given price unless a
  SPECIFIC resolution-reading reason exists (anti-hallucination; respects the
  favorite-longshot reversal).

Structured output is obtained via STRICT tool use with a FORCED tool_choice.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .analyzer import HeuristicAnalyzer, ResolutionAnalyzer
from .contracts import OutcomeCandidate, ResolutionAssessment

# Default model: a cheap, fast classification-grade model for offline triage.
DEFAULT_MODEL = "claude-haiku-4-5"

# Strict tool-use definition. `strict: True` + `additionalProperties: False` +
# `required` guarantee the tool_use.input validates exactly to this schema.
TOOL: Dict[str, Any] = {
    "name": "report_resolution_assessment",
    "description": (
        "Return a structured assessment of how a Polymarket outcome will RESOLVE, "
        "focusing on whether the crowd may have misread the resolution criteria."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "true_prob_estimate": {
                "type": "number",
                "description": (
                    "Your estimate in [0,1] of the probability this outcome resolves "
                    "YES, based ONLY on the resolution rules + widely-known facts. "
                    "Default to the market price unless you have a specific reason."
                ),
            },
            "ambiguity_score": {
                "type": "number",
                "description": "0..1 how ambiguous/misread-able the resolution criteria are.",
            },
            "rationale": {"type": "string"},
        },
        "required": ["true_prob_estimate", "ambiguity_score", "rationale"],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "You are an OFFLINE research analyst assessing how a Polymarket outcome will "
    "RESOLVE. Reason ONLY about the resolution rules and widely-known facts. On "
    "Polymarket cheap outcomes are systematically OVERpriced (favorite-longshot "
    "reversal), so the ONLY reason to believe the true settle probability exceeds "
    "the price is a SPECIFIC resolution-reading edge — the crowd misread the "
    "criteria. By DEFAULT set true_prob_estimate EQUAL to the market price. Only "
    "deviate when you can point to a concrete clause the market is likely "
    "misreading. Do not speculate about the underlying event beyond what the rules "
    "and common knowledge support."
)


def _build_prompt(candidate: OutcomeCandidate) -> str:
    """Build the user prompt strictly from public market fields.

    Contains no secrets. Resolution semantics only.
    """
    return (
        f"Market: {candidate.market_slug}\n"
        f"Outcome: {candidate.outcome}\n"
        f"Current price (implied probability): {candidate.price}\n"
        f"Resolution criteria (verbatim):\n"
        f"---\n{candidate.resolution_text}\n---\n\n"
        "Assess how this outcome resolves. Call report_resolution_assessment with "
        "your estimate. Default true_prob_estimate to the price above unless a "
        "specific reading of the resolution rules justifies a different value."
    )


class ClaudeAnalyzer(ResolutionAnalyzer):
    """LLM-backed offline resolution analyzer (strict tool use, forced tool).

    Parameters
    ----------
    model : model id; defaults to env SCANNER_MODEL or DEFAULT_MODEL.
    client : optional pre-built Anthropic client (or a fake, for tests). If None,
        a real client is lazily constructed on first use.
    fallback_to_heuristic : if True, missing SDK/key or an API error falls back to
        the offline HeuristicAnalyzer instead of raising.
    max_tokens : cap for the tool-use response.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        client: Any = None,
        fallback_to_heuristic: bool = False,
        max_tokens: int = 1024,
    ) -> None:
        self.model = model or os.getenv("SCANNER_MODEL", DEFAULT_MODEL)
        self._client = client
        self.fallback_to_heuristic = fallback_to_heuristic
        self.max_tokens = max_tokens
        self._heuristic = HeuristicAnalyzer()
        self.source = f"claude:{self.model}"

    def _get_client(self) -> Any:
        """Return the (possibly injected) client; lazily build a real one.

        The `anthropic` import is deferred to here so the module imports without
        the SDK. The key is read by the SDK from the environment — we never read
        or log it ourselves.
        """
        if self._client is not None:
            return self._client
        try:
            import anthropic  # lazy import: package optional
        except ImportError as exc:  # pragma: no cover - exercised only without SDK
            raise RuntimeError(
                "ClaudeAnalyzer requires the 'anthropic' package. "
                "Install it, or use the heuristic analyzer."
            ) from exc
        # Reads ANTHROPIC_API_KEY from env; never logged.
        self._client = anthropic.Anthropic()
        return self._client

    def _call(self, candidate: OutcomeCandidate) -> Dict[str, Any]:
        client = self._get_client()
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=_SYSTEM,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "report_resolution_assessment"},
            messages=[{"role": "user", "content": _build_prompt(candidate)}],
        )
        # Pull the forced tool_use block; its .input is already a dict matching the
        # strict schema: {true_prob_estimate, ambiguity_score, rationale}.
        block = next(b for b in resp.content if getattr(b, "type", None) == "tool_use")
        return block.input

    def assess(self, candidate: OutcomeCandidate) -> ResolutionAssessment:
        try:
            data = self._call(candidate)
        except Exception:
            if self.fallback_to_heuristic:
                # Note: we deliberately do NOT log the exception text — it could in
                # principle echo request details. The heuristic carries on offline.
                return self._heuristic.assess(candidate)
            raise

        # Defensive clamping; the model is instructed to stay in [0,1] and the
        # strict schema enforces numeric types, but we clamp anyway.
        true_prob = float(data["true_prob_estimate"])
        ambiguity = float(data["ambiguity_score"])
        true_prob = min(1.0, max(0.0, true_prob))
        ambiguity = min(1.0, max(0.0, ambiguity))
        rationale = str(data.get("rationale", ""))

        return ResolutionAssessment(
            true_prob_estimate=round(true_prob, 6),
            ambiguity_score=round(ambiguity, 6),
            rationale=rationale,
            source=self.source,
        )
