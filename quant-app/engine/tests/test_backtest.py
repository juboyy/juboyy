"""Backtest smoke test over the small synthetic JSONL fixture + datasource/capture."""

import os
from pathlib import Path

import pytest

from engine.config import get_profile
from engine import backtest as bt
from engine.datasource import RecordedSource, MockSource, LiveBtcSpotSource
from engine.capture import CaptureRecorder

FIXTURE = Path(__file__).parent / "fixtures" / "backtest_small.jsonl"


def test_backtest_smoke_runs_and_reports_all_metrics():
    metrics = bt.run_backtest(str(FIXTURE), profile=get_profile("conservative"))
    # all 03 §9 metric keys present
    for key in [
        "win_rate", "break_even_hit_rate", "expectancy_per_trade",
        "sharpe_per_trade", "max_drawdown", "turnover_trades_per_day",
        "profit_factor", "cost_drag_pct", "cap_respect_pct",
    ]:
        assert key in metrics
    # 5 markets, each enters once with a settlement => 5 trades
    assert metrics["trades"] == 5
    assert 0.0 <= metrics["win_rate"] <= 1.0
    # cap-respect must be 100% on the small set
    assert metrics["cap_respect_pct"] == 100.0
    # report renders
    rep = bt.format_report(metrics)
    assert "BACKTEST REPORT" in rep


def test_backtest_deterministic():
    m1 = bt.run_backtest(str(FIXTURE))
    m2 = bt.run_backtest(str(FIXTURE))
    assert m1 == m2


def test_recorded_source_reads():
    src = RecordedSource(str(FIXTURE))
    snaps = list(src.snapshots())
    assert len(snaps) == 30
    assert snaps[0].market_slug.startswith("btc-updown")


def test_mock_source_deterministic():
    a = list(MockSource(n=10, seed=42).snapshots())
    b = list(MockSource(n=10, seed=42).snapshots())
    assert [s.btc_price_now for s in a] == [s.btc_price_now for s in b]
    assert len(a) == 10


def test_live_btc_spot_source_gated():
    with pytest.raises(NotImplementedError):
        LiveBtcSpotSource()


def test_capture_recorder_roundtrip(tmp_path):
    out = tmp_path / "cap.jsonl"
    rec = CaptureRecorder(str(out))
    snaps = list(MockSource(n=5).snapshots())
    n = rec.record_stream(snaps)
    assert n == 5
    assert rec.count() == 5
    # appends, not overwrites
    rec.record(snaps[0], settle_side="up")
    assert rec.count() == 6
