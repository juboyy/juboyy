"""runtime_paths.py — unified ``runtime/`` layout + JSON-lines logging setup.

PHASE 0 of the multi-strategy unification. This module is the single place that
defines where the unified runtime artifacts live and how structured events are
appended. It is standard-library only, holds no key material, and performs no
network I/O.

Layout (all under ``<root>/runtime/``):

    events.jsonl    — one JSON object per supervisor/strategy event (the
                      unified runtime log).
    orders.jsonl    — one JSON object per routed order / fill.
    equity.jsonl    — one JSON object per equity/heartbeat sample.
    commands.jsonl  — one JSON object per operator command (kill/arm/…).

Every record is a single line of compact JSON terminated by ``\n`` so the files
are append-only and trivially tailable. ``JsonlLogger`` wraps a stdlib
``logging.Logger`` whose handler writes those lines; tests inject a temp root so
nothing escapes the sandbox.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# Canonical file names inside the runtime dir.
EVENTS_FILE = "events.jsonl"
ORDERS_FILE = "orders.jsonl"
EQUITY_FILE = "equity.jsonl"
COMMANDS_FILE = "commands.jsonl"

ALL_STREAMS = (EVENTS_FILE, ORDERS_FILE, EQUITY_FILE, COMMANDS_FILE)


def _utc_iso(ts: Optional[float] = None) -> str:
    t = time.time() if ts is None else ts
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved absolute paths for the unified ``runtime/`` layout.

    Construct via :meth:`under` (defaults to ``<cwd>/runtime``) or pass an
    explicit root. :meth:`ensure` creates the directory tree; it never deletes.
    """

    root: Path

    @classmethod
    def under(cls, base: Optional[os.PathLike[str] | str] = None) -> "RuntimePaths":
        base_path = Path(base) if base is not None else Path.cwd()
        return cls(root=base_path / "runtime")

    def ensure(self) -> "RuntimePaths":
        self.root.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def events(self) -> Path:
        return self.root / EVENTS_FILE

    @property
    def orders(self) -> Path:
        return self.root / ORDERS_FILE

    @property
    def equity(self) -> Path:
        return self.root / EQUITY_FILE

    @property
    def commands(self) -> Path:
        return self.root / COMMANDS_FILE

    def path_for(self, stream: str) -> Path:
        if stream not in ALL_STREAMS:
            raise ValueError(f"unknown runtime stream {stream!r}; choose from {ALL_STREAMS}")
        return self.root / stream


class JsonlFormatter(logging.Formatter):
    """Formatter that renders a record's ``payload`` dict as one JSON line.

    The supervisor logs by calling ``logger.info("", extra={"payload": {...}})``.
    A ``ts`` and ``level`` are added if absent. Anything not JSON-serializable is
    coerced with ``default=str`` so logging never raises.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "payload", None)
        if not isinstance(payload, dict):
            payload = {"message": record.getMessage()}
        out: Dict[str, Any] = dict(payload)
        out.setdefault("ts", _utc_iso())
        out.setdefault("level", record.levelname)
        return json.dumps(out, default=str, sort_keys=True)


class JsonlLogger:
    """Append-only JSON-lines writer over the unified runtime layout.

    Wraps one stdlib :class:`logging.Logger` per stream (events/orders/equity/
    commands). Each :meth:`write` appends exactly one line. The logger name is
    namespaced so it never collides with the root logger or other components.
    """

    def __init__(self, paths: RuntimePaths, *, namespace: str = "runtime") -> None:
        self.paths = paths.ensure()
        self.namespace = namespace
        self._loggers: Dict[str, logging.Logger] = {}

    def _logger_for(self, stream: str) -> logging.Logger:
        path = self.paths.path_for(stream)
        key = stream
        logger = self._loggers.get(key)
        if logger is not None:
            return logger
        name = f"{self.namespace}.{stream}"
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        # Replace any handlers from a prior run pointed at a stale path.
        for h in list(logger.handlers):
            logger.removeHandler(h)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(JsonlFormatter())
        logger.addHandler(handler)
        self._loggers[key] = logger
        return logger

    def write(self, stream: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Append ``payload`` (a JSON-able dict) to ``stream``; returns the payload."""
        logger = self._logger_for(stream)
        logger.info("", extra={"payload": payload})
        for h in logger.handlers:
            h.flush()
        return payload

    # Convenience wrappers ---------------------------------------------------
    def event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.write(EVENTS_FILE, payload)

    def order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.write(ORDERS_FILE, payload)

    def equity_sample(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.write(EQUITY_FILE, payload)

    def command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.write(COMMANDS_FILE, payload)

    def close(self) -> None:
        """Detach and close every handler (so temp dirs can be cleaned up)."""
        for logger in self._loggers.values():
            for h in list(logger.handlers):
                h.flush()
                h.close()
                logger.removeHandler(h)
        self._loggers.clear()
