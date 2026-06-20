"""
parser.py — Reads the runtime artifacts produced by the
`5min-btc-polymarket` bot and turns them into structured data
for the dashboard.

The bot writes (see scripts/btc5m_ctl.sh and btc5m_latest_report.py in the
upstream project):

    runtime/btc5m.pid                  -> process id of the running session
    runtime/btc5m.meta.json            -> JSON metadata (start ts, profile, params)
    runtime/btc5m_<profile>_<UTC>.log  -> per-session log; tail contains a JSON
                                          trade result object
    runtime/latest.log                 -> symlink to the active log

For richer, dashboard-friendly streaming this module also understands two
optional files the bot can emit (and that demo mode generates):

    runtime/btc5m_events.jsonl         -> one JSON trade record per line
    runtime/btc5m_signal.json          -> latest live signal snapshot

Everything degrades gracefully: missing files just mean empty sections.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone, date
from pathlib import Path


# ---------------------------------------------------------------------------
# Low level helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_ts(value):
    """Parse an ISO8601 / epoch timestamp into an aware datetime (UTC)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        v = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


# Scan a blob of text for top-level balanced JSON objects.
_JSON_OBJ = re.compile(r"\{")


def _extract_json_objects(text):
    """Yield every balanced top-level JSON object found in *text*."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        start = i
        while i < n:
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = text[start:i + 1]
                        try:
                            out.append(json.loads(chunk))
                        except ValueError:
                            pass
                        i += 1
                        break
            i += 1
    return out


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class RuntimeReader:
    def __init__(self, runtime_dir: str, config: dict | None = None):
        self.dir = Path(runtime_dir)
        self.config = config or {}

    # -- bot status --------------------------------------------------------
    def status(self):
        meta = _read_json(self.dir / "btc5m.meta.json") or {}
        pid = None
        pid_file = self.dir / "btc5m.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
            except (OSError, ValueError):
                pid = None
        if pid is None:
            pid = meta.get("pid")

        running = bool(pid) and _pid_alive(pid)
        started = _parse_ts(meta.get("start_ts") or meta.get("start") or meta.get("started_at"))
        uptime_sec = None
        if running and started:
            uptime_sec = max(0, int((_utcnow() - started).total_seconds()))

        return {
            "running": running,
            "pid": pid,
            "profile": meta.get("profile"),
            "started_at": started.isoformat() if started else None,
            "uptime_sec": uptime_sec,
            "params": {
                k: meta.get(k)
                for k in (
                    "threshold", "stake_usd", "stop_loss_pct", "exit_before_sec",
                    "min_entry_seconds_left", "entry_timeout_min", "poll_sec",
                    "execute",
                )
                if k in meta
            },
            "log_path": meta.get("log_path"),
        }

    # -- live signal -------------------------------------------------------
    def signal(self):
        sig = _read_json(self.dir / "btc5m_signal.json")
        if sig:
            sig = dict(sig)
            sig["age_sec"] = self._age(sig.get("ts"))
            return sig
        return None

    def _age(self, ts):
        dt = _parse_ts(ts)
        if not dt:
            return None
        return max(0, int((_utcnow() - dt).total_seconds()))

    # -- trades ------------------------------------------------------------
    def trades(self, limit=200):
        records = []

        # Preferred: structured event stream (one JSON per line).
        jsonl = self.dir / "btc5m_events.jsonl"
        if jsonl.exists():
            try:
                for line in jsonl.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        continue
            except OSError:
                pass

        # Fallback: scan per-session logs for tail JSON trade results.
        if not records:
            for log in sorted(self.dir.glob("btc5m_*.log")):
                try:
                    text = log.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for obj in _extract_json_objects(text):
                    if "realized_cashflow_pnl_usdc" in obj or "opened" in obj:
                        obj.setdefault("ts", self._log_ts_from_name(log.name))
                        obj.setdefault("profile", self._profile_from_name(log.name))
                        records.append(obj)

        records = [self._normalize_trade(r) for r in records]
        records.sort(key=lambda r: r.get("ts") or "", reverse=True)
        return records[:limit]

    @staticmethod
    def _log_ts_from_name(name):
        m = re.search(r"_(\d{8}T\d{6})", name)
        if m:
            try:
                dt = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                return None
        return None

    @staticmethod
    def _profile_from_name(name):
        m = re.search(r"btc5m_([a-z]+)_", name)
        return m.group(1) if m else None

    @staticmethod
    def _normalize_trade(r):
        opened = r.get("opened") or {}
        closed = r.get("closed") or {}
        pnl = r.get("realized_cashflow_pnl_usdc")
        try:
            pnl = float(pnl) if pnl is not None else None
        except (TypeError, ValueError):
            pnl = None
        return {
            "ts": r.get("ts"),
            "profile": r.get("profile"),
            "result": r.get("result"),
            "side": opened.get("side"),
            "market_slug": opened.get("market_slug"),
            "cost_usdc": opened.get("cost_usdc"),
            "open_tx": opened.get("open_tx"),
            "close_success": closed.get("close_success"),
            "close_status": closed.get("close_status"),
            "close_skipped": closed.get("close_skipped"),
            "close_tx": closed.get("close_tx"),
            "pnl_usdc": pnl,
            "btc_move_usd": r.get("btc_move_usd"),
            "skew": r.get("skew"),
            "seconds_left_at_entry": r.get("seconds_left_at_entry"),
            "entry_price": r.get("entry_price"),
            "threshold_price": r.get("threshold_price"),
            "stake_usd": r.get("stake_usd"),
        }

    # -- aggregated KPIs ---------------------------------------------------
    def summary(self, trades=None, status=None):
        trades = self.trades() if trades is None else trades
        status = self.status() if status is None else status
        profile = status.get("profile")
        caps = self._profile_caps(profile)

        today = _utcnow().date()
        today_trades = [t for t in trades if self._is_today(t.get("ts"), today)]

        def _sum(items):
            return round(sum((t.get("pnl_usdc") or 0.0) for t in items), 4)

        wins = [t for t in trades if (t.get("pnl_usdc") or 0) > 0]
        losses = [t for t in trades if (t.get("pnl_usdc") or 0) < 0]
        settled = [t for t in trades if t.get("pnl_usdc") is not None]

        pnl_today = _sum(today_trades)
        daily_loss_cap_usd = caps.get("daily_max_loss_usd")
        loss_used_pct = None
        if daily_loss_cap_usd and pnl_today < 0:
            loss_used_pct = round(min(100.0, abs(pnl_today) / daily_loss_cap_usd * 100), 1)

        open_position = next(
            (t for t in trades if not t.get("close_tx") and not t.get("close_skipped")
             and t.get("open_tx")),
            None,
        )

        return {
            "pnl_total": _sum(trades),
            "pnl_today": pnl_today,
            "trades_total": len(trades),
            "trades_today": len(today_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(settled) * 100, 1) if settled else None,
            "best_trade": max((t.get("pnl_usdc") or 0) for t in settled) if settled else None,
            "worst_trade": min((t.get("pnl_usdc") or 0) for t in settled) if settled else None,
            "max_trades_per_day": caps.get("max_trades_per_day"),
            "daily_loss_cap_usd": daily_loss_cap_usd,
            "daily_loss_cap_pct": caps.get("daily_max_loss_pct"),
            "loss_cap_used_pct": loss_used_pct,
            "trades_cap_used_pct": (
                round(len(today_trades) / caps["max_trades_per_day"] * 100, 1)
                if caps.get("max_trades_per_day") else None
            ),
            "open_position": open_position,
        }

    def _profile_caps(self, profile):
        prof = ((self.config.get("profiles") or {}).get(profile) or {})
        sizing = prof.get("sizing") or {}
        daily_pct = sizing.get("daily_max_loss_pct")
        # Estimate USD cap from stake/notional if equity unknown.
        notional = sizing.get("max_notional_usd")
        equity_guess = self.config.get("equity_usd")
        daily_loss_usd = None
        if daily_pct is not None and equity_guess:
            daily_loss_usd = round(equity_guess * daily_pct / 100.0, 2)
        elif daily_pct is not None and notional:
            # No equity known: express cap as pct of (notional * max trades) heuristic.
            mt = sizing.get("max_trades_per_day") or 1
            daily_loss_usd = round(notional * mt * daily_pct / 100.0, 2)
        return {
            "max_trades_per_day": sizing.get("max_trades_per_day"),
            "daily_max_loss_pct": daily_pct,
            "daily_max_loss_usd": daily_loss_usd,
            "max_notional_usd": notional,
            "stake_usd": sizing.get("stake_usd"),
        }

    @staticmethod
    def _is_today(ts, today):
        dt = _parse_ts(ts)
        return bool(dt) and dt.date() == today

    # -- equity curve ------------------------------------------------------
    def equity_curve(self, trades=None):
        trades = self.trades() if trades is None else trades
        chrono = sorted(
            [t for t in trades if t.get("pnl_usdc") is not None],
            key=lambda t: t.get("ts") or "",
        )
        cum = 0.0
        points = []
        for t in chrono:
            cum += t.get("pnl_usdc") or 0.0
            points.append({"ts": t.get("ts"), "cum_pnl": round(cum, 4),
                           "pnl": t.get("pnl_usdc")})
        return points

    # -- logs --------------------------------------------------------------
    def log_tail(self, lines=120):
        target = None
        latest = self.dir / "latest.log"
        if latest.exists():
            target = latest
        else:
            logs = sorted(self.dir.glob("btc5m_*.log"),
                          key=lambda p: p.stat().st_mtime if p.exists() else 0)
            if logs:
                target = logs[-1]
        if not target:
            return []
        try:
            data = target.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return []
        return data[-lines:]
