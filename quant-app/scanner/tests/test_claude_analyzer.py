"""ClaudeAnalyzer WITHOUT network: inject a fake client, assert it parses the
tool_use input correctly, uses strict tool use + forced tool_choice, and never
logs the key. No real API call is made."""

from __future__ import annotations

from scanner.claude_analyzer import DEFAULT_MODEL, TOOL, ClaudeAnalyzer
from scanner.contracts import OutcomeCandidate
from scanner.tests.fixtures import FakeAnthropicClient, cheap_vague


def test_tool_is_strict_and_closed():
    assert TOOL["strict"] is True
    schema = TOOL["input_schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"true_prob_estimate", "ambiguity_score", "rationale"}


def test_parses_fake_tool_use_input():
    fake_input = {
        "true_prob_estimate": 0.42,
        "ambiguity_score": 0.7,
        "rationale": "resolution clause is ambiguous",
    }
    client = FakeAnthropicClient(fake_input)
    analyzer = ClaudeAnalyzer(client=client, model="claude-haiku-4-5")
    assessment = analyzer.assess(cheap_vague())

    assert assessment.true_prob_estimate == 0.42
    assert assessment.ambiguity_score == 0.7
    assert assessment.rationale == "resolution clause is ambiguous"
    assert assessment.source == "claude:claude-haiku-4-5"


def test_uses_forced_tool_choice_and_strict_tool():
    client = FakeAnthropicClient(
        {"true_prob_estimate": 0.1, "ambiguity_score": 0.1, "rationale": "x"}
    )
    analyzer = ClaudeAnalyzer(client=client)
    analyzer.assess(cheap_vague())

    assert len(client.calls) == 1
    kwargs = client.calls[0]
    # Forced tool_choice to the exact tool name.
    assert kwargs["tool_choice"] == {
        "type": "tool",
        "name": "report_resolution_assessment",
    }
    # Strict tool passed.
    assert kwargs["tools"][0]["strict"] is True
    assert kwargs["tools"][0]["name"] == "report_resolution_assessment"


def test_default_model_constant():
    assert DEFAULT_MODEL == "claude-haiku-4-5"


def test_clamps_out_of_range_values():
    client = FakeAnthropicClient(
        {"true_prob_estimate": 1.5, "ambiguity_score": -0.3, "rationale": "weird"}
    )
    analyzer = ClaudeAnalyzer(client=client)
    a = analyzer.assess(cheap_vague())
    assert a.true_prob_estimate == 1.0
    assert a.ambiguity_score == 0.0


def test_never_logs_key(capsys, monkeypatch):
    # Set a sentinel key; assert it never appears in captured stdout/stderr.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SENTINEL-DO-NOT-LOG")
    client = FakeAnthropicClient(
        {"true_prob_estimate": 0.2, "ambiguity_score": 0.5, "rationale": "ok"}
    )
    analyzer = ClaudeAnalyzer(client=client)
    analyzer.assess(cheap_vague())
    captured = capsys.readouterr()
    assert "SENTINEL" not in captured.out
    assert "SENTINEL" not in captured.err


def test_prompt_contains_no_secret(monkeypatch):
    # The prompt is built from public market fields only; ensure the key is not
    # interpolated into the request messages.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SENTINEL")
    client = FakeAnthropicClient(
        {"true_prob_estimate": 0.2, "ambiguity_score": 0.5, "rationale": "ok"}
    )
    analyzer = ClaudeAnalyzer(client=client)
    analyzer.assess(cheap_vague())
    sent = client.calls[0]["messages"][0]["content"]
    assert "SENTINEL" not in sent


def test_fallback_to_heuristic_on_client_error():
    class BoomClient:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("simulated API failure")

    cand = OutcomeCandidate(
        market_slug="m",
        outcome="Yes",
        price=0.1,
        resolution_text="as determined by the team in its sole discretion, approximately.",
        end_iso="",
        top_ask_notional_usd=100.0,
    )
    analyzer = ClaudeAnalyzer(client=BoomClient(), fallback_to_heuristic=True)
    a = analyzer.assess(cand)
    # Heuristic fallback used => source is heuristic.
    assert a.source == "heuristic"


def test_no_network_import_not_required():
    # Constructing with an injected client must not import anthropic.
    client = FakeAnthropicClient(
        {"true_prob_estimate": 0.2, "ambiguity_score": 0.5, "rationale": "ok"}
    )
    analyzer = ClaudeAnalyzer(client=client)
    # _get_client returns the injected client without importing anthropic.
    assert analyzer._get_client() is client
