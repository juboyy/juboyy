"""
cli.py — small CLI for the engine.

Commands:
  decide <snapshot.json>   — run the spine on one snapshot, print Signal+Decision.
  backtest <data.jsonl>    — replay recorded JSONL, print the `03 §9` report.
  capture <snapshot.json>  — append a normalized snapshot to the capture JSONL.

Run:  python -m engine.cli decide path/to/snapshot.json --profile conservative

Stdlib only. The CLI is an I/O shell around the pure spine.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .contracts import MarketSnapshot
from .config import get_profile
from . import indicators, signal_engine as signal_mod, risk as risk_mod, backtest as backtest_mod
from .capture import CaptureRecorder, DEFAULT_PATH


def _load_snapshot(path: str) -> MarketSnapshot:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return MarketSnapshot.from_dict(data)


def cmd_decide(args) -> int:
    profile = get_profile(args.profile)
    snap = _load_snapshot(args.snapshot)
    features = indicators.compute(snap, history=[], profile=profile)
    sig, dec = signal_mod.evaluate_and_decide(features, snap, profile, risk_allows=True)
    out = {
        "features": features.to_dict(),
        "signal": sig.to_dict(),
        "decision": dec.to_dict(),
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_backtest(args) -> int:
    profile = get_profile(args.profile)
    metrics = backtest_mod.run_backtest(args.data, profile=profile)
    print(backtest_mod.format_report(metrics))
    if args.json:
        print(json.dumps(metrics, indent=2))
    return 0


def cmd_capture(args) -> int:
    snap = _load_snapshot(args.snapshot)
    recorder = CaptureRecorder(args.out)
    rec = recorder.record(snap, settle_side=args.settle_side)
    print(f"captured 1 record to {args.out} (total {recorder.count()})")
    print(json.dumps(rec))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="engine", description="deterministic trading engine CLI")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("decide", help="run the spine on one snapshot JSON")
    d.add_argument("snapshot")
    d.add_argument("--profile", default="conservative")
    d.set_defaults(func=cmd_decide)

    b = sub.add_parser("backtest", help="replay a recorded JSONL dataset")
    b.add_argument("data")
    b.add_argument("--profile", default="conservative")
    b.add_argument("--json", action="store_true", help="also print metrics JSON")
    b.set_defaults(func=cmd_backtest)

    c = sub.add_parser("capture", help="append a normalized snapshot to JSONL")
    c.add_argument("snapshot")
    c.add_argument("--out", default=DEFAULT_PATH)
    c.add_argument("--settle-side", default=None, help="realized outcome up/down (backtest label)")
    c.set_defaults(func=cmd_capture)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
