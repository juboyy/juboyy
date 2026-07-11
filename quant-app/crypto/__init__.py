"""Crypto execution + wallet adapter for the quant cockpit.

Security model (see ``crypto/README.md`` and ``docs/06_SECURITY.md``):

- **Non-custodial.** ``PM_PRIVATE_KEY`` is read ONLY from env, ONLY inside the
  live adapter process, and is NEVER logged, returned, written to disk, or passed
  to the API / mobile layers.
- **Dry-run by default.** The default adapter is :class:`crypto.paper.PaperExecutionAdapter`,
  which is fully offline and never touches keys. Live execution
  (:class:`crypto.polymarket.PolymarketExecutionAdapter`) is impossible without an
  explicit ``armed=True`` + ``mode="live"`` *and* the presence of the env creds.

Use :func:`crypto.factory.get_adapter` to obtain an adapter; it returns Paper by
default and Polymarket only when explicitly live + armed.
"""

from .adapter import (
    ExecutionAdapter,
    Order,
    Position,
    Quote,
    TradeResult,
)
from .factory import get_adapter
from .paper import PaperExecutionAdapter
from .safety import (
    Arming,
    ArmingError,
    DeadMansSwitch,
    KillSwitch,
    redact,
)

__all__ = [
    "ExecutionAdapter",
    "Order",
    "Position",
    "Quote",
    "TradeResult",
    "PaperExecutionAdapter",
    "get_adapter",
    "Arming",
    "ArmingError",
    "DeadMansSwitch",
    "KillSwitch",
    "redact",
]
