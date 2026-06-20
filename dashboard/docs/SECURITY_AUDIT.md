# Security Audit — `Novals83/5min-btc-polymarket` execution bot

> Scope: a **read-only review of public source** of the upstream bot that this
> dashboard monitors, focused on the only thing that can instantly cost you
> everything — how it handles your wallet key, dependencies, and network.
> Reviewed at commit on `main` as of 2026-06-20. This is **not** an endorsement;
> re-verify before trusting it with funds.

## TL;DR verdict

**Not obviously malicious.** It uses the **official** Polymarket client and only
talks to **official** Polymarket hosts, and it does **not** print or log your
private key. The residual risk is **not** the bot's intent — it's
**supply-chain (unpinned deps), key-custody hygiene, and operational failure
modes**. Mitigations below are mandatory before `--execute`.

## What the bot actually does with your key

From `scripts/test_btc_5m_session_exit_sl.py`:

```python
from py_clob_client.client import ClobClient        # official Polymarket SDK
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import ApiCreds

key    = os.getenv('PM_PRIVATE_KEY') or ''
funder = os.getenv('PM_FUNDER') or os.getenv('PM_ADDRESS') or None
sig    = int(os.getenv('PM_SIGNATURE_TYPE', '2'))
v1,v2,v3 = os.getenv('PM_API_KEY'), os.getenv('PM_API_SECRET'), os.getenv('PM_API_PASSPHRASE')

c = ClobClient(host=clob_base, chain_id=POLYGON, key=key, signature_type=sig, funder=funder)
c.set_api_creds(ApiCreds(api_key=v1, api_secret=v2, api_passphrase=v3))
```

- The private key is read from the env var **`PM_PRIVATE_KEY`** and passed
  straight to the **official `py_clob_client.ClobClient`** — signing is done by
  that library, not by hand-rolled code. Good.
- `signature_type` defaults to **2** with a **`PM_FUNDER`** address — i.e. it
  expects the **Polymarket proxy-wallet** model, not necessarily your raw EOA.
- Endpoints are the **official** `https://clob.polymarket.com` and
  `https://gamma-api.polymarket.com/events`. No unknown/exfil hosts seen.
- The key is **never** included in the JSON report it prints. Good.

## Risk findings

| # | Severity | Finding | Why it matters |
|---|----------|---------|----------------|
| 1 | **High** | **No `requirements.txt`** (returns 404). Deps are unpinned. | Any compromised/typo-squatted transitive dep installed alongside `py-clob-client` runs in the **same process that holds `PM_PRIVATE_KEY` in memory**. This is the most realistic way to lose funds. |
| 2 | **Medium** | `import subprocess` in the runner. | A trading script shelling out is a flag. Read every `subprocess.*` call and confirm it isn't run with untrusted input. |
| 3 | **Medium** | Key lives in a plaintext **`.env` on disk**, and `docker-compose.yml` **bind-mounts the host workspace** into the container. | If the workspace is ever synced (Dropbox/iCloud/git), backed up, or the box is shared, the key leaks. |
| 4 | **Medium** | README does **not** document env vars or give a hard dry-run warning — only a generic disclaimer. | Easy to misconfigure; one `--execute` away from live orders. |
| 5 | **Low** | `py-clob-client` is pulled from PyPI by name. | Confirm it resolves to the **official `Polymarket/py-clob-client`** and pin the exact version + hash. |

## Required mitigations (do all before `--execute`)

1. **Dedicated, isolated wallet.** Create a brand-new wallet used *only* for this
   bot. Fund it with **only** the capital you can lose. Never put your main
   wallet's key in `.env`. Prefer the Polymarket **proxy-wallet** model
   (`PM_SIGNATURE_TYPE=2` + `PM_FUNDER`) so the signing key is not your primary
   holdings key.
2. **Pin dependencies + isolate.** Use the `requirements.pinned.txt` in this
   folder (pin exact versions, ideally with hashes via `pip-compile`), install
   in a clean `.venv` **inside the container only**, and verify
   `py-clob-client` is the official package before installing.
3. **Lock down the `.env`.** `chmod 600 .env`, keep it outside any synced/backup
   folder, confirm it is git-ignored, and never paste it anywhere.
4. **Read the `subprocess` calls** in `test_btc_5m_session_exit_sl.py` yourself.
   If any pass network/market data into a shell, do not run it.
5. **Dry-run first.** Run with `--execute` **omitted** for a meaningful sample
   (days, not minutes) and reconcile the reported P&L before risking a cent.

See `SAFE_OPERATION.md` for the step-by-step runbook and `.env.example` for the
exact variable names.

## What this audit does NOT cover

- The internals of `py-clob-client` itself (assumed-official, not re-audited).
- Whether the **strategy is profitable** — that is an edge question, not a
  security one. Backtest it; do not trust stars.
- Polymarket's own custody, resolution, or regulatory restrictions in your
  jurisdiction.
