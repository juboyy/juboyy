"""Auth enforcement + control endpoints (08 §2/§4): dry-run is never bypassed."""

from __future__ import annotations

from .conftest import READ_TOKEN, CONTROL_TOKEN

CONTROL_PATHS = [
    ("/control/start", {"profile": "conservative", "mode": "dry_run"}),
    ("/control/stop", {}),
    ("/control/arm", {"confirm": "ARM LIVE", "runbook_ack": True}),
    ("/control/disarm", {}),
    ("/control/profile", {"profile": "aggressive"}),
    ("/control/config", {"params": {"threshold_price": 0.72}}),
]


def test_control_requires_token(client):
    for path, body in CONTROL_PATHS + [("/control/kill", {"confirm": "KILL"})]:
        st, b = client.post(path, body, token=None)
        assert st == 401, path
        assert b["error"]["code"] == "unauthorized"


def test_control_rejects_wrong_token(client):
    st, b = client.post("/control/stop", {}, token="not-the-token")
    assert st == 401
    assert b["error"]["code"] == "unauthorized"


def test_read_token_is_not_control_token(client):
    # A read token must not unlock control endpoints.
    st, b = client.post("/control/stop", {}, token=READ_TOKEN)
    assert st == 401


def test_kill_returns_202(client):
    st, b = client.post("/control/kill", {"confirm": "KILL"}, token=CONTROL_TOKEN)
    assert st == 202
    d = b["data"]
    assert d["killed"] is True
    assert d["blocking_new_entries"] is True
    assert "positions_closed" in d and "positions_close_skipped" in d


def test_kill_bad_confirm_rejected(client):
    st, b = client.post("/control/kill", {"confirm": "nope"}, token=CONTROL_TOKEN)
    assert st == 400
    assert b["error"]["code"] == "validation"


def test_arm_requires_exact_confirm_and_runbook(client):
    st, b = client.post("/control/arm", {"confirm": "ARM LIVE", "runbook_ack": False}, token=CONTROL_TOKEN)
    assert st == 400
    assert b["error"]["code"] == "validation"
    st, b = client.post("/control/arm", {"confirm": "wrong", "runbook_ack": True}, token=CONTROL_TOKEN)
    assert st == 400


def test_start_live_requires_armed(client, server):
    # Not armed → live start is forbidden (not_armed). Dry-run never bypassed.
    st, b = client.post("/control/start", {"profile": "conservative", "mode": "live"}, token=CONTROL_TOKEN)
    assert st == 403
    assert b["error"]["code"] == "not_armed"
    # Bridge stays in dry-run / disarmed.
    assert server["bridge"].mode == "dry_run"
    assert server["bridge"].armed is False


def test_arm_then_start_live_allowed_but_paper_adapter(client, server):
    st, b = client.post("/control/arm", {"confirm": "ARM LIVE", "runbook_ack": True}, token=CONTROL_TOKEN)
    assert st == 200 and b["data"]["armed"] is True
    st, b = client.post("/control/start", {"profile": "conservative", "mode": "live"}, token=CONTROL_TOKEN)
    assert st == 200
    assert b["data"]["mode"] == "live"
    # Even armed+live, no real order placement happens here (no keys read).
    assert server["bridge"].armed is True


def test_config_out_of_range_rejected_with_detail(client):
    st, b = client.post("/control/config", {"params": {"threshold_price": 0.99}}, token=CONTROL_TOKEN)
    assert st == 400
    assert b["error"]["code"] == "validation"
    assert "threshold_price" in b["error"]["detail"]
    assert "0.55" in b["error"]["detail"]["threshold_price"]


def test_config_in_range_accepted(client):
    st, b = client.post("/control/config", {"params": {"threshold_price": 0.72}}, token=CONTROL_TOKEN)
    assert st == 200
    assert b["data"]["ok"] is True


def test_config_cap_cannot_disable_itself(client):
    st, b = client.post("/control/config", {"params": {"max_trades_per_day": 0}}, token=CONTROL_TOKEN)
    assert st == 400
    assert "max_trades_per_day" in b["error"]["detail"]


def test_profile_switch_validated(client):
    st, b = client.post("/control/profile", {"profile": "nonexistent"}, token=CONTROL_TOKEN)
    assert st == 400
    assert b["error"]["code"] == "validation"
    st, b = client.post("/control/profile", {"profile": "aggressive"}, token=CONTROL_TOKEN)
    assert st == 200
    assert b["data"]["profile"] == "aggressive"


def test_kill_then_status_reflects_killed(client):
    client.post("/control/kill", {"confirm": "KILL"}, token=CONTROL_TOKEN)
    st, b = client.get("/status")
    assert b["data"]["killed"] is True
    assert b["data"]["running"] is False


def test_config_control_updates_profile_params(client):
    client.post("/control/config", {"params": {"threshold_price": 0.8}}, token=CONTROL_TOKEN)
    st, b = client.get("/config")
    assert b["data"]["params"]["threshold_price"] == 0.8
