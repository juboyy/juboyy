"""End-to-end tests for capture_runner against a fake injected source writing to
a temp runtime dir. Asserts the JSONL records carry the right MarketSnapshot
fields and that btc_price_open is held within an interval and resets across one.
"""

from __future__ import annotations

import json

from engine.capture import CaptureRecorder
from engine.contracts import MarketSnapshot
from engine.datasource import MarketSnapshotSource

from feeds import capture_runner


class FakeSource(MarketSnapshotSource):
    """Deterministic injectable source: yields a queued list of snapshots."""

    def __init__(self, snaps):
        self._snaps = list(snaps)
        self._i = 0

    def poll_once(self):
        if self._i >= len(self._snaps):
            return None
        snap = self._snaps[self._i]
        self._i += 1
        return snap

    def snapshots(self):
        s = self.poll_once()
        if s is not None:
            yield s


def _snap(ts, slug, secs, up_ask, btc_open, btc_now):
    return MarketSnapshot(
        ts=ts,
        market_slug=slug,
        seconds_left=secs,
        clob_up_ask=up_ask,
        clob_down_ask=round(1 - up_ask, 2),
        gamma_up=up_ask,
        gamma_down=round(1 - up_ask, 2),
        min_spread=0.02,
        btc_price_open=btc_open,
        btc_price_now=btc_now,
        age_sec=1,
        source="clob+gamma",
    )


def _read_jsonl(path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_capture_writes_records_with_snapshot_fields(tmp_path):
    snaps = [
        _snap("2026-06-20T18:01:00Z", "btc-updown-1405", 240, 0.60, 64900.0, 64900.0),
        _snap("2026-06-20T18:02:00Z", "btc-updown-1405", 180, 0.62, 64900.0, 64950.0),
    ]
    path = tmp_path / "captured_snapshots.jsonl"
    rec = CaptureRecorder(str(path))
    src = FakeSource(snaps)

    written = capture_runner.run_capture(
        src, rec, duration=0, poll_sec=0,
        sleep_fn=lambda s: None, now_fn=lambda: 0.0, log=lambda m: None,
    )
    # duration=0 with now_fn constant -> exactly one poll
    assert written == 1
    rows = _read_jsonl(path)
    assert len(rows) == 1
    r = rows[0]
    for field in (
        "ts", "market_slug", "seconds_left", "clob_up_ask", "clob_down_ask",
        "gamma_up", "gamma_down", "min_spread", "btc_price_open",
        "btc_price_now", "age_sec", "source", "schema_version",
    ):
        assert field in r
    assert r["market_slug"] == "btc-updown-1405"
    assert r["source"] == "clob+gamma"


def test_capture_once_flag(tmp_path):
    snaps = [_snap("2026-06-20T18:01:00Z", "btc-updown-1405", 240, 0.6, 64900.0, 64900.0)]
    path = tmp_path / "cap.jsonl"
    rec = CaptureRecorder(str(path))
    written = capture_runner.run_capture(
        FakeSource(snaps), rec, once=True,
        sleep_fn=lambda s: None, log=lambda m: None,
    )
    assert written == 1
    assert len(_read_jsonl(path)) == 1


def test_dry_run_writes_nothing(tmp_path):
    snaps = [_snap("2026-06-20T18:01:00Z", "btc-updown-1405", 240, 0.6, 64900.0, 64900.0)]
    path = tmp_path / "cap.jsonl"
    rec = CaptureRecorder(str(path))
    written = capture_runner.run_capture(
        FakeSource(snaps), rec, once=True, dry=True,
        sleep_fn=lambda s: None, log=lambda m: None,
    )
    assert written == 0
    assert not path.exists()


def test_btc_price_open_constant_within_interval_resets_across(tmp_path):
    # interval A (1405): open stays 64900 across 3 polls; interval B (1410): resets
    snaps = [
        _snap("2026-06-20T18:01:00Z", "btc-updown-1405", 240, 0.60, 64900.0, 64900.0),
        _snap("2026-06-20T18:02:00Z", "btc-updown-1405", 180, 0.61, 64900.0, 64950.0),
        _snap("2026-06-20T18:04:00Z", "btc-updown-1405", 60, 0.63, 64900.0, 65010.0),
        _snap("2026-06-20T18:06:00Z", "btc-updown-1410", 240, 0.55, 65020.0, 65020.0),
        _snap("2026-06-20T18:07:00Z", "btc-updown-1410", 180, 0.56, 65020.0, 65080.0),
    ]
    path = tmp_path / "cap.jsonl"
    rec = CaptureRecorder(str(path))

    # drive exactly len(snaps) polls via a stepping clock. now_fn is read once
    # at start and once per post-poll duration check, so an N-poll run needs the
    # Nth check to be the first >= duration. With ticks 0,1,2,... that is
    # duration == len(snaps) - 1 producing... use a generous duration and let the
    # source exhaust by stopping when it returns None.
    written = capture_runner.run_capture(
        FakeSource(snaps), rec,
        max_polls=len(snaps), poll_sec=1,
        sleep_fn=lambda s: None, now_fn=lambda: 0.0,
        log=lambda m: None,
    )
    rows = _read_jsonl(path)
    assert written == len(snaps)
    interval_a = [r for r in rows if r["market_slug"] == "btc-updown-1405"]
    interval_b = [r for r in rows if r["market_slug"] == "btc-updown-1410"]
    # held constant within each interval
    assert {r["btc_price_open"] for r in interval_a} == {64900.0}
    assert {r["btc_price_open"] for r in interval_b} == {65020.0}
    # reset across the boundary
    assert interval_a[0]["btc_price_open"] != interval_b[0]["btc_price_open"]


def test_capture_survives_source_error(tmp_path):
    class Boom(MarketSnapshotSource):
        def poll_once(self):
            raise RuntimeError("feed exploded")

        def snapshots(self):
            raise RuntimeError("feed exploded")

    path = tmp_path / "cap.jsonl"
    rec = CaptureRecorder(str(path))
    # must not raise; writes nothing
    written = capture_runner.run_capture(
        Boom(), rec, once=True, sleep_fn=lambda s: None, log=lambda m: None,
    )
    assert written == 0
