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
        client: Any = None,
    ) -> None:
        self.mode = mode
        self.armed = bool(armed)
        self.profile = profile
        self.stop_loss_pct = stop_loss_pct
        self._env = os.environ if env is None else env
        # ``client`` is the test seam: an injected fake CLOB client used in place
        # of the real (lazy-imported) ``py_clob_client``. It is ONLY honored after
        # all construction gates below pass, so injecting a client can never
        # bypass the arm + cred gate. In production it is None and the real client
        # is built lazily inside ``_make_client``.
        self._client = client  # set/overwritten in _ensure_client(); never holds the key

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
        """Return the CLOB client, building it lazily the first time.

        If a client was injected at construction (test seam), it is returned
        as-is. Otherwise the real official client is built via ``_make_client``.
        The private key is never assigned to ``self``.
        """
        if self._client is not None:
            return self._client
        self._client = self._make_client()
        return self._client

    def _make_client(self):
        """Lazily build the official ClobClient. Imports py_clob_client only here.

        The private key is read from env into a local, handed to the official
        client (which does the signing), and never assigned to ``self``. Tests
        monkeypatch this seam (or inject ``client=``) so no network/SDK is needed.
        """
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

        return client

    def _assert_operational(self) -> None:
        if not (self.armed and self.mode == "live"):
            raise LiveGateError("adapter is not armed for live; operation refused")
        missing = _missing_required_env(self._env)
        if missing:
            raise LiveGateError(f"missing live credentials: {', '.join(missing)}")

    # -- response coercion helpers (pure; no key, no network) --------------
    @staticmethod
    def _resp_get(resp: Any, *keys: str, default: Any = None) -> Any:
        """Read a value from an SDK response that may be a dict or an object.

        The official client returns dicts for most calls; this tolerates both so
        the mapping is robust to minor SDK shape differences.
        """
        for k in keys:
            if isinstance(resp, dict):
                if k in resp and resp[k] is not None:
                    return resp[k]
            else:
                v = getattr(resp, k, None)
                if v is not None:
                    return v
        return default

    def _stop_loss_price(self, entry_price: float) -> float:
        return round(max(0.0, entry_price * (1.0 - self.stop_loss_pct)), 6)

    # -- order primitives (gated; required for market-making) --------------
    def place_limit(
        self,
        *,
        token_id: str,
        price: float,
        size: float,
        side: str,
        market_slug: Optional[str] = None,
        seconds_left: Optional[int] = None,
    ) -> Order:
        """Place a LIMIT order on the CLOB and map the response to :class:`Order`.

        Gated: requires armed+live+creds. Builds an ``OrderArgs`` via the official
        client and posts it; the resulting order id / tx hash are mapped into the
        canonical 05 §5 Order shape. ``side`` is the strategy-side label
        ("up"/"down"/"buy"/"sell") carried through verbatim.
        """
        self._assert_operational()
        client = self._ensure_client()
        try:
            from py_clob_client.clob_types import OrderArgs  # noqa: WPS433

            args = OrderArgs(
                price=float(price),
                size=float(size),
                side=side,
                token_id=str(token_id),
            )
            signed = client.create_order(args)
            resp = client.post_order(signed)
        except Exception as exc:  # pragma: no cover - exercised via fake in tests
            raise LiveGateError(f"place_limit failed: {redact(exc)}") from None

        order_id = str(self._resp_get(resp, "orderID", "order_id", "id", default=""))
        open_tx = self._resp_get(resp, "transactionHash", "transaction_hash", "tx_hash")
        shares = int(round(float(size)))
        entry = float(price)
        return Order(
            schema_version=SCHEMA_VERSION,
            order_id=order_id,
            ts=_now_iso(),
            market_slug=market_slug or str(token_id),
            side=side,
            entry_price=entry,
            shares=shares,
            cost_usdc=round(entry * shares, 6),
            open_tx=open_tx,
            mode=self.mode,
            status="open",
            stop_loss_price=self._stop_loss_price(entry),
            seconds_left_at_entry=seconds_left,
            profile=self.profile,
        )

    def place_market(
        self,
        *,
        token_id: str,
        size: float,
        side: str,
        price: float,
        market_slug: Optional[str] = None,
        seconds_left: Optional[int] = None,
    ) -> Order:
        """Place a marketable order. Polymarket's CLOB is a limit book, so a
        "market" order is a marketable-limit at ``price`` (the crossing ask/bid);
        the caller supplies that price from the quote. Maps to :class:`Order`.
        """
        return self.place_limit(
            token_id=token_id,
            price=price,
            size=size,
            side=side,
            market_slug=market_slug,
            seconds_left=seconds_left,
        )

    def replace(self, order_id: str, new_price: float, new_size: float) -> Order:
        """Cancel ``order_id`` and place a replacement limit at ``new_price``/
        ``new_size`` (the CLOB has no atomic amend). Required for market-making.

        The replacement reuses the original order's token/side/slug, which the
        official client exposes via ``get_order``.
        """
        self._assert_operational()
        client = self._ensure_client()
        try:
            existing = client.get_order(order_id)
        except Exception as exc:  # pragma: no cover - exercised via fake in tests
            raise LiveGateError(f"replace: get_order failed: {redact(exc)}") from None

        token_id = self._resp_get(existing, "asset_id", "token_id", "tokenID")
        side = self._resp_get(existing, "side", default="buy")
        market_slug = self._resp_get(existing, "market", "market_slug")

        # Best-effort cancel first; refuse to place the replacement if it fails so
        # we never double up exposure.
        if not self.cancel(order_id):
            raise LiveGateError(f"replace: cancel of {order_id!r} did not succeed")

        return self.place_limit(
            token_id=str(token_id),
            price=float(new_price),
            size=float(new_size),
            side=str(side),
            market_slug=market_slug,
        )

    def positions(self) -> list:
        """Return current open positions as a list of :class:`Position` records.

        Reads the live order/position state via the official client and maps each
        into the 05 §5 Position shape. Never returns or logs key material.
        """
        self._assert_operational()
        client = self._ensure_client()
        try:
            raw = client.get_orders()
        except Exception as exc:  # pragma: no cover - exercised via fake in tests
            raise LiveGateError(f"positions failed: {redact(exc)}") from None

        out: list = []
        for o in raw or []:
            entry = float(self._resp_get(o, "price", default=0.0) or 0.0)
            size = self._resp_get(o, "size_matched", "original_size", "size", default=0.0)
            shares = int(round(float(size or 0.0)))
            out.append(
                Position(
                    schema_version=SCHEMA_VERSION,
                    order_id=str(self._resp_get(o, "id", "orderID", "order_id", default="")),
                    ts=_now_iso(),
                    market_slug=str(self._resp_get(o, "market", "market_slug", default="")),
                    side=str(self._resp_get(o, "side", default="")),
                    entry_price=entry,
                    shares=shares,
                    cost_usdc=round(entry * shares, 6),
                    open_tx=self._resp_get(o, "transactionHash", "transaction_hash"),
                    mode=self.mode,
                    status=str(self._resp_get(o, "status", default="open")),
                    stop_loss_price=self._stop_loss_price(entry),
                    seconds_left_at_entry=None,
                    profile=self.profile,
                )
            )
        return out

    # -- ExecutionAdapter --------------------------------------------------
    def quote(self, market: Any) -> Quote:
        self._assert_operational()
        client = self._ensure_client()
        slug = market if isinstance(market, str) else getattr(market, "market_slug", "unknown")
        token_id = market if isinstance(market, str) else getattr(market, "clob_up_token_id", market)
        try:
            book = client.get_order_book(token_id)
        except Exception as exc:  # pragma: no cover - exercised via fake in tests
            raise LiveGateError(f"quote failed: {redact(exc)}") from None

        asks = self._resp_get(book, "asks", default=[]) or []
        bids = self._resp_get(book, "bids", default=[]) or []

        def _best(levels, pick):
            prices = [float(self._resp_get(l, "price", default=0.0)) for l in levels]
            return pick(prices) if prices else None

        best_ask = _best(asks, min)
        best_bid = _best(bids, max)
        return Quote(
            schema_version=SCHEMA_VERSION,
            ts=_now_iso(),
            market_slug=str(slug),
            clob_up_ask=best_ask,
            clob_up_bid=best_bid,
            min_spread=(round(best_ask - best_bid, 6) if (best_ask is not None and best_bid is not None) else None),
            source="live",
        )

    def open_position(self, decision: Any) -> Order:
        self._assert_operational()
        # The Decision carries the token/side/price/size the supervisor sized.
        token_id = getattr(decision, "token_id", None) or getattr(decision, "market_slug", None)
        side = getattr(decision, "side", "buy")
        price = float(getattr(decision, "limit_price", 0.0) or 0.0)
        size_usd = float(getattr(decision, "size_usd", 0.0) or 0.0)
        shares = getattr(decision, "shares", None)
        size = float(shares) if shares else (size_usd / price if price > 0 else 0.0)
        return self.place_market(
            token_id=str(token_id),
            size=size,
            side=str(side),
            price=price,
            market_slug=getattr(decision, "market_slug", None),
            seconds_left=getattr(decision, "seconds_left", None),
        )

    def close_position(self, position: Order) -> TradeResult:
        self._assert_operational()
        client = self._ensure_client()
        # Post the opposite-side marketable order to flatten, then build the
        # canonical TradeResult. The exit cashflow comes from the fill response.
        opp = {"buy": "sell", "sell": "buy", "up": "down", "down": "up"}.get(
            str(position.side), "sell"
        )
        try:
            from py_clob_client.clob_types import OrderArgs  # noqa: WPS433

            args = OrderArgs(
                price=0.0,
                size=float(position.shares),
                side=opp,
                token_id=str(getattr(position, "market_slug", position.order_id)),
            )
            signed = client.create_order(args)
            resp = client.post_order(signed)
        except Exception as exc:  # pragma: no cover - exercised via fake in tests
            raise LiveGateError(f"close_position failed: {redact(exc)}") from None

        close_tx = self._resp_get(resp, "transactionHash", "transaction_hash", "tx_hash")
        exit_cashflow = float(self._resp_get(resp, "cashflow_usdc", "proceeds_usdc", default=0.0) or 0.0)
        cost_basis = float(position.cost_usdc or 0.0)
        pnl = round(exit_cashflow - cost_basis, 6)
        result = "win" if pnl > 0 else ("loss" if pnl < 0 else "breakeven")
        return TradeResult(
            schema_version=SCHEMA_VERSION,
            ts=_now_iso(),
            profile=self.profile,
            result=result,
            side=position.side,
            market_slug=position.market_slug,
            entry_price=position.entry_price,
            shares=position.shares,
            cost_usdc=position.cost_usdc,
            open_tx=position.open_tx,
            close_reason="time_exit",
            close_success=True,
            close_status="closed",
            close_skipped=False,
            close_tx=close_tx,
            realized_cashflow_pnl_usdc=pnl,
            btc_move_usd=None,
            skew=None,
            seconds_left_at_entry=position.seconds_left_at_entry,
            threshold_price=None,
            stake_usd=position.cost_usdc,
            fees_usdc=0.0,
            slippage_usdc=0.0,
            gas_usdc=0.0,
            mode=self.mode,
        )

    def cancel(self, order_id: str) -> bool:
        self._assert_operational()
        client = self._ensure_client()
        try:
            resp = client.cancel(order_id)
        except Exception as exc:  # pragma: no cover - exercised via fake in tests
            raise LiveGateError(f"cancel failed: {redact(exc)}") from None
        if resp is None:
            return True
        # The SDK returns e.g. {"canceled": ["<id>"], "not_canceled": {}}.
        canceled = self._resp_get(resp, "canceled", default=None)
        if canceled is not None:
            return order_id in canceled if isinstance(canceled, (list, tuple, set)) else bool(canceled)
        success = self._resp_get(resp, "success", default=None)
        return bool(success) if success is not None else True

    def balance(self) -> Balance:
        self._assert_operational()
        # Funder/signature metadata come from env (already validated at
        # construction). The on-chain equity is queried via the client when one is
        # available (injected or built); if the client/SDK is unavailable we still
        # return the masked funder + signature_type without leaking the key.
        equity: Optional[float] = None
        try:
            client = self._ensure_client()
            raw = client.get_balance_allowance()
            bal = self._resp_get(raw, "balance", "collateral", default=None)
            if bal is not None:
                equity = round(float(bal), 6)
        except Exception:
            equity = None  # never raise from balance(); never leak key material
        return Balance(
            schema_version=SCHEMA_VERSION,
            ts=_now_iso(),
            equity_usd=equity,
            funder_address_masked=mask_address(self._funder),
            signature_type=self._signature_type,
            currency="USDC",
        )
