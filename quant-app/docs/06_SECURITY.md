# 06 — Security Architecture & Threat Model

> Builds on the existing **`dashboard/docs/SECURITY_AUDIT.md`** (audit of the
> upstream execution bot) and **`dashboard/docs/SAFE_OPERATION.md`** (runbook).
> This document is the *system-wide* threat model for the cockpit (engine + API +
> mobile + adapter). It **references** the audit; it does not repeat it.

## 1. Assets to protect (in priority order)
| ID | Asset | Impact if lost |
|----|-------|----------------|
| A1 | **`PM_PRIVATE_KEY`** (dedicated trading wallet) | Total loss of wallet funds |
| A2 | **Wallet funds** (USDC in funder/proxy) | Direct financial loss |
| A3 | **Polymarket API creds** (`PM_API_KEY/SECRET/PASSPHRASE`) | Unauthorized order placement |
| A4 | **Backend control auth** (bearer token) | Remote arm/start/kill of the bot |
| A5 | **Integrity of the decision spine** | Malicious/buggy trades |
| A6 | **Operational availability** (no dead-bot-with-open-position) | Unstopped losses |

## 2. Trust boundaries (recap of `02`)
- **Custodial zone (one process only):** the **Execution Adapter** on the host
  holds A1/A3 in env. *Nothing else touches keys.*
- **Read/control zone:** Backend API reads `runtime/` artifacts and flips
  flags; **never** reads keys.
- **Untrusted-ish zone:** the mobile device + the network between phone and API.
- Crossing phone→API requires **A4 token over TLS**; crossing API→adapter is
  **flag files / signals only** (no key transit).

## 3. STRIDE threat model
| Threat (STRIDE) | Scenario | Affected | Mitigation |
|-----------------|----------|----------|-----------|
| **Spoofing** | Attacker calls control API to arm/kill | A4 | Bearer token, TLS, device-bound token in secure storage, per-device revocation; control endpoints require auth + (live) typed confirm |
| **Spoofing** | Fake Polymarket host (DNS/MITM) | A1,A2 | **Official hosts only** (`clob.polymarket.com`, `gamma-api.polymarket.com`), TLS verify on, host allow-list, no user-supplied endpoint in live |
| **Tampering** | Compromised dependency runs in key-holding process | A1 | **Pin deps** (`requirements.pinned.txt`→lock, hashes), isolated container venv, verify `py-clob-client` is official (audit finding #1/#5) |
| **Tampering** | Altered runtime artifacts feed false KPIs | A5,A6 | Artifacts written only by the adapter; file perms; API is read-only on them; reconcile vs on-chain |
| **Repudiation** | "I didn't arm/kill that" | A4,A6 | Append-only audit log of control actions (who/when/from-device); `btc5m_events.jsonl` immutable append |
| **Information disclosure** | Key/secret leaked via logs, reports, or commits | A1,A3 | Key **never** logged/printed (audit confirms), **never** in any `05` contract, addresses **masked**, `.env` `chmod 600`, git-ignored, outside synced/backup folders |
| **Information disclosure** | Token leaks from phone | A4 | `expo-secure-store` (Keychain/Keystore), biometric gate, no token in JS bundle/logs, short TTL + refresh |
| **Denial of service** | API flooded; bot can't be controlled | A6 | Kill switch path prioritized/rate-limit-exempt; local kill also works on host; dead-man's switch independent of API |
| **Elevation of privilege** | Read user gains control rights | A4 | Separate scopes: **read token** vs **control token**; control requires the higher scope + (live) biometric/confirm |

## 4. Non-custodial key handling (hard rules)
1. `PM_PRIVATE_KEY` exists **only** in the Execution Adapter's process env on the
   operator's host. Prefer the **proxy-wallet model** (`PM_SIGNATURE_TYPE=2` +
   `PM_FUNDER`) so the signing key isn't the main holdings key (audit §Required #1).
2. The **mobile app never receives, stores, or transmits** a private key or seed.
   The app holds only the API base URL + bearer token.
