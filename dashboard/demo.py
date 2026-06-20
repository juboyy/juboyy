"""
demo.py — Generates realistic synthetic runtime artifacts so the dashboard
can be demonstrated without a live bot.

It writes the SAME files the real `5min-btc-polymarket` bot produces, in the
same shape (see scripts/test_btc_5m_session_exit_sl.py and btc5m_ctl.sh):

  runtime/btc5m.meta.json                 -> ctl.sh metadata (start ts, profile…)
  runtime/btc5m.pid                       -> process id
  runtime/btc5m_<profile>_<UTC>.log       -> ONE session report JSON each
  runtime/latest.log                      -> points at the newest session log

Each session report mirrors the runner's real schema: started_at, params,
attempts[] (heartbeats with clob_up_ask / clob_down_ask / seconds_left /
gamma_up / gamma_down / min_spread), opened{}, closed{},
realized_cashflow_pnl_usdc, result, finished_at.

Usage:
  python demo.py [--runtime DIR] [--profile conservative|aggressive]
                 [--sessions N] [--running | --stopped]
"""

from __future__ import annotations

import argparse
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tx():
    return "0x" + "".join(random.choice("0123456789abcdef") for _ in range(12))


def build_session_report(start, profile, threshold, stake):
    """Produce one full session report matching the runner's output schema."""
    slug = f"btc-updown-5m-{start.strftime('%Y%m%d-%H%M')}"
    market_end = start + timedelta(minutes=5)

    params = {
        "profile": profile, "threshold": threshold, "stake_usd": stake,
        "stop_loss_pct": 0.25 if profile == "conservative" else 0.30,
        "exit_before_sec": 20, "min_entry_seconds_left": 60,
        "entry_timeout_min": 60, "poll_sec": 5,
        "close_retry_max": 3, "close_retry_delay_sec": 1.5, "execute": True,
    }

    # Decide up front whether momentum carries one side over the threshold by
    # the close (~60% of sessions do), then drift the gamma/asks accordingly.
    entered = random.random() < 0.6
    strong_up = random.random() < 0.5
    target = round(random.uniform(threshold + 0.02, 0.92), 3) if entered \
        else round(random.uniform(0.50, threshold - 0.03), 3)

    attempts = []
    sec = random.randint(180, 240)
    g_strong = round(random.uniform(0.40, 0.55), 3)
    steps = max(1, sec // 35)
    step_i = 0
    while sec > 25:
        # Strong side trends toward `target` as the close approaches.
        frac = step_i / max(1, steps)
        g_strong = round(min(0.95, g_strong + (target - g_strong) * frac
                             + random.uniform(-0.02, 0.02)), 3)
        g_weak = round(max(0.03, 1 - g_strong + random.uniform(-0.02, 0.02)), 3)
        g_up, g_dn = (g_strong, g_weak) if strong_up else (g_weak, g_strong)
        up_ask = round(min(0.98, max(0.03, g_up + random.uniform(-0.02, 0.02))), 3)
        dn_ask = round(min(0.98, max(0.03, g_dn + random.uniform(-0.02, 0.02))), 3)
        attempts.append({
            "ts": _iso(start + timedelta(seconds=240 - sec)),
            "slug": slug, "status": "heartbeat",
            "gamma_up": g_up, "gamma_down": g_dn,
            "clob_up_ask": up_ask, "clob_down_ask": dn_ask,
            "seconds_left": sec, "min_spread": round(random.uniform(0.005, 0.025), 3),
        })
        sec -= random.randint(20, 45)
        step_i += 1

    last = attempts[-1]
    side = "UP" if strong_up else "DOWN"
    entry = last["clob_up_ask"] if strong_up else last["clob_down_ask"]
    entered = entry >= threshold

    report = {
        "started_at": _iso(start),
        "params": params,
        "attempts": attempts,
    }

    if not entered:
        attempts.append({
            "ts": _iso(start + timedelta(minutes=4, seconds=40)),
            "slug": slug, "status": "skip_price_below_threshold",
            "threshold": threshold, "clob_up_ask": last["clob_up_ask"],
            "clob_down_ask": last["clob_down_ask"], "seconds_left": 30,
        })
        report["result"] = "no_entry_timeout"
        report["finished_at"] = _iso(market_end)
        return report, start

    shares = round(stake / max(0.01, entry), 2)
    cost = round(shares * entry, 2)
    win_p = 0.50 + (entry - 0.7) * 0.4
    win = random.random() < max(0.4, min(0.78, win_p))
    if win:
        close_price = round(min(1.0, entry + random.uniform(0.1, 0.3)), 3)
        close_status, close_reason = "settled_win", "market_resolved_in_favor"
    else:
        close_price = round(max(0.0, entry - random.uniform(0.2, entry)), 3)
        close_status, close_reason = "settled_loss", "stop_loss_or_adverse_resolution"
    close_usdc = round(shares * close_price, 2)
    pnl = round(close_usdc - cost, 3)

    report["opened"] = {
        "opened_at": _iso(start + timedelta(minutes=3)),
        "market_slug": slug, "market_end_iso": _iso(market_end),
        "side": side, "token_id": _tx(), "entry_price": entry,
        "shares": shares, "cost_usdc": cost,
        "open_order_id": _tx(), "open_tx": _tx(),
    }
    report["closed"] = {
        "close_reason": close_reason,
        "closed_at": _iso(market_end - timedelta(seconds=20)),
        "close_success": True, "close_status": close_status,
        "close_order_id": _tx(), "close_tx": _tx(),
        "close_shares": shares, "close_usdc": close_usdc,
    }
    report["realized_cashflow_pnl_usdc"] = pnl
    report["result"] = "done"
    report["finished_at"] = _iso(market_end)
    return report, start


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", default=str(Path(__file__).parent / "runtime"))
    ap.add_argument("--profile", default="conservative",
                    choices=["conservative", "aggressive"])
    ap.add_argument("--sessions", "--trades", dest="sessions", type=int, default=16)
    ap.add_argument("--running", action="store_true", default=True)
    ap.add_argument("--stopped", dest="running", action="store_false")
    args = ap.parse_args()

    rt = Path(args.runtime)
    rt.mkdir(parents=True, exist_ok=True)
    random.seed()

    threshold, stake = 0.70, 5.0
    now = datetime.now(timezone.utc)
    start0 = now - timedelta(minutes=6 * args.sessions + 10)

    # Each 5m market => one session log file.
    newest_log = None
    t = start0
    for _ in range(args.sessions):
        report, sstart = build_session_report(t, args.profile, threshold, stake)
        log_file = rt / f"btc5m_{args.profile}_{sstart.strftime('%Y%m%dT%H%M%S')}.log"
        log_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        newest_log = log_file
        t += timedelta(minutes=6)
        if t > now:
            break

    # ctl.sh metadata + pid
    meta = {
        "start_ts": _iso(start0),
        "pid": os.getpid() if args.running else 999999,
        "profile": args.profile, "threshold": threshold, "stake_usd": stake,
        "stop_loss_pct": 0.25 if args.profile == "conservative" else 0.30,
        "exit_before_sec": 20, "min_entry_seconds_left": 60,
        "entry_timeout_min": 60, "poll_sec": 5, "execute": True,
        "log_path": str(newest_log) if newest_log else None,
    }
    (rt / "btc5m.meta.json").write_text(json.dumps(meta, indent=2))
    (rt / "btc5m.pid").write_text(str(meta["pid"]))

    # latest.log -> newest session
    latest = rt / "latest.log"
    if newest_log:
        try:
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            latest.symlink_to(newest_log.name)
        except OSError:
            latest.write_text(newest_log.read_text())

    print(f"demo data written to {rt} ({args.sessions} sessions, running={args.running})")


if __name__ == "__main__":
    main()
