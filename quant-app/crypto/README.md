# `crypto/` — Execution Adapter (non-custodial wallet + execution)

The execution adapter is the **only** component allowed to hold key material
(`02_SYSTEM_SPEC.md` §2, the non-custodial boundary). Everything else — the API,
the mobile app, the dashboard — is key-free and reads runtime artifacts only.

## Security model (summary of `docs/06_SECURITY.md`)

- **Non-custodial.** `PM_PRIVATE_KEY` is read **only** from the process env,
  **only** inside the live adapter, and is **never**:
  - logged or printed,
  - returned from any method,
  - written to disk,
  - stored as an instance attribute,
  - passed to the API / mobile layers, or
  - placed in any `05_DATA_CONTRACTS.md` record.
  The key is read into a transient local inside `_ensure_client()`, handed to the
  **official** `py_clob_client.ClobClient` (which does the signing), and dropped.
- **Dry-run by default.** The default adapter is `PaperExecutionAdapter`, which is
  fully offline, standard-library only, and touches **no** keys. A live order is
  **impossible** unless all of these hold:
  1. `mode == "live"`, **and**
  2. `armed == True`, **and**
  3. every required env var is present (`PM_PRIVATE_KEY`, `PM_API_KEY`,
     `PM_API_SECRET`, `PM_API_PASSPHRASE`, and `PM_FUNDER`/`PM_ADDRESS`).
  If any is missing, `PolymarketExecutionAdapter` **refuses to even construct**
  (raises `LiveGateError`). The factory returns Paper for every other combination.
- **Host allow-list.** Live mode only talks to the official Polymarket CLOB host
  (`https://clob.polymarket.com`). Custom endpoints are rejected (`06 §3`).
- **Lazy import.** `py_clob_client` is imported **only** inside the live adapter,
  **only** when arming live. The core/paper path imports nothing third-party.
- **Redaction.** `safety.redact()` scrubs any key-like material (known secret env
  values, `SECRET=...` assignments, and standalone 64+ hex-char blobs) from every
  error/repr. Addresses are masked to `0x1234…ab12`.

## Dry-run vs live

```python
from crypto.factory import get_adapter

# Default: offline paper simulator (no keys, deterministic fills).
adapter = get_adapter()                       # PaperExecutionAdapter

adapter = get_adapter(mode="dry_run", armed=True)   # still Paper (armed alone ≠ live)
adapter = get_adapter(mode="live", armed=False)     # still Paper (not armed)

# Live: requires BOTH flags AND env creds, else raises LiveGateError.
adapter = get_adapter(mode="live", armed=True)      # PolymarketExecutionAdapter
```

Arming is a deliberate, typed-confirmation action (`safety.Arming`): the
disarmed → armed transition requires the exact confirm token (`06 §7`). The API /
Risk Manager are expected to gate `armed=True` behind that state machine plus the
kill switch and dead-man's switch.

### Paper adapter (`paper.py`)

Deterministic simulated fills using the engine cost model (`03 §8`):

- **Slippage:** `shares × slip_ticks × tick` (default `slip_ticks=1`, `tick=0.01`).
- **Gas:** `gas_usdc` per on-chain action (default `0.02`; open and close count
  separately; a skipped close incurs no close-side gas).
- **Fees:** `fee_bps` on notional (default `0`).
- **Net P&L (canonical):**
  `realized_cashflow_pnl_usdc = cashflow − cost_basis − slippage − gas − fees`.

A single seeded `random.Random` drives any fill jitter (default off), so identical
inputs ⇒ identical outputs (`02 §2`, `03 §9`). Produces `Order`/`Position` and
`TradeResult` exactly per `05 §5`/`§6` (field names match `dashboard/parser.py`).

### Live adapter (`polymarket.py`)

Mirrors the upstream bot's construction (`dashboard/docs/SECURITY_AUDIT.md`):
`ClobClient(host, chain_id=POLYGON, key=…, signature_type=…, funder=…)` +
`set_api_creds(ApiCreds(...))`. The actual order-submission calls are clearly
marked `# LIVE — gated` stubs (raise `NotImplementedError`) so this build makes
**no** network calls; the gating, credential handling, masking, and shapes around
them are real and correct.

## Exact env vars (from `dashboard/docs/env.example`)

| Var | Meaning |
|-----|---------|
| `PM_PRIVATE_KEY` | Private key of the **dedicated** trading wallet (hex). **Never leaves this process.** |
| `PM_FUNDER` (or alias `PM_ADDRESS`) | Funder / proxy-wallet address holding the USDC. |
| `PM_SIGNATURE_TYPE` | Polymarket signature type; `2` = proxy/email-wallet model (recommended). |
| `PM_API_KEY` / `PM_API_SECRET` / `PM_API_PASSPHRASE` | Polymarket CLOB API credentials. |
| `PM_CLOB_BASE` *(optional)* | Defaults to the official host; live mode forbids non-official hosts. |

Load these from a `chmod 600 .env` kept outside synced/backup/git paths
(`06 §5`). The key, API secrets, and any seed material **never** appear in code,
logs, images, CI output, the mobile bundle, crash reports, or any API response.

## Files

| File | Purpose |
|------|---------|
| `adapter.py` | Abstract `ExecutionAdapter` interface + `Quote`/`Order`/`Position`/`TradeResult`/`Balance` shapes (`05`). Stdlib only, no keys. |
| `paper.py` | `PaperExecutionAdapter` (default) + `CostModel`. Deterministic, offline. |
| `polymarket.py` | `PolymarketExecutionAdapter` (live, gated). Lazy `py_clob_client`; key never stored/logged. |
| `safety.py` | `Arming`, `KillSwitch`, `DeadMansSwitch`, `redact()`, `mask_address()`. |
| `factory.py` | `get_adapter(mode, armed)` → Paper by default, Polymarket only when live+armed. |
| `tests/` | Pytest suite — offline, no network, no real key required. |

## Running the tests

```bash
cd quant-app/crypto && python -m pytest -q
```

Tests cover: deterministic paper fills + cost integration, the arming state
machine (cannot go live without the confirm token), the kill switch (blocks new
entries + triggers close), dead-man trip conditions, `redact()` never leaking a
key, and the live adapter **refusing** to operate when disarmed or missing env.
They never hit the network and never need a real key.
