# scanner — convexity / resolution-edge scanner

An **OFFLINE, ADVISORY-ONLY** research tool that scans Polymarket outcomes for
**asymmetric (convex) +EV bets** and emits a ranked watchlist. It produces a
list of candidates worth a human look — it never executes trades.

---

## Hard invariant (enforced)

> The scanner is **OFFLINE** and **ADVISORY ONLY**. It produces a watchlist; it
> **NEVER executes trades** and is **NEVER imported by the trade-decision
> runtime**. An LLM (Claude) may be used here for **OFFLINE resolution-text
> analysis only** — it is **not** in the deterministic decision/execution loop.
> The trade engine's "no LLM in runtime" invariant is preserved because this
> module is a separate research tool.

How this is enforced in code:

- The package has no path that places an order or touches an execution surface.
- The deterministic core (`contracts`, `convexity`, `analyzer` /
  `HeuristicAnalyzer`, `scan`) imports and runs with **no third-party
  dependencies**.
- The optional LLM analyzer (`ClaudeAnalyzer`) **lazily imports `anthropic`**
  only when constructed, so the package — and the heuristic path — works with no
  SDK installed. The API key is read by the SDK from the environment and is
  **never logged**; prompts are built from public market fields only.

---

## The convexity thesis & the favorite-longshot reversal it guards against

On Polymarket there is a documented **favorite-longshot REVERSAL**: cheap,
low-probability outcomes (price ≤ ~0.30) are systematically **OVERpriced**
because retail overpays for tails. Consequences:

- Buying a cheap outcome is **−EV BY DEFAULT**.
- A high payoff multiple (`1/price`) is **NOT** a reason to bet — the scanner
  never flags something merely because the payoff is large.

The **only** way a cheap outcome is +EV is a **specific edge**, most reliably a
**resolution-rule edge**: the crowd misread the resolution criteria, so the true
settle probability is higher than the price. The scanner therefore flags an
outcome **only** when an analyzer supplies an estimated true probability that
exceeds the price by a margin, net of costs, **and** the resolution text looks
genuinely misread-able.

### How the reversal is enforced in code

1. **Analyzers default to no edge.** `HeuristicAnalyzer` sets
   `true_prob_estimate = price` by default, nudging it above price only on
   strong, *specific* ambiguity (capped at +0.12). `ClaudeAnalyzer` is prompted
   to default `true_prob_estimate` to the price unless a concrete
   resolution-reading reason exists (anti-hallucination).
2. **`convex_score` collapses to ~0 when edge ≤ 0** (`convexity.convex_score`).
   It rewards convexity (`1/price`) *only after* a positive edge is established,
   and also returns 0 when EV-after-costs is not positive. A cheap outcome with
   `true_prob == price` scores exactly 0 and is never flagged — the core
   **anti-longshot-trap guarantee**.
3. **Hard gates** (below) require a minimum edge, positive EV after costs, and a
   minimum resolution ambiguity — payoff size alone never passes.

---

## Hard gates and their defaults

An outcome is flagged only if **every** gate passes (`scan.evaluate`). Defaults
live in `convexity.py`:

| Gate | Default | Rationale |
|---|---|---|
| `price ≤ max_longshot_price` | **0.15** | The convex zone — the cheap tail where the reversal premium is concentrated and a resolution edge yields large asymmetric payoff. |
| `true_prob − price ≥ min_edge` | **0.10** | A cheap outcome must beat its price by ≥10 probability points to overcome the −EV default plus model uncertainty. |
| `ev_per_dollar > min_ev_per_dollar` | **0.0** | EV after fees + slippage must be strictly positive. |
| `ambiguity_score ≥ min_ambiguity` | **0.4** | Only resolution-edge cases qualify; edge with no rule ambiguity is treated as suspect. |
| `top_ask_notional_usd ≥ min_liquidity_usd` | **50.0** | Below this a fill is not actionable even as a watchlist item. |

Cost inputs (also in `convexity.py`): `fee_bps` default **0.0** (Polymarket has
no default maker/taker fee), `slip` default **0.005** (0.5% slippage haircut on
the $1 stake). EV per dollar:

```
ev_per_dollar = true_prob * (1/price) - 1 - (fee_bps/10_000 + slip)
```

