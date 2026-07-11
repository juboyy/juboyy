"""Read endpoints return the right `05` shapes the mobile client consumes (08 §3).

Each test asserts the envelope (08 §1) plus the exact normative field names from
``05_DATA_CONTRACTS.md`` / ``mobile/src/types/contracts.ts``.
"""

from __future__ import annotations


def _assert_envelope(body):
    assert set(body.keys()) >= {"schema_version", "ts", "data"}
    assert body["schema_version"] == "1.0"
    assert isinstance(body["ts"], str)


def test_status_shape(client):
    st, body = client.get("/status")
    assert st == 200
    _assert_envelope(body)
    d = body["data"]
    for k in (
        "schema_version", "running", "state", "pid", "profile", "mode",
        "armed", "killed", "started_at", "uptime_sec", "params", "log_path",
    ):
        assert k in d, k
    assert d["state"] in ("RODANDO", "PARADO", "STALE")
    assert d["mode"] == "dry_run"
    assert d["armed"] is False
    for p in (
        "threshold", "stake_usd", "stop_loss_pct", "exit_before_sec",
        "min_entry_seconds_left", "poll_sec", "execute",
    ):
        assert p in d["params"], p


def test_snapshot_shape(client):
    st, body = client.get("/snapshot")
    assert st == 200
    d = body["data"]
    for k in (
        "ts", "market_slug", "seconds_left", "clob_up_ask", "clob_down_ask",
        "clob_up_bid", "clob_down_bid", "gamma_up", "gamma_down", "min_spread",
        "top_ask_notional_usd", "top_bid_notional_usd", "btc_price_open",
        "btc_price_now", "age_sec", "source", "schema_version",
    ):
        assert k in d, k


def test_signal_shape(client):
    st, body = client.get("/signal")
    assert st == 200
    d = body["data"]
    for k in (
        "chosen_side", "chosen_side_ask", "total_score", "enter_score_min",
        "subscores", "weights", "gates", "gates_passed", "failed_gate",
        "model_version", "age_sec", "source",
    ):
        assert k in d, k
    for sk in ("momentum_score", "skew_score", "liquidity_score",
               "imbalance_score", "time_decay_score", "rv_penalty", "agreement_bonus"):
        assert sk in d["subscores"], sk
    for wk in ("w_mom", "w_skew", "w_liq", "w_imb", "w_time", "w_vol"):
        assert wk in d["weights"], wk
    for gk in ("health", "in_window", "momentum_present", "spread_ok",
               "notional_ok", "skew_agreement", "ask_ge_threshold",
               "ask_le_max", "risk_allows"):
        assert gk in d["gates"], gk


def test_decision_shape(client):
    st, body = client.get("/decision")
    assert st == 200
    d = body["data"]
    for k in (
        "action", "side", "limit_price", "size_usd", "shares", "reason",
        "hedge", "risk_verdict", "risk_reason", "mode", "armed", "signal_ref_ts",
    ):
        assert k in d, k
    assert d["action"] in ("enter", "hold", "exit", "hedge", "skip")
    assert d["risk_verdict"] in ("allow", "veto", "clamp")
    assert set(d["hedge"].keys()) == {"enabled", "side", "notional_usd"}
    # Dry-run default is never bypassed.
    assert d["mode"] == "dry_run"
    assert d["armed"] is False


def test_positions_is_list(client):
    st, body = client.get("/positions")
    assert st == 200
    assert isinstance(body["data"], list)


def test_trades_is_list(client):
    st, body = client.get("/trades?limit=10")
    assert st == 200
    assert isinstance(body["data"], list)


def test_trade_not_found(client):
    st, body = client.get("/trades/does-not-exist")
    assert st == 404
    assert body["error"]["code"] == "not_found"


def test_risk_shape(client):
    st, body = client.get("/risk")
    assert st == 200
    d = body["data"]
    for k in (
        "profile", "mode", "armed", "killed", "running", "pnl_today",
        "pnl_total", "trades_today", "trades_total", "wins", "losses",
        "win_rate", "max_trades_per_day", "trades_cap_used_pct",
        "daily_loss_cap_usd", "daily_loss_cap_pct", "loss_cap_used_pct",
        "best_trade", "worst_trade", "open_position", "dead_man_tripped",
    ):
        assert k in d, k


def test_equity_shape(client):
    st, body = client.get("/equity?range=session")
    assert st == 200
    d = body["data"]
    for k in ("equity_usd", "funder_address_masked", "signature_type",
              "currency", "equity_curve"):
        assert k in d, k
    assert isinstance(d["equity_curve"], list)


def test_equity_bad_range(client):
    st, body = client.get("/equity?range=bogus")
    assert st == 400
    assert body["error"]["code"] == "validation"


def test_config_shape(client):
    st, body = client.get("/config")
    assert st == 200
    d = body["data"]
    assert set(d.keys()) == {"profile", "params", "ranges"}
    for k in ("threshold_price", "stake_usd", "max_notional_usd",
              "daily_max_loss_pct", "max_trades_per_day", "stop_loss_pct",
              "exit_before_sec", "hedge_enabled", "hedge_notional_usd"):
        assert k in d["params"], k
        assert k in d["ranges"], k
        assert set(d["ranges"][k].keys()) >= {"min", "max"}


def test_health_shape(client):
    st, body = client.get("/health")
    assert st == 200
    d = body["data"]
    assert set(d.keys()) == {"ok", "state", "age_sec", "dead_man_tripped"}


def test_unknown_path_404(client):
    st, body = client.get("/nope")
    assert st == 404
    assert body["error"]["code"] == "not_found"
