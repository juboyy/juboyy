"""
server.py — zero-dependency HTTP + WebSocket API server (`08_API_SPEC.md`).

Reuses the dashboard's stdlib ``ThreadingHTTPServer`` pattern (``dashboard/app.py``)
and the runtime-reading approach (``dashboard/parser.py``) — no third-party deps.

Endpoints (all under ``/api/v1`` per 08 §1):

  GET  /status /snapshot /signal /decision /positions /trades /trades/{id}
       /risk /equity /config /health      (scope: read)
  POST /control/start /stop /kill /arm /disarm /profile /config (scope: control)
  WS   /stream?token=<read-token>         (live push; 08 §5)

The WebSocket is a minimal RFC-6455 server-side implementation (handshake + text
frames) using only the standard library. The mobile WS hook also supports a REST
polling fallback (08 §5), which works against the same read endpoints, so a heavy
socket is never required for the app to function.

Run from quant-app/:
    python -m backend.server
Env: BTC5M_API_TOKEN, BTC5M_API_CONTROL_TOKEN, BTC5M_RUNTIME, BTC5M_PROFILE,
     BTC5M_EQUITY_USD, BTC5M_FUNDER_ADDRESS, BTC5M_SIGNATURE_TYPE, HOST, PORT.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Allow `python backend/server.py` as well as `python -m backend.server`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend import api  # type: ignore
    from backend.engine_bridge import EngineBridge  # type: ignore
else:
    from . import api
    from .engine_bridge import EngineBridge

API_PREFIX = "/api/v1"
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


class Handler(BaseHTTPRequestHandler):
    bridge: EngineBridge = None  # set on the server class
    protocol_version = "HTTP/1.1"

    # -- quieten default logging; never log tokens ------------------------
    def log_message(self, fmt, *args):  # noqa: A003
        pass

    # -- helpers ----------------------------------------------------------
    def _is_local(self) -> bool:
        host = self.client_address[0] if self.client_address else ""
        return host in _LOCAL_HOSTS

    def _bearer(self):
        h = self.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            return h[len("Bearer "):].strip()
        return None

    def _send_json(self, status: int, body) -> None:
        data = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _send_result(self, result: "api.ApiResult") -> None:
        self._send_json(result.status, result.body)

    def _strip_prefix(self, path: str):
        if path.startswith(API_PREFIX):
            return path[len(API_PREFIX):] or "/"
        return None

    # -- CORS preflight ---------------------------------------------------
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- GET --------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        rel = self._strip_prefix(parsed.path)
        if rel is None:
            return self._send_json(404, api.error_body("not_found", "unknown path"))

        # WebSocket upgrade on /stream
        if rel == "/stream" and self.headers.get("Upgrade", "").lower() == "websocket":
            return self._handle_ws(parse_qs(parsed.query))

        query = parse_qs(parsed.query)

        # Dynamic /trades/{order_id}
        if rel.startswith("/trades/"):
            order_id = rel[len("/trades/"):]
            auth_err = api.check_auth("read", self._bearer(), is_local=self._is_local())
            if auth_err:
                return self._send_result(auth_err)
            return self._send_result(api.handle_trade(self.bridge, order_id=order_id))

        handler = api.READ_ROUTES.get(("GET", rel))
        if handler is None:
            return self._send_json(404, api.error_body("not_found", "unknown path"))

        auth_err = api.check_auth("read", self._bearer(), is_local=self._is_local())
        if auth_err:
            return self._send_result(auth_err)
        try:
            return self._send_result(handler(self.bridge, query=query))
        except Exception as exc:  # never crash the server on a bad read
            return self._send_json(503, api.error_body("unavailable", str(exc)))

    # -- POST -------------------------------------------------------------
    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        rel = self._strip_prefix(parsed.path)
        if rel is None:
            return self._send_json(404, api.error_body("not_found", "unknown path"))

        handler = api.CONTROL_ROUTES.get(("POST", rel))
        if handler is None:
            return self._send_json(404, api.error_body("not_found", "unknown path"))

        # All control endpoints require the control token (08 §2/§4).
        auth_err = api.check_auth("control", self._bearer(), is_local=self._is_local())
        if auth_err:
            return self._send_result(auth_err)

        body = self._read_json_body()
        if body is None:
            body = {}
        try:
            return self._send_result(handler(self.bridge, body=body))
        except Exception as exc:
            return self._send_json(503, api.error_body("unavailable", str(exc)))

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return None

    # -- WebSocket (08 §5) ------------------------------------------------
    def _handle_ws(self, query):
        # Read-scope auth: token from ?token= or Authorization header.
        token = None
        if query.get("token"):
            token = query["token"][0]
        if token is None:
            token = self._bearer()
        auth_err = api.check_auth("read", token, is_local=self._is_local())
        if auth_err is not None:
            return self._send_result(auth_err)

        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            return self._send_json(400, api.error_body("validation", "missing Sec-WebSocket-Key"))
        accept = base64.b64encode(
            hashlib.sha1((key + _WS_GUID).encode("utf-8")).digest()
        ).decode("ascii")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        try:
            self._ws_loop()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _ws_send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([0x81])  # FIN + text opcode
        n = len(payload)
        if n < 126:
            header.append(n)
        elif n < (1 << 16):
            header.append(126)
            header += struct.pack(">H", n)
        else:
            header.append(127)
            header += struct.pack(">Q", n)
        self.wfile.write(bytes(header) + payload)
        self.wfile.flush()

    def _ws_loop(self) -> None:
        """Push state-change frames + a heartbeat every <=10s (08 §5)."""
        last_sig = None
        last_snap = None
        last_risk = None
        last_status = None
        last_beat = 0.0
        # Push an initial burst so the client renders immediately.
        self._ws_send_text(self._frame("status", self.bridge.status().to_dict()))
        self._ws_send_text(self._frame("snapshot", self.bridge.snapshot().to_dict()))
        self._ws_send_text(self._frame("signal", self.bridge.signal().to_dict()))
        while True:
            now = time.time()
            try:
                snap = self.bridge.snapshot().to_dict()
                sig = self.bridge.signal().to_dict()
                dec = self.bridge.decision().to_dict()
                rsk = self.bridge.risk().to_dict()
                sts = self.bridge.status().to_dict()
            except Exception:
                snap = sig = dec = rsk = sts = None

            if snap and snap != last_snap:
                self._ws_send_text(self._frame("snapshot", snap))
                last_snap = snap
            if sig and sig != last_sig:
                self._ws_send_text(self._frame("signal", sig))
                self._ws_send_text(self._frame("decision", dec))
                last_sig = sig
            if rsk and rsk != last_risk:
                self._ws_send_text(self._frame("risk", rsk))
                last_risk = rsk
            if sts and sts != last_status:
                self._ws_send_text(self._frame("status", sts))
                last_status = sts

            if now - last_beat >= 8.0:
                age = (snap or {}).get("age_sec") if snap else None
                self._ws_send_text(self._frame("heartbeat", {"age_sec": age if age is not None else 0}))
                last_beat = now

            time.sleep(1.0)

    @staticmethod
    def _frame(kind: str, data) -> str:
        return json.dumps(
            {"type": kind, "ts": api.now_iso(), "data": data}, default=str
        )


def build_bridge() -> EngineBridge:
    runtime = os.environ.get("BTC5M_RUNTIME")
    profile = os.environ.get("BTC5M_PROFILE", "conservative")
    equity = os.environ.get("BTC5M_EQUITY_USD")
    equity_usd = None
    if equity:
        try:
            equity_usd = float(equity)
        except ValueError:
            equity_usd = None
    sig_type = os.environ.get("BTC5M_SIGNATURE_TYPE")
    signature_type = int(sig_type) if (sig_type and sig_type.isdigit()) else None
    return EngineBridge(
        runtime_dir=runtime,
        profile=profile,
        equity_usd=equity_usd,
        funder_address=os.environ.get("BTC5M_FUNDER_ADDRESS"),
        signature_type=signature_type,
    )


def serve(host: str = "127.0.0.1", port: int = 8788, bridge: EngineBridge = None):
    Handler.bridge = bridge or build_bridge()
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 8788))
    httpd = serve(host, port)
    token_set = bool(os.environ.get(api.TOKEN_ENV))
    print(f"btc5m backend API  ->  http://{host}:{port}{API_PREFIX}")
    print(f"runtime dir        :  {Handler.bridge.runtime_dir or '(MockSource)'}")
    print(f"profile            :  {Handler.bridge.profile_name}  mode=dry_run armed=False")
    print(f"auth token set     :  {token_set}  (read GETs open on localhost when unset)")
    print("Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
        httpd.shutdown()


if __name__ == "__main__":
    main()
