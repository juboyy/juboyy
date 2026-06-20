"""
demo.py — Generates realistic synthetic runtime artifacts so the dashboard
can be demonstrated without a live bot.

It writes the same files the real `5min-btc-polymarket` bot produces:
  runtime/btc5m.meta.json, runtime/btc5m.pid,
  runtime/btc5m_events.jsonl, runtime/btc5m_signal.json,
  runtime/latest.log

Usage:
  python demo.py [--runtime DIR] [--profile conservative|aggressive]
                 [--trades N] [--running]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def gen_trade(ts, profile, threshold, stake):
    side = random.choice(["UP", "DOWN"])
    btc_move = round(random.uniform(60, 130), 1)
    skew = round(random.uniform(0.55, 0.97), 3)
    sl = random.randint(95, 145)
    entry = round(random.uniform(0.58, 0.82), 3)
    # Outcome: edge toward wins when move strong + skew aligned.
    win_p = 0.50 + min(0.25, (btc_move - 70) / 240) + (skew - 0.6) * 0.3
    win = random.random() < max(0.35, min(0.8, win_p))
    cost = round(stake, 2)
    if win:
        pnl = round(cost * (1.0 / entry - 1.0) * random.uniform(0.7, 1.0), 3)
        close_status = "settled_win"
    else:
        pnl = round(-cost * random.uniform(0.6, 1.0), 3)
        close_status = "settled_loss"
    slug = f"btc-updown-5m-{ts.strftime('%Y%m%d-%H%M')}"
    return {
        "ts": _iso(ts),
        "profile": profile,
        "result": "ok",
        "opened": {
            "side": side,
            "market_slug": slug,
            "cost_usdc": cost,
            "open_tx": "0x" + "".join(random.choice("0123456789abcdef") for _ in range(12)),
        },
        "closed": {
            "close_success": True,
            "close_status": close_status,
            "close_skipped": False,
            "close_tx": "0x" + "".join(random.choice("0123456789abcdef") for _ in range(12)),
        },
        "realized_cashflow_pnl_usdc": pnl,
        "btc_move_usd": btc_move,
        "skew": skew,
        "seconds_left_at_entry": sl,
        "entry_price": entry,
        "threshold_price": threshold,
        "stake_usd": stake,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", default=str(Path(__file__).parent / "runtime"))
    ap.add_argument("--profile", default="conservative",
                    choices=["conservative", "aggressive"])
    ap.add_argument("--trades", type=int, default=18)
    ap.add_argument("--running", action="store_true", default=True)
    ap.add_argument("--stopped", dest="running", action="store_false")
    args = ap.parse_args()

    rt = Path(args.runtime)
    rt.mkdir(parents=True, exist_ok=True)
    random.seed()

    threshold = 0.70
    stake = 5.0
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=3, minutes=20)

    # meta + pid
    meta = {
        "start_ts": _iso(start),
        "pid": os.getpid() if args.running else 999999,
        "profile": args.profile,
        "threshold": threshold,
        "stake_usd": stake,
        "stop_loss_pct": 0.25 if args.profile == "conservative" else 0.30,
        "exit_before_sec": 20,
        "min_entry_seconds_left": 60,
        "entry_timeout_min": 60,
        "poll_sec": 5,
        "execute": True,
        "log_path": str(rt / "latest.log"),
    }
    (rt / "btc5m.meta.json").write_text(json.dumps(meta, indent=2))
    (rt / "btc5m.pid").write_text(str(meta["pid"]))

    # events spread across the session, every ~10 min
    events = []
    t = start + timedelta(minutes=8)
    for _ in range(args.trades):
        events.append(gen_trade(t, args.profile, threshold, stake))
        t += timedelta(minutes=random.randint(8, 14))
        if t > now:
            break
    with open(rt / "btc5m_events.jsonl", "w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")

    # live signal snapshot
    sl = random.randint(40, 175)
    up = round(random.uniform(0.40, 0.75), 3)
    down = round(1 - up + random.uniform(-0.05, 0.05), 3)
    signal = {
        "ts": _iso(now),
        "btc_price": round(random.uniform(98000, 104000), 1),
        "btc_move_usd": round(random.uniform(20, 120), 1),
        "seconds_left": sl,
        "up_ask": up,
        "down_ask": max(0.0, down),
        "skew": round(max(up, down) / max(0.001, up + down), 3),
        "market_slug": f"btc-updown-5m-{now.strftime('%Y%m%d-%H%M')}",
        "in_entry_window": 60 <= sl <= 150,
    }
    (rt / "btc5m_signal.json").write_text(json.dumps(signal, indent=2))

    # human log tail
    lines = [f"[{_iso(start)}] session start profile={args.profile} execute=True"]
    for e in events[-12:]:
        o = e["opened"]
        lines.append(
            f"[{e['ts']}] ENTER {o['side']} move=${e['btc_move_usd']} "
            f"skew={e['skew']} sl={e['seconds_left_at_entry']}s "
            f"cost={o['cost_usdc']} -> pnl={e['realized_cashflow_pnl_usdc']}"
        )
    lines.append(json.dumps(events[-1]))
    log_file = rt / f"btc5m_{args.profile}_{start.strftime('%Y%m%dT%H%M%S')}.log"
    log_file.write_text("\n".join(lines) + "\n")
    latest = rt / "latest.log"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(log_file.name)
    except OSError:
        latest.write_text("\n".join(lines) + "\n")

    print(f"demo data written to {rt} ({len(events)} trades, running={args.running})")


if __name__ == "__main__":
    main()
