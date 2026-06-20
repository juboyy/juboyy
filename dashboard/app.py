#!/usr/bin/env python3
"""
app.py — Zero-dependency dashboard server for the `5min-btc-polymarket` bot.

Serves a single-page UI and a small JSON API that reads the bot's runtime
artifacts (see parser.py). No third-party packages required — just Python 3.8+.

Run:
    python app.py                       # serve on http://127.0.0.1:8787
    python app.py --port 9000
    python app.py --runtime /path/to/5min-btc-polymarket/skills/btc-5m-live/runtime
    python app.py --demo                # generate sample data, then serve

Environment:
    BTC5M_RUNTIME   runtime directory (overridden by --runtime)
    BTC5M_CONFIG    path to btc_5m_profiles.yaml (optional; PyYAML used if present)
    PORT            port (overridden by --port)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from parser import RuntimeReader  # noqa: E402


def load_config(yaml_path: str | None):
    """Load profile config. Prefer the real YAML (if PyYAML present),
    otherwise fall back to the bundled JSON defaults."""
    if yaml_path and Path(yaml_path).exists():
        try:
            import yaml  # type: ignore
            with open(yaml_path, "r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
            cfg.setdefault("equity_usd", None)
            return cfg
        except Exception:
            pass
    try:
        with open(HERE / "config_defaults.json", "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


class Handler(BaseHTTPRequestHandler):
    reader: RuntimeReader = None  # set on the server instance
    config: dict = {}

    # quieten default logging
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, content_type="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, default=str).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self._serve_static("index.html", "text/html; charset=utf-8")
            if path == "/static/dashboard.js":
                return self._serve_static("static/dashboard.js", "application/javascript")
            if path == "/static/dashboard.css":
                return self._serve_static("static/dashboard.css", "text/css")
            if path == "/api/health":
                return self._send(200, {"ok": True})
            if path == "/api/config":
                return self._send(200, self._public_config())
            if path == "/api/state":
                return self._send(200, self._state())
            if path == "/api/logs":
                return self._send(200, {"lines": self.reader.log_tail(160)})
            return self._send(404, {"error": "not found"})
        except BrokenPipeError:
            pass
        except Exception as exc:  # never crash the server on a bad read
            self._send(500, {"error": str(exc)})

    def _serve_static(self, rel, content_type):
        fp = HERE / rel
        try:
            data = fp.read_bytes()
        except OSError:
            return self._send(404, {"error": f"missing {rel}"})
        self._send(200, data, content_type)

    def _public_config(self):
        c = self.config
        return {
            "market": c.get("market"),
            "strategy": c.get("strategy_reference", {}),
            "profiles": c.get("profiles", {}),
            "runtime_dir": str(self.reader.dir),
        }

    def _state(self):
        r = self.reader
        status = r.status()
        trades = r.trades()
        return {
            "status": status,
            "signal": r.signal(),
            "summary": r.summary(trades=trades, status=status),
            "trades": trades[:60],
            "equity_curve": r.equity_curve(trades=trades),
            "server_time": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }


def main():
    ap = argparse.ArgumentParser(description="5min-btc-polymarket monitoring dashboard")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8787)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--runtime", default=os.environ.get(
        "BTC5M_RUNTIME", str(HERE / "runtime")))
    ap.add_argument("--config", default=os.environ.get("BTC5M_CONFIG"))
    ap.add_argument("--demo", action="store_true",
                    help="generate demo data into the runtime dir before serving")
    args = ap.parse_args()

    if args.demo:
        import demo as demo_mod
        sys.argv = ["demo", "--runtime", args.runtime]
        demo_mod.main()

    config = load_config(args.config)
    reader = RuntimeReader(args.runtime, config=config)
    Handler.reader = reader
    Handler.config = config

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"5m-BTC dashboard  ->  {url}")
    print(f"runtime dir       :  {reader.dir}")
    print(f"profiles loaded   :  {', '.join((config.get('profiles') or {}).keys()) or 'none'}")
    print("Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
        httpd.shutdown()


if __name__ == "__main__":
    main()
