"""
cli.py — command-line entry point for the convexity / resolution-edge scanner.

OFFLINE / ADVISORY. Reads a JSONL file of candidates, runs the chosen analyzer,
and writes a watchlist of gate-passers (ranked) to JSONL.

Usage:

    python -m scanner.cli scan <candidates.jsonl> [--analyzer heuristic|claude] \
        [--out watchlist.jsonl]

Default analyzer = heuristic (offline, no API key). The `claude` analyzer is
optional and requires the `anthropic` package + ANTHROPIC_API_KEY (model from
SCANNER_MODEL, default claude-haiku-4-5). The key is never logged.

Each input line is a JSON object with the OutcomeCandidate fields:
    market_slug, outcome, price, resolution_text, end_iso, top_ask_notional_usd
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from .analyzer import make_analyzer
from .contracts import OutcomeCandidate
from .scan import ScanParams, scan, to_jsonl


def _load_candidates(path: str) -> List[OutcomeCandidate]:
    candidates: List[OutcomeCandidate] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}")
            try:
                candidates.append(
                    OutcomeCandidate(
                        market_slug=str(obj["market_slug"]),
                        outcome=str(obj["outcome"]),
                        price=float(obj["price"]),
                        resolution_text=str(obj["resolution_text"]),
                        end_iso=str(obj.get("end_iso", "")),
                        top_ask_notional_usd=float(obj.get("top_ask_notional_usd", 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise SystemExit(f"{path}:{lineno}: bad candidate record: {exc}")
    return candidates


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scanner.cli",
        description="OFFLINE convexity / resolution-edge scanner (advisory watchlist only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="Scan a candidates JSONL file into a watchlist.")
    scan_p.add_argument("candidates", help="Path to candidates JSONL file.")
    scan_p.add_argument(
        "--analyzer",
        choices=["heuristic", "claude"],
        default="heuristic",
        help="Analyzer to use (default: heuristic, fully offline, no API key).",
    )
    scan_p.add_argument(
        "--out",
        default=None,
        help="Output watchlist JSONL path (default: stdout).",
    )
    scan_p.add_argument(
        "--claude-fallback",
        action="store_true",
        help="If --analyzer claude and SDK/key/API fails, fall back to heuristic.",
    )
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command != "scan":
        parser.error("unknown command")

    candidates = _load_candidates(args.candidates)

    if args.analyzer == "claude":
        analyzer = make_analyzer("claude", fallback_to_heuristic=args.claude_fallback)
    else:
        analyzer = make_analyzer("heuristic")

    items = scan(candidates, analyzer, ScanParams())
    output = to_jsonl(items)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(output)
            if output:
                fh.write("\n")
    else:
        if output:
            sys.stdout.write(output + "\n")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
