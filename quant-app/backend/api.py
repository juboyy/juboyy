"""
api.py — request handlers, auth, envelopes, and error mapping (`08_API_SPEC.md`).

Pure-ish layer between the HTTP server (``server.py``) and the engine adapter
(``engine_bridge.EngineBridge``). It:

  * wraps every success in the standard envelope
    ``{ "schema_version", "ts", "data" }`` (08 §1);
  * maps errors to ``{ "error": { code, message, detail } }`` with the right HTTP
    status (08 §1 codes);
  * enforces the **bearer-token auth model** (08 §2): two scopes, ``read`` for GETs
    and ``control`` for POST control endpoints. Read GETs may be open on localhost;
    control endpoints always require the token. The kill endpoint is rate-limit
    exempt and always processable (08 §4).

No secrets are ever logged. The token is read from the environment, not hard-coded.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional, Tuple

from . import engine_bridge as eb
from .engine_bridge import EngineBridge, ValidationError, SCHEMA_VERSION, now_iso

# Env var holding the bearer token (08 §2/§4). When unset, read GETs are open on
# localhost but control endpoints are refused (fail-safe: no token ⇒ no control).
TOKEN_ENV = "BTC5M_API_TOKEN"
# Optional separate control token; falls back to the read token.
CONTROL_TOKEN_ENV = "BTC5M_API_CONTROL_TOKEN"

# Error code → HTTP status (08 §1).
_STATUS_FOR_CODE = {
    "unauthorized": 401,
    "forbidden": 403,
    "not_armed": 403,
    "cap_reached": 409,
    "killed": 409,
    "validation": 400,
    "not_found": 404,
    "unavailable": 503,
    "rate_limited": 429,
}


class ApiResult:
    """A handler result: HTTP status + a JSON-able body (already enveloped)."""

    def __init__(self, status: int, body: Dict[str, Any]):
        self.status = status
        self.body = body


def envelope(data: Any) -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "ts": now_iso(), "data": data}


def error_body(code: str, message: str, detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if detail:
        err["detail"] = detail
    return {"error": err}


def error_result(code: str, message: str, detail: Optional[Dict[str, Any]] = None) -> ApiResult:
    return ApiResult(_STATUS_FOR_CODE.get(code, 400), error_body(code, message, detail))


# ---------------------------------------------------------------------------
# Auth (08 §2)
# ---------------------------------------------------------------------------
def _expected_token(scope: str) -> Optional[str]:
    if scope == "control":
        return os.environ.get(CONTROL_TOKEN_ENV) or os.environ.get(TOKEN_ENV)
    return os.environ.get(TOKEN_ENV)


def check_auth(scope: str, presented: Optional[str], *, is_local: bool) -> Optional[ApiResult]:
    """Return an error ApiResult if auth fails, else None.

    - ``control`` scope ALWAYS requires a matching token. If no control token is
      configured server-side, control is refused (fail-safe).
    - ``read`` scope: open on localhost when no token configured; otherwise the
      token must match.
    """
    expected = _expected_token(scope)
    if scope == "control":
        if not expected:
            return error_result("forbidden", "control disabled: no server token configured")
        if presented != expected:
            return error_result("unauthorized", "missing or invalid control token")
        return None
    # read scope
    if expected is None:
        if is_local:
            return None
        return error_result("unauthorized", "read token required")
    if presented != expected:
        return error_result("unauthorized", "missing or invalid token")
    return None


# ---------------------------------------------------------------------------
# Read handlers (08 §3)
# ---------------------------------------------------------------------------
def _to_dict(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


def handle_status(bridge: EngineBridge, **_: Any) -> ApiResult:
    return ApiResult(200, envelope(bridge.status().to_dict()))


def handle_snapshot(bridge: EngineBridge, **_: Any) -> ApiResult:
    return ApiResult(200, envelope(bridge.snapshot().to_dict()))


def handle_signal(bridge: EngineBridge, **_: Any) -> ApiResult:
    return ApiResult(200, envelope(bridge.signal().to_dict()))


def handle_decision(bridge: EngineBridge, **_: Any) -> ApiResult:
    return ApiResult(200, envelope(bridge.decision().to_dict()))


def handle_positions(bridge: EngineBridge, **_: Any) -> ApiResult:
    return ApiResult(200, envelope([p.to_dict() for p in bridge.positions()]))


def handle_trades(bridge: EngineBridge, query: Optional[Dict[str, Any]] = None, **_: Any) -> ApiResult:
    query = query or {}
    limit = 200
    try:
        if query.get("limit"):
            limit = max(1, min(1000, int(query["limit"][0] if isinstance(query["limit"], list) else query["limit"])))
    except (TypeError, ValueError):
        return error_result("validation", "limit must be an integer", {"limit": "int 1..1000"})
    before = None
    if query.get("before"):
        before = query["before"][0] if isinstance(query["before"], list) else query["before"]
    trades = bridge.trades(limit=limit, before=before)
    return ApiResult(200, envelope([t.to_dict() for t in trades]))


def handle_trade(bridge: EngineBridge, order_id: Optional[str] = None, **_: Any) -> ApiResult:
    t = bridge.trade(order_id) if order_id else None
    if t is None:
        return error_result("not_found", "trade not found", {"order_id": order_id})
    return ApiResult(200, envelope(t.to_dict()))


def handle_risk(bridge: EngineBridge, **_: Any) -> ApiResult:
    return ApiResult(200, envelope(bridge.risk().to_dict()))


def handle_equity(bridge: EngineBridge, query: Optional[Dict[str, Any]] = None, **_: Any) -> ApiResult:
    query = query or {}
    rng = "session"
    if query.get("range"):
        rng = query["range"][0] if isinstance(query["range"], list) else query["range"]
    if rng not in ("session", "7d", "30d", "all"):
        return error_result("validation", "invalid range", {"range": "session|7d|30d|all"})
    return ApiResult(200, envelope(bridge.equity(rng).to_dict()))


def handle_config(bridge: EngineBridge, **_: Any) -> ApiResult:
    # ConfigResponse (mobile) carries its own schema_version/ts/profile/params/ranges.
    cfg = bridge.config()
    data = {
        "profile": cfg["profile"],
        "params": cfg["params"],
        "ranges": cfg["ranges"],
    }
    return ApiResult(200, envelope(data))


def handle_health(bridge: EngineBridge, **_: Any) -> ApiResult:
    # /health is a bare object (08 §3) but still enveloped for client consistency.
    return ApiResult(200, envelope(bridge.health()))


# ---------------------------------------------------------------------------
# Control handlers (08 §4)
# ---------------------------------------------------------------------------
def _run_control(fn: Callable[[], Dict[str, Any]], *, success_status: int = 200) -> ApiResult:
    try:
        data = fn()
    except ValidationError as exc:
        return error_result("validation", str(exc), exc.detail)
    except PermissionError as exc:
        code = str(exc) or "forbidden"
        msg = "live mode requires armed" if code == "not_armed" else "forbidden"
        return error_result(code if code in _STATUS_FOR_CODE else "forbidden", msg)
    return ApiResult(success_status, envelope(data))


def handle_start(bridge: EngineBridge, body: Optional[Dict[str, Any]] = None, **_: Any) -> ApiResult:
    body = body or {}
    return _run_control(lambda: bridge.start(profile=body.get("profile"), mode=body.get("mode", "dry_run")))


def handle_stop(bridge: EngineBridge, **_: Any) -> ApiResult:
    return _run_control(bridge.stop)


def handle_kill(bridge: EngineBridge, body: Optional[Dict[str, Any]] = None, **_: Any) -> ApiResult:
    body = body or {}
    # 08 §4: kill returns 202 and is always processable.
    return _run_control(lambda: bridge.kill(confirm=body.get("confirm")), success_status=202)


def handle_arm(bridge: EngineBridge, body: Optional[Dict[str, Any]] = None, **_: Any) -> ApiResult:
    body = body or {}
    return _run_control(lambda: bridge.arm(confirm=body.get("confirm"), runbook_ack=body.get("runbook_ack", False)))


def handle_disarm(bridge: EngineBridge, **_: Any) -> ApiResult:
    return _run_control(bridge.disarm)


def handle_profile(bridge: EngineBridge, body: Optional[Dict[str, Any]] = None, **_: Any) -> ApiResult:
    body = body or {}
    return _run_control(lambda: bridge.set_profile(body.get("profile")))


def handle_config_update(bridge: EngineBridge, body: Optional[Dict[str, Any]] = None, **_: Any) -> ApiResult:
    body = body or {}
    return _run_control(lambda: bridge.update_config(body.get("params", {})))


# ---------------------------------------------------------------------------
# Route table — (method, path-pattern) → (scope, handler)
# ---------------------------------------------------------------------------
# Static routes; dynamic /trades/{order_id} handled in server by prefix match.
READ_ROUTES = {
    ("GET", "/status"): handle_status,
    ("GET", "/snapshot"): handle_snapshot,
    ("GET", "/signal"): handle_signal,
    ("GET", "/decision"): handle_decision,
    ("GET", "/positions"): handle_positions,
    ("GET", "/trades"): handle_trades,
    ("GET", "/risk"): handle_risk,
    ("GET", "/equity"): handle_equity,
    ("GET", "/config"): handle_config,
    ("GET", "/health"): handle_health,
}

CONTROL_ROUTES = {
    ("POST", "/control/start"): handle_start,
    ("POST", "/control/stop"): handle_stop,
    ("POST", "/control/kill"): handle_kill,
    ("POST", "/control/arm"): handle_arm,
    ("POST", "/control/disarm"): handle_disarm,
    ("POST", "/control/profile"): handle_profile,
    ("POST", "/control/config"): handle_config_update,
}
