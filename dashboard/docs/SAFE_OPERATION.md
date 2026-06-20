# Safe Operation Runbook — 5min BTC Polymarket

A hard-nosed checklist to operate the `Novals83/5min-btc-polymarket` bot without
getting wrecked, with the dashboard as your watchtower. Read
`SECURITY_AUDIT.md` first.

## 0. Before anything (capital & legal)

- [ ] Decide the **loss budget**: the amount you can lose to zero with no change
      to your life. That is your entire bankroll for this — not a cent more.
- [ ] Confirm Polymarket is **permitted in your jurisdiction**. US persons are
      restricted (CFTC). Using a VPN to bypass can get funds frozen.
- [ ] Understand you will owe **tax reporting** on potentially hundreds of trades.

## 1. Wallet & key custody

- [ ] Create a **brand-new, dedicated wallet**. Never reuse a wallet that holds
      other funds.
- [ ] Fund it with **only the loss budget** from step 0.
- [ ] Use the Polymarket **proxy-wallet** model: set `PM_SIGNATURE_TYPE=2` and
      `PM_FUNDER=<your funder/proxy address>`.
- [ ] Put the key in `.env` (see `.env.example`), then:
      ```bash
      chmod 600 .env
      ```
- [ ] Confirm `.env` is git-ignored and lives **outside** any cloud-synced or
      backed-up folder.

## 2. Dependency & environment isolation

- [ ] Run **only inside the container** (`scripts/btc5m_docker.sh up`), never on
      your host Python.
- [ ] **Pin** dependencies — do not `pip install` floating latest. Start from
      `requirements.pinned.txt`, verify `py-clob-client` is the official
      Polymarket package, then freeze exact versions (ideally with hashes):
      ```bash
      pip install -r requirements.pinned.txt
      pip freeze > requirements.lock.txt   # commit this lock
      ```
- [ ] Read the `subprocess` usage in `test_btc_5m_session_exit_sl.py` and
      confirm it never shells out with market/network input.

## 3. Dry-run validation (no `--execute`)

- [ ] Run the runner **without** `--execute` for a real sample window
      (days, across different volatility regimes):
      ```bash
      python scripts/test_btc_5m_session_exit_sl.py --profile conservative \
        --threshold 0.70 --stake-usd 4 --stop-loss-pct 0.25 \
        --exit-before-sec 20 --min-entry-seconds-left 60 --poll-sec 5
      ```
- [ ] Point the **dashboard** at the runtime dir and watch win rate, drawdown,
      and risk-cap usage build up:
      ```bash
      cd dashboard
      python app.py --runtime /workspace/.../runtime \
                    --config  /workspace/.../config/btc_5m_profiles.yaml
      ```
- [ ] **Only proceed if** the simulated edge survives spread + slippage + gas and
      the worst-case drawdown is inside your loss budget. If win rate < ~70% at
      a 0.70 entry, the math is negative — stop.

## 4. Go live — smallest possible size

- [ ] Start with the **conservative** profile and the **minimum** stake.
- [ ] Keep `daily_max_loss_pct` and `max_trades_per_day` tight, and verify in the
      dashboard that the **risk gauges actually stop new entries** when a cap is
      hit (don't trust the YAML — confirm the behavior).
- [ ] Add a **dead-man's switch**: an alert when the bot process dies (the
      dashboard shows `PARADO` / stale signal). A dead bot with an **open
      position** cannot fire its own stop-loss.

## 5. Daily operating loop

1. Check dashboard: bot **RODANDO**, profile correct, params correct.
2. Watch **loss-cap** and **trades/day** gauges — stop the day if either nears
   100%.
3. Reconcile reported P&L against actual on-chain balance periodically.
4. Rotate the key and re-fund deliberately; never top up impulsively after losses.

## Kill switch

```bash
scripts/btc5m_ctl.sh stop        # stop the session
scripts/btc5m_docker.sh down     # tear down the container
```

If anything looks wrong — unexpected fills, the bot touching a wrong market,
balance moving without a logged trade — **stop first, investigate second**, and
move funds out of the trading wallet.

---

*Operational/educational tooling, not financial advice. The dashboard observes;
it never trades. The risk and the decision are yours.*
