"""Shared pytest fixtures: an in-process HTTP client against the live server.

Boots the real ``ThreadingHTTPServer`` (MockSource-backed) on an ephemeral port
with known tokens, then exposes a tiny urllib client. No third-party deps.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# Make quant-app/ importable (engine, crypto, backend) when run from anywhere.
_QUANT_APP = Path(__file__).resolve().parent.parent.parent
if str(_QUANT_APP) not in sys.path:
    sys.path.insert(0, str(_QUANT_APP))

READ_TOKEN = "read-token-xyz"
CONTROL_TOKEN = "control-token-abc"


@pytest.fixture()
def server(monkeypatch):
    monkeypatch.setenv("BTC5M_API_TOKEN", READ_TOKEN)
    monkeypatch.setenv("BTC5M_API_CONTROL_TOKEN", CONTROL_TOKEN)
    # Ensure no live private key is needed/used.
    monkeypatch.delenv("PM_PRIVATE_KEY", raising=False)

    from backend import server as srv
    from backend.engine_bridge import EngineBridge

    bridge = EngineBridge(runtime_dir=None, profile="conservative")
    httpd = srv.serve("127.0.0.1", 0, bridge=bridge)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        yield {"base": f"http://127.0.0.1:{port}/api/v1", "bridge": bridge}
    finally:
        httpd.shutdown()


class Client:
    def __init__(self, base: str):
        self.base = base

    def request(self, method, path, body=None, token=None):
        req = urllib.request.Request(self.base + path, method=method)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data=data) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def get(self, path, token=READ_TOKEN):
        return self.request("GET", path, token=token)

    def post(self, path, body=None, token=CONTROL_TOKEN):
        return self.request("POST", path, body=body, token=token)


@pytest.fixture()
def client(server):
    return Client(server["base"])
