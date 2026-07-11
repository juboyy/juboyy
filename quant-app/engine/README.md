# engine — deterministic trading engine

Pure-function trading spine for the quant app, implemented exactly to the
normative specs:

- `docs/03_QUANT_STRATEGY.md` — entry/exit/sizing/hedge rules, cost model, backtest.
- `docs/04_INDICATORS.md` — indicator math + the Signal Engine (gates + score).
- `docs/05_DATA_CONTRACTS.md` — canonical contracts (field names are normative).
- `docs/02_SYSTEM_SPEC.md` — the pure-function spine.

## Invariants

- **No LLM, no network, no clock reads** inside `indicators/`, `signal`, `decide`.
  Pure functions: same input ⇒ same output. Time enters as `seconds_left`/`ts`
  parameters, never read from the clock.
- **Standard library only** for the core (indicators, signal, risk, sizing, costs,
  backtest). `pytest` is the only dev dependency. `py_clob_client` is **not**
  imported here — live execution lives in the separate `crypto/` workstream.
- Everything dry-run / deterministic. Any simulated jitter is seeded.

## The spine (`02 §2`)

```
Snapshot ─▶ indicators.compute(Snapshot, history, profile) ─▶ Features
Features ─▶ signal.evaluate(Features, Snapshot, profile, risk_allows) ─▶ Signal
Signal   ─▶ signal.decide(Signal, profile, seconds_left, skew_clob, ...) ─▶ Decision
Decision ─▶ risk.apply_decision(Decision, RiskState, profile) ─▶ Decision'
```

`signal.evaluate_and_decide(...)` runs `evaluate` then `decide`, threading
`seconds_left` (from the snapshot) and `skew_clob` (from features) for the overlays.

## Modules

| File | Responsibility |
|------|----------------|
| `contracts.py` | Dataclasses for every `05` contract (MarketSnapshot, Features, Signal, Decision, Order/Position, TradeResult, RiskState, Account, BotStatus). Field names match `dashboard/parser.py`. |
| `config.py` | `Profile` dataclass + `conservative`/`aggressive` defaults from `config_defaults.json` and the `03 §7` / `04 §8` parameter tables. |
| `indicators/` | One pure function per `04` indicator: `momentum`, `realized_vol`, `skew`, `liquidity`, `imbalance`, `time_decay`, `staleness`. `compute()` assembles `Features`. |
| `signal_engine.py` | Signal Engine (`04 §8`): hard gates → weighted composite score → Decision with overlays (stop_loss / time_exit / hedge / kill). Carries every subscore + the passed/failed gate list. (Named `signal_engine`, not `signal`, to avoid shadowing the stdlib `signal` module.) |
| `risk.py` | Risk Manager (`03 §6`): daily caps, kill flag, dead-man, no conflicting position. `risk.apply(state, profile, ...) -> Allowance(allowed, reason)`. |
| `sizing.py` | Position sizing (`03 §4`): stake/notional/risk caps, `shares = floor(min(...) / limit_price)`, fractional-Kelly helper, `w<=p ⇒ do-not-trade` guard. |
| `costs.py` | Cost model (`03 §8`): slippage, gas, fees, canonical net `realized_cashflow_pnl_usdc`, cost-adjusted break-even. |
| `datasource.py` | Pluggable `MarketSnapshotSource` / `BtcSpotSource` (abstract) + `RecordedSource` (JSONL) + `MockSource` (seeded). `LiveBtcSpotSource` is a GATED stub (raises). |
| `capture.py` | `CaptureRecorder` appends normalized snapshots to `runtime/captured_snapshots.jsonl` to build a backtest dataset over time. |
| `backtest.py` | Walk-forward harness (`03 §9`): replays JSONL through the same spine, costs always on, deterministic, no look-ahead. `run_backtest(path) -> metrics` + `format_report`. |
| `cli.py` | `decide` / `backtest` / `capture` commands. |

## Open decision: BTC spot source

`LiveBtcSpotSource` is intentionally **not implemented** and raises
`NotImplementedError`. The concrete live feed (e.g. Binance / Coinbase websocket)
is an open decision **gated on the owner** and belongs in the networked `crypto/`
workstream behind the `BtcSpotSource` interface — never inside the pure core.
Backtests and dry-run use `RecordedSource` / `MockSource`.

## CLI

```bash
# decide on a single snapshot JSON
python -m engine.cli decide path/to/snapshot.json --profile conservative

# walk-forward backtest over a recorded JSONL dataset
python -m engine.cli backtest engine/tests/fixtures/backtest_small.jsonl --json

# append a normalized snapshot to the capture file
python -m engine.cli capture path/to/snapshot.json --settle-side up
```

(Run `python -m engine.cli ...` from the `quant-app/` directory so `engine` imports
as a package.)

## Tests

```bash
cd quant-app/engine
pip install pytest            # if needed
python -m pytest -q           # 70 passed
```

Unit tests cover every indicator (incl. null/edge cases), every hard gate (pass +
fail), the weighted score math, the decision overlays (enter/hold/skip/exit/hedge/
kill), sizing (incl. do-not-trade when `w<=p`), costs, risk caps (cap-respect), and
a backtest smoke test over `tests/fixtures/backtest_small.jsonl`.

## Backtest dataset & acceptance

The harness reads recorded snapshots where each record carries a `settle_side`
(`"up"`/`"down"`) label, revealed only after entry (no look-ahead). It reports all
`03 §9` metrics. **Positive backtest results are hypotheses to be killed, not proof**
(`03 §2`): default to paper, and clear the cost-adjusted break-even with margin in
forward paper before any live arming.
