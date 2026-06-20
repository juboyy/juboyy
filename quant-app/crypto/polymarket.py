"""LIVE, GATED Polymarket execution adapter.

Wraps ``py_clob_client.ClobClient`` (POLYGON) using the *exact* env var names the
upstream bot reads (``PM_PRIVATE_KEY``, ``PM_FUNDER`` / ``PM_ADDRESS``,
``PM_SIGNATURE_TYPE``, ``PM_API_KEY``/``PM_API_SECRET``/``PM_API_PASSPHRASE``).

Hard invariants (06 §4, §7):
  * Refuses to construct / operate unless ``armed=True and mode=="live"`` AND all
    required env vars are present — otherwise raises a clear error. This makes a
    live order **impossible** without explicit arming + creds.
  * ``py_clob_client`` is imported **lazily**, only here, only when arming live.
  * The private key is read from env, passed straight to the official client, and
    is **never** stored on the instance, logged, returned, or put in a repr.
  * Only the **official** Polymarket hosts are allowed in live mode (host
    allow-list, 06 §3); no user-supplied endpoint.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from .adapter import (
    SCHEMA_VERSION,
    Balance,
    ExecutionAdapter,
    Order,
    Position,
    Quote,
    TradeResult,
)
from .safety import mask_address, redact

# Official Polymarket hosts only (06 §3 host allow-list).
OFFICIAL_CLOB_HOST = "https://clob.polymarket.com"
OFFICIAL_GAMMA_HOST = "https://gamma-api.polymarket.com"
_ALLOWED_CLOB_HOSTS = frozenset({OFFICIAL_CLOB_HOST})

# Required env vars to even *attempt* a live arm (mirrors the upstream runner).
REQUIRED_ENV = (
    "PM_PRIVATE_KEY",
    "PM_API_KEY",
    "PM_API_SECRET",
    "PM_API_PASSPHRASE",
)
# PM_FUNDER (or PM_ADDRESS alias) is required for the proxy-wallet model.
FUNDER_ENV = ("PM_FUNDER", "PM_ADDRESS")


class LiveGateError(RuntimeError):
    """Raised when the live adapter is constructed/operated without arming or creds."""


def _now_iso(ts: Optional[float] = None) -> str:
    t = time.time() if ts is None else ts
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _missing_required_env(env: Optional[dict] = None) -> list[str]:
    e = os.environ if env is None else env
    missing = [name for name in REQUIRED_ENV if not e.get(name)]
    if not any(e.get(n) for n in FUNDER_ENV):
        missing.append("PM_FUNDER")
    return missing


class PolymarketExecutionAdapter(ExecutionAdapter):
    """Live CLOB adapter. Construction itself is gated.

    The constructor refuses (raises :class:`LiveGateError`) unless
    ``armed and mode == "live"`` AND every required env var is set. There is no
    code path that places a live order without passing this gate.
    """

    def __init__(
        self,
        *,
        armed: bool = False,
        mode: str = "dry_run",
        profile: str = "conservative",
        clob_host: str = OFFICIAL_CLOB_HOST,
        env: Optional[dict] = None,
        stop_loss_pct: float = 0.25,
    ) -> None:
        self.mode = mode
        self.armed = bool(armed)
        self.profile = profile
        self.stop_loss_pct = stop_loss_pct
        self._env = os.environ if env is None else env
        self._client = None  # set in _ensure_client(); never holds the key

        # --- GATE 1: explicit arming + live mode (dry-run by default) ---
        if not (self.armed and self.mode == "live"):
            raise LiveGateError(
                "PolymarketExecutionAdapter refuses to construct: live execution "
                "requires armed=True AND mode='live' (dry-run is the default; use "
                "PaperExecutionAdapter). "
                f"Got armed={self.armed!r}, mode={self.mode!r}."
            )

        # --- GATE 2: host allow-list (no custom endpoints in live, 06 §3) ---
        if clob_host not in _ALLOWED_CLOB_HOSTS:
            raise LiveGateError(
                f"live mode forbids non-official CLOB host: {clob_host!r}. "
                f"Allowed: {sorted(_ALLOWED_CLOB_HOSTS)}"
            )
        self._clob_host = clob_host

        # --- GATE 3: all required creds present (else cannot operate) ---
        missing = _missing_required_env(self._env)
        if missing:
            raise LiveGateError(
                "live execution requires these env vars to be set: "
                f"{', '.join(missing)}. Refusing to operate without credentials."
            )

        # Read the proxy/funder model params (NOT the key — never stored).
        self._signature_type = int(self._env.get("PM_SIGNATURE_TYPE", "2"))
        self._funder = self._env.get("PM_FUNDER") or self._env.get("PM_ADDRESS")

    # -- never leak secrets ------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"PolymarketExecutionAdapter(mode={self.mode!r}, armed={self.armed!r}, "
            f"profile={self.profile!r}, host={self._clob_host!r}, "
            f"funder={mask_address(getattr(self, '_funder', None))!r}, "
            f"signature_type={getattr(self, '_signature_type', None)!r})"
        )

    __str__ = __repr__

    # -- lazy client construction ------------------------------------------
    def _ensure_client(self):
        """Lazily build the official ClobClient. Imports py_clob_client only here.

        The private key is read from env into a local, handed to the official
        client (which does the signing), and never assigned to ``self``.
        """
        if self._client is not None:
            return self._client

        # LIVE — gated: lazy import of the official Polymarket SDK. Only reached
        # after all gates pass. Do NOT import at module top (core/paper path is
        # stdlib-only, 02 §7).
        try:
            from py_clob_client.client import ClobClient  # noqa: WPS433
            from py_clob_client.constants import POLYGON  # noqa: WPS433
            from py_clob_client.clob_types import ApiCreds  # noqa: WPS433
        except Exception as exc:  # pragma: no cover - import path not exercised in tests
            raise LiveGateError(
                "py_clob_client is not installed; live execution unavailable. "
                f"({redact(exc)})"
            ) from None

        # Read the key as a transient local. NEVER store on self / log / return.
        key = self._env.get("PM_PRIVATE_KEY") or ""
        try:
            client = ClobClient(
                host=self._clob_host,
                chain_id=POLYGON,
                key=key,
                signature_type=self._signature_type,
                funder=self._funder,
            )
            client.set_api_creds(
                ApiCreds(
                    api_key=self._env.get("PM_API_KEY"),
                    api_secret=self._env.get("PM_API_SECRET"),
                    api_passphrase=self._env.get("PM_API_PASSPHRASE"),
                )
            )
        except Exception as exc:  # pragma: no cover - network/SDK path
            # Redact in case the SDK echoes any cred material into the message.
            raise LiveGateError(f"failed to init ClobClient: {redact(exc)}") from None
        finally:
            # Drop the local reference promptly; the SDK retains what it needs.
            key = None  # noqa: F841

        self._client = client
        return client

    def _assert_operational(self) -> None:
        if not (self.armed and self.mode == "live"):
            raise LiveGateError("adapter is not armed for live; operation refused")
        missing = _missing_required_env(self._env)
        if missing:
            raise LiveGateError(f"missing live credentials: {', '.join(missing)}")

    # -- ExecutionAdapter --------------------------------------------------
    def quote(self, market: Any) -> Quote:
        self._assert_operational()
        client = self._ensure_client()
        slug = market if isinstance(market, str) else getattr(market, "market_slug", "unknown")
        # LIVE — gated: real order-book fetch goes here, e.g.
        #     book = client.get_order_book(token_id)
        # Stubbed (no network in this environment); structure is real.
        raise NotImplementedError(
            "live quote() is a gated stub in this build — wire client.get_order_book here"
        )

    def open_position(self, decision: Any) -> Order:
        self._assert_operational()
        client = self._ensure_client()
        # LIVE — gated: build + post the marketable-limit order via the official
        # client, e.g.:
        #     from py_clob_client.clob_types import OrderArgs
        #     signed = client.create_order(OrderArgs(price=..., size=..., side=...,
        #                                             token_id=...))
        #     resp = client.post_order(signed)
        #     order_id, open_tx = resp["orderID"], resp.get("transactionHash")
        # Then map into the 05 §5 Order shape (open_tx set, status="open").
        raise NotImplementedError(
            "live open_position() is a gated stub in this build — wire "
            "client.create_order/post_order here (05 §5 Order shape)"
        )

    def close_position(self, position: Order) -> TradeResult:
        self._assert_operational()
        client = self._ensure_client()
        # LIVE — gated: post the opposite/close order or await settlement, then
        # build the canonical TradeResult with realized_cashflow_pnl_usdc (03 §8).
        raise NotImplementedError(
            "live close_position() is a gated stub in this build — wire the close/"
            "settlement path here (05 §6 TradeResult)"
        )

    def cancel(self, order_id: str) -> bool:
        self._assert_operational()
        client = self._ensure_client()
        # LIVE — gated: client.cancel(order_id) / client.cancel_all()
        raise NotImplementedError(
            "live cancel() is a gated stub in this build — wire client.cancel here"
        )

    def balance(self) -> Balance:
        self._assert_operational()
        # Funder/signature metadata come from env (already validated at
        # construction); reporting them does NOT require building the client or
        # touching the key. The on-chain equity value is a gated stub below.
        return Balance(
            schema_version=SCHEMA_VERSION,
            ts=_now_iso(),
            equity_usd=None,  # LIVE — gated: client.get_balance_allowance(...) →
            #                   self._ensure_client() then query collateral.
            funder_address_masked=mask_address(self._funder),
            signature_type=self._signature_type,
            currency="USDC",
        )