This mirrors the slippage + fee idea from `../engine/costs.py`, replicated
minimally here so the deterministic core needs no engine import.

Override any default by constructing `ScanParams(...)` and passing it to
`scan(...)`.

---

## Files

| File | Role |
|---|---|
| `contracts.py` | Dataclasses: `OutcomeCandidate`, `ResolutionAssessment`, `ConvexSignal`, `WatchlistItem`. |
| `convexity.py` | Pure deterministic math: `payoff_multiple`, `net_payoff_multiple`, `edge`, `expected_value_per_dollar`, `convex_score`, and documented gate defaults. |
| `analyzer.py` | `ResolutionAnalyzer` ABC, default `HeuristicAnalyzer` (offline), `make_analyzer(kind, ...)` factory. |
| `claude_analyzer.py` | Optional `ClaudeAnalyzer` — strict tool use + forced `tool_choice`, lazy `anthropic` import. |
| `scan.py` | `scan(candidates, analyzer, params)` + `evaluate(...)` + `to_jsonl(items)`. |
| `cli.py` | `python -m scanner.cli scan ...`. |
| `tests/` | pytest suite + fixtures (offline, no network, no key). |

---

## Environment variables (ClaudeAnalyzer only)

- `SCANNER_MODEL` — model id for the OFFLINE Claude analyzer. Default
  `claude-haiku-4-5` (a cheap, fast classification-grade model).
- `ANTHROPIC_API_KEY` — read by the Anthropic SDK from the environment. **Never
  logged** by this module.

### Claude strict-tool-use integration

`ClaudeAnalyzer` obtains structured JSON via **strict tool use with a forced
`tool_choice`** — the tool `report_resolution_assessment` has `strict: True`,
`additionalProperties: False`, and a `required` list, and the request forces
`tool_choice={"type": "tool", "name": "report_resolution_assessment"}`. The
result is read off the response's `tool_use` block (`block.input`), already a
dict of `{true_prob_estimate, ambiguity_score, rationale}`. If the SDK or key is
missing, the analyzer either raises a clear error or (operator-configurable via
`fallback_to_heuristic=True`) falls back to the offline `HeuristicAnalyzer`.

---

## CLI usage

```bash
# Offline (default; no API key needed)
python -m scanner.cli scan candidates.jsonl --analyzer heuristic --out watchlist.jsonl

# Optional OFFLINE LLM analysis (requires anthropic + ANTHROPIC_API_KEY)
SCANNER_MODEL=claude-haiku-4-5 \
  python -m scanner.cli scan candidates.jsonl --analyzer claude --out watchlist.jsonl

# Fall back to heuristic if the SDK/key/API is unavailable
python -m scanner.cli scan candidates.jsonl --analyzer claude --claude-fallback
```

Each input line is a JSON object with the `OutcomeCandidate` fields:

```json
{"market_slug": "will-x-happen", "outcome": "Yes", "price": 0.06,
 "resolution_text": "Resolves YES ... as determined by the organizer in its sole discretion ...",
 "end_iso": "2026-12-31T00:00:00Z", "top_ask_notional_usd": 800.0}
```

Output is JSONL, one ranked `WatchlistItem` per line (gate-passers only, ranked
by `convex_score` descending). With no `--out`, output goes to stdout.

---

## Programmatic use

```python
from scanner import OutcomeCandidate, make_analyzer
from scanner.scan import scan, ScanParams

candidates = [OutcomeCandidate(...), ...]
analyzer = make_analyzer("heuristic")          # offline default
watchlist = scan(candidates, analyzer, ScanParams())
```

`scan` is **pure given an injected analyzer**: with the heuristic analyzer the
whole pipeline is deterministic and offline.

---

## Tests

```bash
cd /home/user/juboyy/quant-app
python -m pytest scanner -q
```

The suite covers convexity math and monotonicity, the anti-longshot-trap
guarantee (zero edge ⇒ score ≈ 0, gates fail), the heuristic analyzer's no-edge
default and ambiguity scoring, `scan()` gate-filtering + ranking, and the
`ClaudeAnalyzer` parsing path with an **injected fake client** (no real API call,
no key in logs). **All tests run OFFLINE with no network and no API key**, and
the deterministic core imports and tests with **no `anthropic` package**.
