"""
backend — zero-dependency HTTP/WS API server bridging the deterministic engine to
the mobile app and dashboard (`docs/08_API_SPEC.md`, `docs/05_DATA_CONTRACTS.md`).

Standard-library only (``http.server`` like ``dashboard/app.py``). Read-only and
dry-run by default; control endpoints are token-gated and never place real orders
(they flip in-process flags and write an auditable command file). Non-custodial:
the backend never reads or logs ``PM_PRIVATE_KEY``.

Run from ``quant-app/``:

    python -m backend.server
"""

from .engine_bridge import EngineBridge, ValidationError  # noqa: F401

__all__ = ["EngineBridge", "ValidationError"]
__version__ = "1.0"