3. **Dedicated, isolated wallet** funded with only losable capital
   (`SAFE_OPERATION.md` §1).
4. No contract, log, report, push notification, or API response may contain key
   material; addresses are masked (`05` §8). Automated secret-scan in CI
   (`gitleaks`/`run_secret_scanning`) blocks commits containing key-like strings.

## 5. Secrets policy
- Secrets via **env only** (`PM_*`), loaded from a `chmod 600 .env` kept outside
  synced/backup/git paths (audit finding #3). `.env.example` documents names only
  (`dashboard/docs/env.example`).
- Backend control token: generated server-side, delivered once to the device,
  stored in secure storage; rotatable; revocable per device.
- **No secrets in:** code, container images, CI logs, mobile bundle, crash
  reports, analytics.

## 6. Supply chain
- **Pin everything**, install in a clean container venv, verify
  `py-clob-client` resolves to the official `Polymarket/py-clob-client` before
  install, then freeze a lock with hashes (`SAFE_OPERATION.md` §2, audit #1/#5).
- Mobile: lockfile committed; minimize transitive deps; audit `expo-secure-store`
  / `expo-local-authentication` versions; no key-handling third-party SDKs.
- CI: dependency review + secret scanning on every change.

## 7. Guardrails (defense in depth)
| Guardrail | Where | Behavior |
|-----------|-------|----------|
| **Dry-run by default** | Adapter | No live order unless `mode=live` AND `armed=true` AND runbook ack |
| **Caps** | Risk Manager | `daily_max_loss_pct`, `max_trades_per_day`, `max_notional_usd`, `stop_loss_pct` enforced **in code**, verified to actually halt entries (runbook §4) |
| **Kill switch** | API + host | `/control/kill` sets a flag → block new entries, attempt safe close; host-side `btc5m_ctl.sh stop` / `btc5m_docker.sh down` always available |
| **Dead-man's switch** | Health + alerts | `dead_man_tripped` when process dead or `age_sec > dead_man_sec (30)` → push alert; a dead bot with an open position cannot self-stop (runbook §4) |
| **Arming gate** | API + mobile | Live arm requires control-scope token + **typed confirmation** + **biometric** + acknowledging the runbook checklist in-app |
| **Host allow-list** | Adapter | Only official Polymarket hosts; live mode forbids custom endpoints |

## 8. Mobile-specific security
- **Secure storage:** token in Keychain (iOS) / Keystore (Android) via
  `expo-secure-store`; never AsyncStorage/plaintext.
- **No key on device by default.** The product does **not** put `PM_PRIVATE_KEY`
  on the phone. *If* a future advanced mode ever signs on-device, it must be an
  explicit opt-in, hardware-backed, biometric-gated, and documented as higher
  risk — **not** in MVP/v1.
- **Biometric gate** (`expo-local-authentication`) required to: open the app
  control surface, arm live, and confirm a kill.
- **Transport:** TLS only; certificate handling per platform defaults; reject
  cleartext. Optional pinning for the API host.
- **Hygiene:** no secrets in logs/crash reports; screenshot/redaction on the
  Settings/arm screens; auto-lock on background; clear sensitive state on logout.

## 9. Incident response (aligned to runbook "Kill switch")
1. **Stop first, investigate second** (runbook). Hit kill (app or host).
2. If anomaly involves funds/keys: **move funds out of the trading wallet** and
   **rotate the key** (re-fund deliberately, runbook §5).
3. Revoke the affected control token; review the append-only control audit log.
4. Reconcile reported P&L vs on-chain before resuming.

## 10. Relationship to the existing audit
- The upstream-bot audit (`SECURITY_AUDIT.md`) covers key-handling, deps, and
  network for the *execution* layer; its **Required mitigations** are pre-reqs to
  any live run and are inherited here verbatim (dedicated wallet, pin+isolate,
  lock `.env`, read `subprocess`, dry-run first).
- This document **extends** that to the API + mobile + control plane (A4 token,
  scopes, mobile secure storage, arming gate, dead-man's switch) introduced by
  this product. Where they overlap, the audit + runbook win; do not contradict.
