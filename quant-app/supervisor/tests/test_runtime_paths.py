"""runtime_paths: JSON-lines writer appends valid one-line records to the right files."""

import json

from runtime_paths import (
    ALL_STREAMS,
    JsonlLogger,
    RuntimePaths,
)


def test_paths_layout(tmp_path):
    paths = RuntimePaths.under(str(tmp_path)).ensure()
    assert paths.root.name == "runtime"
    assert paths.events.name == "events.jsonl"
    assert paths.orders.name == "orders.jsonl"
    assert paths.equity.name == "equity.jsonl"
    assert paths.commands.name == "commands.jsonl"
    assert {p.name for p in (paths.events, paths.orders, paths.equity, paths.commands)} == set(ALL_STREAMS)


def test_writes_one_json_line_per_record(tmp_path):
    paths = RuntimePaths.under(str(tmp_path))
    logger = JsonlLogger(paths)
    logger.event({"kind": "decision", "strategy": "s"})
    logger.order({"order_id": "ord_1"})
    logger.equity_sample({"pnl_today": 0.0})
    logger.command({"kind": "kill"})
    logger.close()

    for path, expect_key in (
        (paths.events, "kind"),
        (paths.orders, "order_id"),
        (paths.equity, "pnl_today"),
        (paths.commands, "kind"),
    ):
        lines = path.read_text().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert expect_key in rec
        # Formatter injects ts + level automatically.
        assert "ts" in rec and "level" in rec


def test_unknown_stream_rejected(tmp_path):
    paths = RuntimePaths.under(str(tmp_path))
    try:
        paths.path_for("bogus.jsonl")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown stream")
