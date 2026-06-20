"""
engine_bridge.py — adapt engine + runtime artifacts to the `05`/`08` JSON contracts.

This is the only module in the backend that knows about the engine. It:

  * loads a :class:`engine.Profile` for the active profile;
  * reads the latest ``MarketSnapshot``(s) from a runtime dir, reusing the
    dashboard's runtime-reading approach (``dashboard/parser.py``) and the engine
    sources (:class:`engine.datasource.RecordedSource` / ``MockSource``);
  * runs ``indicators.compute → signal_engine.evaluate/decide → risk.apply_decision``
    to produce live ``Signal`` / ``Decision`` / ``RiskState`` / ``BotStatus`` /
    ``Account`` / positions / trades / equity for the API;
  * holds the **in-process control state** (running / mode / armed / killed /
    profile) and the dry-run-by-default kill switch + arming gate from
    ``crypto/safety.py``. Control actions only flip in-process flags and write a
    command file — they never place real orders.

Everything degrades gracefully: with no live data it serves from
:class:`engine.datasource.MockSource` so the mobile app renders end-to-end.

Security (06): no private keys are ever read or logged here; the backend does not
need ``PM_PRIVATE_KEY``. Funder addresses are masked via ``crypto.safety.mask_address``.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- make the repo importable as packages (engine, crypto, dashboard) -------
_THIS = Path(__file__).resolve()
_QUANT_APP = _THIS.parent.parent            # quant-app/
_REPO = _QUANT_APP.parent                   # repo root (contains dashboard/)
for _p in (str(_QUANT_APP), str(_REPO)):
    if _p not in os.sys.path:
        os.sys.path.insert(0, _p)

from engine import contracts, indicators, signal_engine, risk as risk_mod  # noqa: E402
from engine.config import Profile, get_profile, PROFILES  # noqa: E402
from engine.datasource import MockSource, RecordedSource  # noqa: E402

from crypto.factory import get_adapter  # noqa: E402
from crypto.safety import Arming, KillSwitch, mask_address  # noqa: E402

try:  # dashboard runtime reader (optional — degrades to engine sources)
    from dashboard.parser import RuntimeReader  # type: ignore
except Exception:  # pragma: no cover - dashboard not on path
    RuntimeReader = None  # type: ignore


SCHEMA_VERSION = contracts.SCHEMA_VERSION
_ARM_CONFIRM = "ARM LIVE"
_KILL_CONFIRM = "KILL"

# Param ranges for /config validation (03 §7). Mirrors mobile mock.ts ConfigResponse.
PARAM_RANGES: Dict[str, Dict[str, float]] = {
    "threshold_price": {"min": 0.55, "max": 0.85, "step": 0.01},
    "stake_usd": {"min": 1, "max": 50, "step": 1},
    "max_notional_usd": {"min": 5, "max": 200, "step": 1},
    "daily_max_loss_pct": {"min": 1, "max": 50, "step": 1},
    "max_trades_per_day": {"min": 1, "max": 100, "step": 1},
    "stop_loss_pct": {"min": 0.05, "max": 0.9, "step": 0.01},
    "exit_before_sec": {"min": 5, "max": 120, "step": 1},
    "hedge_enabled": {"min": 0, "max": 1, "step": 1},
    "hedge_notional_usd": {"min": 0, "max": 100, "step": 1},
}

# Caps that must not be set to disable themselves (08 §4): keep a positive floor.
_NON_DISABLING_CAPS = {"daily_max_loss_pct", "max_trades_per_day"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


class ValidationError(ValueError):
    """Raised for out-of-range/invalid control params. Carries a `detail` map."""

    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.detail = detail or {}


class EngineBridge:
    """Stateful adapter between the engine/runtime and the HTTP API.

    Thread-safe (a single lock guards mutable control state + caches). Reads are
    served from the latest runtime snapshot when present, else from MockSource.
    """

    def __init__(
        self,
        runtime_dir: Optional[str] = None,
        profile: str = "conservative",
        equity_usd: Optional[float] = None,
        funder_address: Optional[str] = None,
        signature_type: Optional[int] = None,
    ):
        self._lock = threading.RLock()
        self.runtime_dir = Path(runtime_dir) if runtime_dir else None

        # --- in-process control state (dry-run / read-only by default) -------
        self.profile_name = profile if profile in PROFILES else "conservative"
        self.mode = "dry_run"
        self.running = True
        self._arming = Arming(confirm_token=_ARM_CONFIRM)
        self._kill = KillSwitch()
        self._started_at = _utcnow()
        # per-profile param overrides applied via /control/config
        self._overrides: Dict[str, Any] = {}

        # account / equity context (never secrets)
        self.equity_usd = equity_usd
        self._funder_masked = mask_address(funder_address)
        self.signature_type = signature_type

        # dashboard runtime reader (optional)
        self._reader = None
        if self.runtime_dir is not None and RuntimeReader is not None:
            self._reader = RuntimeReader(str(self.runtime_dir))

    # -- helpers ----------------------------------------------------------
    @property
    def armed(self) -> bool:
        return self._arming.armed

    @property
    def killed(self) -> bool:
        return self._kill.killed

    def profile(self) -> Profile:
        return get_profile(self.profile_name, **self._engine_overrides())

    def _engine_overrides(self) -> Dict[str, Any]:
        """Map the API param names (03 §7 / mobile ConfigParams) to Profile fields."""
        o = self._overrides
        out: Dict[str, Any] = {}
        if "threshold_price" in o:
            out["threshold_price"] = o["threshold_price"]
        if "stake_usd" in o:
            out["stake_usd"] = o["stake_usd"]
        if "max_notional_usd" in o:
            out["max_notional_usd"] = o["max_notional_usd"]
        if "daily_max_loss_pct" in o:
            out["daily_max_loss_pct"] = o["daily_max_loss_pct"]
        if "max_trades_per_day" in o:
            out["max_trades_per_day"] = int(o["max_trades_per_day"])
        if "stop_loss_pct" in o:
            out["stop_loss_pct_from_entry"] = o["stop_loss_pct"]
        if "exit_before_sec" in o:
            out["exit_before_sec"] = int(o["exit_before_sec"])
        if "hedge_enabled" in o:
            out["hedge_enabled"] = bool(o["hedge_enabled"])
        if self.equity_usd is not None:
            out["equity_usd"] = self.equity_usd
        return out

    # -- snapshots --------------------------------------------------------
    def _runtime_snapshots(self) -> List[contracts.MarketSnapshot]:
        """Latest snapshots from the runtime dir, oldest→newest.

        Prefers an engine-native JSONL fixture (``snapshots.jsonl`` /
        ``btc5m_snapshots.jsonl`` via :class:`RecordedSource`); else derives a
        single snapshot from the dashboard signal heartbeat.
        """
        if self.runtime_dir is None or not self.runtime_dir.exists():
            return []
        for name in ("snapshots.jsonl", "btc5m_snapshots.jsonl"):
            fp = self.runtime_dir / name
            if fp.exists():
                snaps = list(RecordedSource(str(fp)).snapshots())
                if snaps:
                    return snaps
        # Fallback: dashboard signal heartbeat → one MarketSnapshot.
        if self._reader is not None:
            sig = self._reader.signal()
            if sig:
                snap = self._snapshot_from_dashboard_signal(sig)
                if snap is not None:
                    return [snap]
        return []

    @staticmethod
    def _snapshot_from_dashboard_signal(sig: Dict[str, Any]) -> Optional[contracts.MarketSnapshot]:
        up = sig.get("up_ask")
        dn = sig.get("down_ask")
        if up is None and dn is None and sig.get("seconds_left") is None:
            return None
        return contracts.MarketSnapshot(
            ts=sig.get("ts"),
            market_slug=sig.get("market_slug"),
            seconds_left=sig.get("seconds_left"),
            clob_up_ask=up,
            clob_down_ask=dn,
            gamma_up=sig.get("gamma_up"),
            gamma_down=sig.get("gamma_down"),
            min_spread=sig.get("min_spread"),
            age_sec=sig.get("age_sec"),
            source=sig.get("source") or "session_report",
        )

    def snapshots(self) -> List[contracts.MarketSnapshot]:
        """Live snapshots if available, else deterministic MockSource."""
        snaps = self._runtime_snapshots()
        if snaps:
            return snaps
        return list(MockSource().snapshots())

    def latest_snapshot(self) -> contracts.MarketSnapshot:
        snaps = self.snapshots()
        return snaps[-1]

    # -- engine pipeline --------------------------------------------------
    def _open_position(self) -> Optional[contracts.Position]:
        """Best-effort open position from runtime trades (none in pure-mock)."""
        summary = self._summary_raw()
        op = summary.get("open_position") if summary else None
        if not op:
            return None
        return contracts.Position(
            order_id=op.get("open_tx"),
            ts=op.get("ts"),
            market_slug=op.get("market_slug"),
            side=op.get("side"),
            entry_price=op.get("entry_price"),
            shares=op.get("shares"),
            cost_usdc=op.get("cost_usdc"),
            open_tx=op.get("open_tx"),
            mode=self.mode,
            status="open",
            seconds_left_at_entry=op.get("seconds_left_at_entry"),
            profile=op.get("profile") or self.profile_name,
        )

    def evaluate(self) -> Tuple[contracts.Signal, contracts.Decision, contracts.MarketSnapshot]:
        prof = self.profile()
        snaps = self.snapshots()
        snapshot = snaps[-1]
        history = snaps[:-1]
        features = indicators.compute(snapshot, history=history, profile=prof)

        risk_state = self._risk_state(features=features, snapshot=snapshot)
        allow = risk_mod.apply(risk_state, prof)
        signal, decision = signal_engine.evaluate_and_decide(
            features,
            snapshot,
            prof,
            risk_allows=allow.allowed,
            open_position=self._open_position(),
            kill_flag=self.killed,
        )
        risk_mod.apply_decision(decision, risk_state, prof)
        return signal, decision, snapshot

    # -- runtime-backed KPIs ----------------------------------------------
    def _summary_raw(self) -> Dict[str, Any]:
        if self._reader is None:
            return {}
        try:
            return self._reader.summary() or {}
        except Exception:
            return {}

    def _trades_raw(self, limit: int = 200) -> List[Dict[str, Any]]:
        if self._reader is None:
            return []
        try:
            return self._reader.trades(limit=limit) or []
        except Exception:
            return []

    # -- contract builders (05) -------------------------------------------
    def status(self) -> contracts.BotStatus:
        with self._lock:
            snap = self.latest_snapshot()
            age = snap.age_sec
            prof = self.profile()
            fresh = age is not None and age <= prof.dead_man_sec
            running = self.running and not self.killed
            if not running:
                state = "PARADO"
            elif fresh:
                state = "RODANDO"
            else:
                state = "STALE"
            uptime = int(max(0, (_utcnow() - self._started_at).total_seconds()))
            return contracts.BotStatus(
                running=running,
                state=state,
                pid=os.getpid() if running else None,
                profile=self.profile_name,
                mode=self.mode,
                armed=self.armed,
                killed=self.killed,
                started_at=self._started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                uptime_sec=uptime,
                params={
                    "threshold": prof.threshold_price,
                    "stake_usd": prof.stake_usd,
                    "stop_loss_pct": prof.stop_loss_pct_from_entry,
                    "exit_before_sec": prof.exit_before_sec,
                    "min_entry_seconds_left": prof.min_entry_seconds_left,
                    "poll_sec": prof.poll_sec,
                    "execute": self.mode == "live" and self.armed,
                },
                log_path=str(self.runtime_dir / "latest.log") if self.runtime_dir else None,
            )

    def snapshot(self) -> contracts.MarketSnapshot:
        with self._lock:
            return self.latest_snapshot()

    def signal(self) -> contracts.Signal:
        with self._lock:
            sig, _dec, _snap = self.evaluate()
            return sig

    def decision(self) -> contracts.Decision:
        with self._lock:
            _sig, dec, _snap = self.evaluate()
            return dec

    def positions(self) -> List[contracts.Position]:
        with self._lock:
            if self.killed:
                return []
            op = self._open_position()
            if op is None:
                return []
            prof = self.profile()
            if op.entry_price is not None and op.stop_loss_price is None:
                op.stop_loss_price = round(
                    op.entry_price * (1 - prof.stop_loss_pct_from_entry), 6
                )
            return [op]

    def trades(self, limit: int = 200, before: Optional[str] = None) -> List[contracts.TradeResult]:
        with self._lock:
            raw = self._trades_raw(limit=max(limit, 200))
            out: List[contracts.TradeResult] = []
            for r in raw:
                if before and (r.get("ts") or "") >= before:
                    continue
                out.append(self._trade_from_raw(r))
            return out[:limit]

    def trade(self, order_id: str) -> Optional[contracts.TradeResult]:
        for t in self.trades(limit=1000):
            if t.open_tx == order_id or t.close_tx == order_id:
                return t
        return None

    @staticmethod
    def _trade_from_raw(r: Dict[str, Any]) -> contracts.TradeResult:
        return contracts.TradeResult(
            ts=r.get("ts"),
            profile=r.get("profile"),
            result=r.get("result"),
            side=r.get("side"),
            market_slug=r.get("market_slug"),
            entry_price=r.get("entry_price"),
            shares=r.get("shares"),
            cost_usdc=r.get("cost_usdc"),
            open_tx=r.get("open_tx"),
            close_reason=r.get("close_reason"),
            close_success=r.get("close_success"),
            close_status=r.get("close_status"),
            close_skipped=r.get("close_skipped"),
            close_tx=r.get("close_tx"),
            realized_cashflow_pnl_usdc=r.get("realized_cashflow_pnl_usdc", r.get("pnl_usdc")),
            btc_move_usd=r.get("btc_move_usd"),
            skew=r.get("skew"),
            seconds_left_at_entry=r.get("seconds_left_at_entry"),
            threshold_price=r.get("threshold_price"),
            stake_usd=r.get("stake_usd"),
            fees_usdc=r.get("fees_usdc"),
            slippage_usdc=r.get("slippage_usdc"),
            gas_usdc=r.get("gas_usdc"),
            mode=r.get("mode", "dry_run"),
        )

    def _risk_state(
        self,
        features: Optional[contracts.Features] = None,
        snapshot: Optional[contracts.MarketSnapshot] = None,
    ) -> contracts.RiskState:
        prof = self.profile()
        summary = self._summary_raw()
        if snapshot is None:
            snapshot = self.latest_snapshot()
        age = snapshot.age_sec
        dead_man = bool(
            (not self.running)
            or (age is not None and age > prof.dead_man_sec)
            or (features is not None and bool(features.dead_man_tripped))
        )
        daily_loss_cap_usd = summary.get("daily_loss_cap_usd")
        if daily_loss_cap_usd is None and self.equity_usd is not None:
            daily_loss_cap_usd = round(self.equity_usd * prof.daily_max_loss_pct / 100.0, 2)
        op = self._open_position()
        return contracts.RiskState(
            ts=now_iso(),
            profile=self.profile_name,
            mode=self.mode,
            armed=self.armed,
            killed=self.killed,
            running=self.running and not self.killed,
            pnl_today=summary.get("pnl_today", 0.0) or 0.0,
            pnl_total=summary.get("pnl_total", 0.0) or 0.0,
            trades_today=summary.get("trades_today", 0) or 0,
            trades_total=summary.get("trades_total", 0) or 0,
            wins=summary.get("wins", 0) or 0,
            losses=summary.get("losses", 0) or 0,
            win_rate=summary.get("win_rate"),
            max_trades_per_day=summary.get("max_trades_per_day", prof.max_trades_per_day),
            trades_cap_used_pct=summary.get("trades_cap_used_pct"),
            daily_loss_cap_usd=daily_loss_cap_usd,
            daily_loss_cap_pct=summary.get("daily_loss_cap_pct", prof.daily_max_loss_pct),
            loss_cap_used_pct=summary.get("loss_cap_used_pct"),
            best_trade=summary.get("best_trade"),
            worst_trade=summary.get("worst_trade"),
            open_position=op.to_dict() if op is not None else None,
            dead_man_tripped=dead_man,
            age_sec=age,
        )

    def risk(self) -> contracts.RiskState:
        with self._lock:
            return self._risk_state()

    def equity(self, range_: str = "session") -> contracts.Account:
        with self._lock:
            curve: List[Dict[str, Any]] = []
            if self._reader is not None:
                try:
                    curve = self._reader.equity_curve() or []
                except Exception:
                    curve = []
            cum = curve[-1]["cum_pnl"] if curve else 0.0
            equity_usd = self.equity_usd
            if equity_usd is not None:
                equity_usd = round(equity_usd + (cum or 0.0), 6)
            return contracts.Account(
                ts=now_iso(),
                equity_usd=equity_usd,
                funder_address_masked=self._funder_masked,
                signature_type=self.signature_type,
                currency="USDC",
                equity_curve=curve,
            )

    def config(self) -> Dict[str, Any]:
        with self._lock:
            prof = self.profile()
            params = {
                "threshold_price": prof.threshold_price,
                "stake_usd": prof.stake_usd,
                "max_notional_usd": prof.max_notional_usd,
                "daily_max_loss_pct": prof.daily_max_loss_pct,
                "max_trades_per_day": prof.max_trades_per_day,
                "stop_loss_pct": prof.stop_loss_pct_from_entry,
                "exit_before_sec": prof.exit_before_sec,
                "hedge_enabled": 1 if prof.hedge_enabled else 0,
                "hedge_notional_usd": prof.hedge_notional_usd_max,
            }
            return {
                "schema_version": SCHEMA_VERSION,
                "ts": now_iso(),
                "profile": self.profile_name,
                "params": params,
                "ranges": {k: dict(v) for k, v in PARAM_RANGES.items()},
            }

    def health(self) -> Dict[str, Any]:
        with self._lock:
            st = self.status()
            snap = self.latest_snapshot()
            prof = self.profile()
            age = snap.age_sec if snap.age_sec is not None else 0
            dead_man = (not self.running) or age > prof.dead_man_sec
            return {
                "ok": st.running and not dead_man,
                "state": st.state,
                "age_sec": age,
                "dead_man_tripped": bool(dead_man),
            }

    # -- control (08 §4) — flips flags only; never places real orders ------
    def _write_command(self, command: str, payload: Dict[str, Any]) -> None:
        """Append an auditable command to a runtime command file (no execution)."""
        if self.runtime_dir is None:
            return
        try:
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            rec = {"ts": now_iso(), "command": command, **payload}
            with open(self.runtime_dir / "commands.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        except OSError:
            pass

    def start(self, profile: Optional[str] = None, mode: str = "dry_run") -> Dict[str, Any]:
        with self._lock:
            if mode not in ("dry_run", "live"):
                raise ValidationError("mode must be dry_run|live", {"mode": "dry_run|live"})
            if mode == "live" and not self.armed:
                raise PermissionError("not_armed")
            if profile is not None:
                if profile not in PROFILES:
                    raise ValidationError("unknown profile", {"profile": sorted(PROFILES)})
                self.profile_name = profile
            self.mode = mode
            self.running = True
            self._kill.reset()
            self._started_at = _utcnow()
            # Obtain an adapter handle to confirm the dry-run-by-default routing.
            # The backend NEVER places orders, so we never instantiate the live
            # adapter here (which would require creds): the factory returns Paper
            # for dry-run, and is_live records intent only.
            self._adapter = get_adapter(mode="dry_run", armed=False, profile=self.profile_name)
            self._write_command("start", {"profile": self.profile_name, "mode": self.mode})
            return {"ok": True, "profile": self.profile_name, "mode": self.mode}

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self.running = False
            self._write_command("stop", {})
            return {"ok": True}

    def kill(self, confirm: Optional[str] = None) -> Dict[str, Any]:
        """Always processable (08 §4). Blocks new entries + simulates safe close."""
        with self._lock:
            if confirm != _KILL_CONFIRM:
                raise ValidationError("confirm must equal 'KILL'", {"confirm": "KILL"})
            had_open = self._open_position() is not None and not self.killed
            self._kill.kill("operator_kill")
            self.running = False
            # Route any close through the (paper-by-default) adapter — never live
            # unless explicitly armed; we do not place real orders here.
            closed = 1 if had_open else 0
            skipped = 0
            self._write_command("kill", {"confirm": "KILL"})
            return {
                "killed": True,
                "blocking_new_entries": True,
                "positions_closed": closed,
                "positions_close_skipped": skipped,
            }

    def arm(self, confirm: Optional[str] = None, runbook_ack: bool = False) -> Dict[str, Any]:
        with self._lock:
            if confirm != _ARM_CONFIRM or runbook_ack is not True:
                raise ValidationError(
                    "arm requires confirm=='ARM LIVE' and runbook_ack==true",
                    {"confirm": "ARM LIVE", "runbook_ack": True},
                )
            self._arming.arm(confirm)
            self.mode = "live"
            self._write_command("arm", {})
            return {"ok": True, "armed": True, "mode": "live"}

    def disarm(self) -> Dict[str, Any]:
        with self._lock:
            self._arming.disarm()
            self.mode = "dry_run"
            self._write_command("disarm", {})
            return {"ok": True, "armed": False, "mode": "dry_run"}

    def set_profile(self, profile: Optional[str]) -> Dict[str, Any]:
        with self._lock:
            if profile not in PROFILES:
                raise ValidationError("unknown profile", {"profile": sorted(PROFILES)})
            self.profile_name = profile
            self._overrides = {}
            self._write_command("profile", {"profile": profile})
            return {"ok": True, "profile": profile}

    def update_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if not isinstance(params, dict) or not params:
                raise ValidationError("params object required", {"params": "object"})
            detail: Dict[str, Any] = {}
            cleaned: Dict[str, Any] = {}
            for key, val in params.items():
                rng = PARAM_RANGES.get(key)
                if rng is None:
                    detail[key] = "unknown param"
                    continue
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    detail[key] = "must be a number"
                    continue
                lo, hi = rng["min"], rng["max"]
                if num < lo or num > hi:
                    detail[key] = f"must be in [{lo},{hi}]"
                    continue
                # Caps cannot be set to disable themselves (08 §4).
                if key in _NON_DISABLING_CAPS and num <= 0:
                    detail[key] = "cap cannot disable itself"
                    continue
                cleaned[key] = num
            if detail:
                raise ValidationError("param out of range", detail)
            self._overrides.update(cleaned)
            self._write_command("config", {"params": cleaned})
            return {"ok": True}
