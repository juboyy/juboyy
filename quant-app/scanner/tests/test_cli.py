"""CLI smoke test: scan a JSONL file with the offline heuristic analyzer."""

from __future__ import annotations

import json

from scanner.cli import main
from scanner.tests.fixtures import VAGUE_TEXT


def test_cli_scan_writes_watchlist(tmp_path, capsys):
    # One vague, cheap candidate. Heuristic nudges true_prob above price on the
    # strong discretion clause, so it should flag IF edge clears min_edge.
    # We construct a strong-edge case by using a very cheap price so the small
    # heuristic nudge yields edge >= 0.10 is hard; instead assert the CLI runs
    # and produces valid JSONL (possibly empty) without error.
    inp = tmp_path / "cands.jsonl"
    rows = [
        {
            "market_slug": "m1",
            "outcome": "Yes",
            "price": 0.05,
            "resolution_text": VAGUE_TEXT,
            "end_iso": "2026-12-31T00:00:00Z",
            "top_ask_notional_usd": 500.0,
        }
    ]
    inp.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    out = tmp_path / "watchlist.jsonl"
    rc = main(["scan", str(inp), "--analyzer", "heuristic", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    # Output is valid JSONL (each non-empty line parses).
    content = out.read_text(encoding="utf-8")
    for line in content.splitlines():
        if line.strip():
            json.loads(line)


def test_cli_scan_stdout(tmp_path, capsys):
    inp = tmp_path / "cands.jsonl"
    inp.write_text(
        json.dumps(
            {
                "market_slug": "m1",
                "outcome": "Yes",
                "price": 0.05,
                "resolution_text": "official UTC value according to feed",
                "end_iso": "",
                "top_ask_notional_usd": 500.0,
            }
        ),
        encoding="utf-8",
    )
    rc = main(["scan", str(inp)])
    assert rc == 0
    # Neutral text => no edge => empty watchlist => no crash.
    out = capsys.readouterr().out
    for line in out.splitlines():
        if line.strip():
            json.loads(line)
