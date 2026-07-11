"""Engine bridge behaviour + security invariants (05/06): dry-run, no keys."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_QUANT_APP = Path(__file__).resolve().parent.parent.parent
if str(_QUANT_APP) not in sys.path:
    sys.path.insert(0, str(_QUANT_APP))

from backend.engine_bridge import EngineBridge, ValidationError  # noqa: E402


def test_mocksource_pipeline_produces_full_signal():
    b = EngineBridge(runtime_dir=None, profile="conservative")
    sig = b.signal().to_dict()
    # The Signal reconstructs the full score breakdown (05 §3).
    assert sig["weights"]["w_mom"] == 0.35
    assert sig["model_version"] == "rule-1.0"
    dec = b.decision().to_dict()
    assert dec["mode"] == "dry_run"
    assert dec["armed"] is False


def test_arm_disarm_flips_flags_only():
    b = EngineBridge(runtime_dir=None, profile="conservative")
    assert b.armed is False and b.mode == "dry_run"
    b.arm(confirm="ARM LIVE", runbook_ack=True)
    assert b.armed is True and b.mode == "live"
    b.disarm()
    assert b.armed is False and b.mode == "dry_run"


def test_arm_rejects_bad_token():
    b = EngineBridge(runtime_dir=None, profile="conservative")
    try:
        b.arm(confirm="WRONG", runbook_ack=True)
        assert False, "expected ValidationError"
    except ValidationError as exc:
        assert "ARM LIVE" in str(exc) or exc.detail


def test_killed_blocks_entries_and_empties_positions():
    b = EngineBridge(runtime_dir=None, profile="conservative")
    res = b.kill(confirm="KILL")
    assert res["killed"] is True
    assert b.killed is True
    assert b.positions() == []
    # A decision under kill is vetoed (risk_reason killed), never an enter.
    dec = b.decision().to_dict()
    assert dec["action"] != "enter"
    assert dec["risk_reason"] in ("killed", "kill", None) or dec["risk_verdict"] == "veto"


def test_funder_address_is_masked_never_raw():
    raw = "0x1234567890abcdef1234567890abcdef12345678"
    b = EngineBridge(runtime_dir=None, profile="conservative", funder_address=raw)
    acct = b.equity().to_dict()
    masked = acct["funder_address_masked"]
    assert masked != raw
    assert "…" in masked
    assert raw not in json.dumps(acct)


def test_no_private_key_in_any_payload(monkeypatch):
    # If a key were ever present in env, it must never surface in API output.
    secret = "a" * 64
    monkeypatch.setenv("PM_PRIVATE_KEY", secret)
    b = EngineBridge(runtime_dir=None, profile="conservative")
    blob = json.dumps([
        b.status().to_dict(), b.signal().to_dict(), b.decision().to_dict(),
        b.risk().to_dict(), b.equity().to_dict(), b.config(), b.health(),
    ], default=str)
    assert secret not in blob


def test_config_validation_detail_lists_offending_field():
    b = EngineBridge(runtime_dir=None, profile="conservative")
    try:
        b.update_config({"threshold_price": 0.1})
        assert False
    except ValidationError as exc:
        assert "threshold_price" in exc.detail


def test_recordedsource_runtime_snapshots(tmp_path):
    # Write a JSONL snapshot fixture; bridge should read it via RecordedSource.
    snap = {
        "schema_version": "1.0", "ts": "2026-06-20T14:00:00Z",
        "market_slug": "btc-updown-test", "seconds_left": 120,
        "clob_up_ask": 0.71, "clob_down_ask": 0.30, "age_sec": 2, "source": "clob+gamma",
    }
    fp = tmp_path / "snapshots.jsonl"
    fp.write_text(json.dumps(snap) + "\n", encoding="utf-8")
    b = EngineBridge(runtime_dir=str(tmp_path), profile="conservative")
    out = b.snapshot().to_dict()
    assert out["market_slug"] == "btc-updown-test"
    assert out["source"] == "clob+gamma"


def test_kill_writes_command_file(tmp_path):
    b = EngineBridge(runtime_dir=str(tmp_path), profile="conservative")
    b.kill(confirm="KILL")
    cmd = (tmp_path / "commands.jsonl")
    assert cmd.exists()
    rec = json.loads(cmd.read_text().splitlines()[-1])
    assert rec["command"] == "kill"
