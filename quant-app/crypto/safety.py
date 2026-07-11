"""Guardrails: Arming state machine, KillSwitch, DeadMansSwitch, redact().

These are the integration points the API / Risk Manager call (``06 §7``). All are
standard-library only and hold no key material. ``redact()`` is the canonical
secret-scrubber used by every adapter's error/repr path.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

# Default dead-man window (06 §7 / 05 Features.dead_man_tripped): trip when the
# heartbeat age exceeds this many seconds.
DEFAULT_DEAD_MAN_SEC = 30


# ---------------------------------------------------------------------------
# Secret redaction (06 §4: key/secrets never logged; addresses masked)
# ---------------------------------------------------------------------------
# Names of env vars / fields whose *values* must never surface in logs or errors.
_SECRET_ENV_NAMES = (
    "PM_PRIVATE_KEY",
    "PM_API_KEY",
    "PM_API_SECRET",
    "PM_API_PASSPHRASE",
)

# Hex blobs long enough to be a private key (32 bytes = 64 hex chars), with or
# without the 0x prefix. Catches a key leaked as a bare string.
_HEX_KEYLIKE = re.compile(r"\b(0x)?[0-9a-fA-F]{64,}\b")

# key=value or "key": "value" style assignments of any known secret name.
_ASSIGN_KEYLIKE = re.compile(
    r"(?i)\b(" + "|".join(_SECRET_ENV_NAMES) + r")\b\s*[:=]\s*[\"']?([^\s\"',}]+)"
)

_MASK = "***REDACTED***"


def redact(value: object, *, extra_secrets: Optional[Iterable[str]] = None) -> str:
    """Return ``str(value)`` with any key-like material masked.

    Masks: (1) the literal values of known secret env vars if present in the
    process env, (2) any ``SECRET_NAME=...`` / ``"SECRET_NAME": "..."`` assignment,
    (3) any standalone 64+ hex-char blob (private-key shaped). ``extra_secrets``
    lets callers scrub specific known values (e.g. a captured key) verbatim.

    This never raises on key material and is safe to call inside ``__repr__`` /
    exception formatting.
    """
    import os

    text = str(value)

    # 1. Scrub exact values pulled from env, if non-empty.
    concrete: list[str] = []
    for name in _SECRET_ENV_NAMES:
        v = os.environ.get(name)
        if v:
            concrete.append(v)
    if extra_secrets:
        concrete.extend(s for s in extra_secrets if s)
    # Longest first so substrings don't leave fragments behind.
    for secret in sorted(set(concrete), key=len, reverse=True):
        if secret and secret in text:
            text = text.replace(secret, _MASK)

    # 2. Scrub explicit assignments (covers values not in this process's env).
    text = _ASSIGN_KEYLIKE.sub(lambda m: f"{m.group(1)}={_MASK}", text)

    # 3. Scrub standalone private-key-shaped hex blobs.
    text = _HEX_KEYLIKE.sub(_MASK, text)

    return text


def mask_address(addr: Optional[str]) -> Optional[str]:
    """Mask a wallet/funder address to ``0x1234…ab12`` form (05 §8)."""
    if not addr:
        return None
    a = str(addr)
    if len(a) <= 10:
        return a
    return f"{a[:6]}…{a[-4:]}"


# ---------------------------------------------------------------------------
# Arming state machine (06 §7: disarmed → armed requires explicit confirm token)
# ---------------------------------------------------------------------------
class ArmingError(RuntimeError):
    """Raised on an invalid arming transition or a bad confirm token."""


@dataclass
class Arming:
    """Two-state arming gate: ``disarmed`` (default) → ``armed``.

    Transition to ``armed`` requires the caller to present the exact
    ``confirm_token`` (a typed confirmation per 06 §3/§7). There is no way to
    reach ``armed`` without it. ``disarm()`` always succeeds (fail-safe).
    """

    confirm_token: str
    _armed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not self.confirm_token:
            raise ArmingError("confirm_token must be a non-empty string")

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def state(self) -> str:
        return "armed" if self._armed else "disarmed"

    def arm(self, token: str) -> bool:
        """Transition disarmed → armed iff ``token`` matches ``confirm_token``.

        Raises :class:`ArmingError` on mismatch. Returns True on success
        (idempotent if already armed with a valid token).
        """
        if token != self.confirm_token:
            # Never echo the supplied token (could be sensitive).
            raise ArmingError("arming refused: confirmation token mismatch")
        self._armed = True
        return True

    def disarm(self) -> None:
        """Return to the safe (disarmed) state. Always allowed."""
        self._armed = False

    def __repr__(self) -> str:  # never leak the token
        return f"Arming(state={self.state!r}, confirm_token={_MASK})"


# ---------------------------------------------------------------------------
# Kill switch (06 §7 / 03 §6): block new entries, force safe close
# ---------------------------------------------------------------------------
@dataclass
class KillSwitch:
    """Operator kill switch.

    When ``killed`` is set: new entries are blocked (:meth:`allow_new_entry`
    returns False) and open positions should be force-closed
    (:meth:`should_close_all` returns True). The kill path is fail-safe: once
    tripped it stays tripped until explicitly :meth:`reset`.
    """

    _killed: bool = field(default=False, init=False)
    reason: Optional[str] = field(default=None, init=False)

    @property
    def killed(self) -> bool:
        return self._killed

    def kill(self, reason: str = "operator_kill") -> None:
        self._killed = True
        self.reason = reason

    def reset(self) -> None:
        self._killed = False
        self.reason = None

    def allow_new_entry(self) -> bool:
        """False when killed — Risk Manager must veto new entries."""
        return not self._killed

    def should_close_all(self) -> bool:
        """True when killed — adapter must attempt a safe close of all positions."""
        return self._killed

    def assert_can_enter(self) -> None:
        """Raise if a new entry is attempted while killed."""
        if self._killed:
            raise RuntimeError(f"kill switch engaged: new entries blocked ({self.reason})")


# ---------------------------------------------------------------------------
# Dead-man's switch (06 §7 / 05 Features.dead_man_tripped)
# ---------------------------------------------------------------------------
@dataclass
class DeadMansSwitch:
    """Independent liveness guard.

    Trips when the last heartbeat is older than ``dead_man_sec`` OR the trading
    process is reported not-running. A dead bot with an open position cannot
    self-stop, so this is checked independently of the API (06 §7, 02 §6).
    """

    dead_man_sec: int = DEFAULT_DEAD_MAN_SEC
    _last_heartbeat: Optional[float] = field(default=None, init=False)
    _process_running: bool = field(default=True, init=False)

    def heartbeat(self, now: Optional[float] = None) -> None:
        """Record a liveness ping (monotonic-ish wall clock)."""
        self._last_heartbeat = time.time() if now is None else now

    def set_process_running(self, running: bool) -> None:
        self._process_running = bool(running)

    def age_sec(self, now: Optional[float] = None) -> Optional[int]:
        """Seconds since the last heartbeat, or ``None`` if never beat."""
        if self._last_heartbeat is None:
            return None
        ref = time.time() if now is None else now
        return int(max(0, ref - self._last_heartbeat))

    def tripped(self, now: Optional[float] = None) -> bool:
        """True if the process is dead OR the heartbeat is stale/never-seen."""
        if not self._process_running:
            return True
        age = self.age_sec(now)
        if age is None:
            return True
        return age > self.dead_man_sec

    def assert_ok(self, now: Optional[float] = None) -> None:
        """Raise if the dead-man's switch has tripped."""
        if self.tripped(now):
            raise RuntimeError(
                f"dead-man's switch tripped "
                f"(process_running={self._process_running}, age_sec={self.age_sec(now)}, "
                f"limit={self.dead_man_sec})"
            )
