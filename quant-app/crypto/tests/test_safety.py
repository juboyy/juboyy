"""Guardrails: arming state machine, kill switch, dead-man's switch, redact()."""

import os

import pytest

from crypto.safety import (
    Arming,
    ArmingError,
    DeadMansSwitch,
    KillSwitch,
    mask_address,
    redact,
)


# --- Arming state machine ------------------------------------------------
def test_arming_starts_disarmed():
    a = Arming(confirm_token="CONFIRM-LIVE")
    assert a.armed is False
    assert a.state == "disarmed"


def test_cannot_arm_without_confirm_token():
    a = Arming(confirm_token="CONFIRM-LIVE")
    with pytest.raises(ArmingError):
        a.arm("wrong-token")
    assert a.armed is False  # still disarmed after a failed attempt


def test_arm_with_correct_token():
    a = Arming(confirm_token="CONFIRM-LIVE")
    assert a.arm("CONFIRM-LIVE") is True
    assert a.armed is True
    assert a.state == "armed"


def test_disarm_is_failsafe():
    a = Arming(confirm_token="CONFIRM-LIVE")
    a.arm("CONFIRM-LIVE")
    a.disarm()
    assert a.armed is False


def test_arming_repr_never_leaks_token():
    a = Arming(confirm_token="super-secret-confirm")
    assert "super-secret-confirm" not in repr(a)


def test_empty_confirm_token_rejected():
    with pytest.raises(ArmingError):
        Arming(confirm_token="")


# --- Kill switch ---------------------------------------------------------
def test_kill_blocks_new_entries_and_triggers_close():
    k = KillSwitch()
    assert k.allow_new_entry() is True
    assert k.should_close_all() is False
    k.kill("operator_kill")
    assert k.killed is True
    assert k.allow_new_entry() is False  # blocks new entries (03 §6)
    assert k.should_close_all() is True  # forces safe close (03 §6)
    with pytest.raises(RuntimeError):
        k.assert_can_enter()


def test_kill_is_sticky_until_reset():
    k = KillSwitch()
    k.kill()
    assert k.killed is True
    k.reset()
    assert k.killed is False
    assert k.allow_new_entry() is True


# --- Dead-man's switch ---------------------------------------------------
def test_dead_man_trips_when_heartbeat_stale():
    d = DeadMansSwitch(dead_man_sec=30)
    d.heartbeat(now=1000.0)
    assert d.tripped(now=1010.0) is False  # 10s old, fresh
    assert d.tripped(now=1041.0) is True  # 41s old > 30s


def test_dead_man_trips_when_process_dead():
    d = DeadMansSwitch(dead_man_sec=30)
    d.heartbeat(now=1000.0)
    d.set_process_running(False)
    # process dead ⇒ tripped even with a fresh heartbeat.
    assert d.tripped(now=1001.0) is True


def test_dead_man_trips_when_never_beat():
    d = DeadMansSwitch(dead_man_sec=30)
    assert d.tripped(now=1000.0) is True  # no heartbeat ever recorded
    assert d.age_sec(now=1000.0) is None


def test_dead_man_assert_ok_raises_when_tripped():
    d = DeadMansSwitch(dead_man_sec=30)
    d.heartbeat(now=1000.0)
    with pytest.raises(RuntimeError):
        d.assert_ok(now=1100.0)


# --- redact() ------------------------------------------------------------
def test_redact_masks_env_private_key(monkeypatch):
    secret = "0x" + "ab" * 31 + "cd"  # 64 hex chars
    monkeypatch.setenv("PM_PRIVATE_KEY", secret)
    leaky = f"connecting with key={secret} to host"
    out = redact(leaky)
    assert secret not in out
    assert "REDACTED" in out


def test_redact_masks_keylike_hex_even_without_env():
    # 64-hex blob is private-key shaped and must be masked even if not in env.
    blob = "deadbeef" * 8  # 64 hex chars
    out = redact(f"raw {blob} value")
    assert blob not in out


def test_redact_masks_named_assignments():
    out = redact('config: PM_API_SECRET="hunter2supersecret"')
    assert "hunter2supersecret" not in out


def test_redact_never_raises_on_arbitrary_input():
    assert isinstance(redact(None), str)
    assert isinstance(redact(12345), str)
    assert isinstance(redact({"a": 1}), str)


def test_redact_does_not_leak_in_exception_chain(monkeypatch):
    secret = "0x" + "11" * 32
    monkeypatch.setenv("PM_PRIVATE_KEY", secret)
    err = ValueError(f"boom key={secret}")
    assert secret not in redact(err)


def test_mask_address():
    assert mask_address("0x1234567890abcdef1234") == "0x1234…1234"
    assert mask_address(None) is None
    assert mask_address("short") == "short"
