"""Adapter factory — Paper by default, Polymarket only when explicitly live+armed.

This is the single entry point the API / trading loop uses to obtain an execution
adapter. It enforces the dry-run-by-default invariant (02 §1, 06 §7): unless the
caller passes both ``mode="live"`` and ``armed=True`` (and the live adapter's own
env-cred gate passes), it returns the offline :class:`PaperExecutionAdapter`.
"""

from __future__ import annotations

from typing import Any, Optional

from .adapter import ExecutionAdapter
from .paper import PaperExecutionAdapter


def get_adapter(
    mode: str = "dry_run",
    armed: bool = False,
    *,
    profile: str = "conservative",
    env: Optional[dict] = None,
    **kwargs: Any,
) -> ExecutionAdapter:
    """Return an execution adapter.

    * Default / anything other than (``mode="live"`` AND ``armed=True``) →
      :class:`PaperExecutionAdapter` (offline, no keys).
    * ``mode="live"`` AND ``armed=True`` → :class:`PolymarketExecutionAdapter`,
      which *additionally* requires all live env creds or it raises.

    The Polymarket import is deferred to this branch so the default path stays
    standard-library only.
    """
    if mode == "live" and armed:
        # Import only on the live branch (keeps the default path stdlib-only and
        # avoids importing the live module's surface when not needed).
        from .polymarket import PolymarketExecutionAdapter

        return PolymarketExecutionAdapter(
            armed=True,
            mode="live",
            profile=profile,
            env=env,
            **{k: v for k, v in kwargs.items() if k in {"clob_host", "stop_loss_pct"}},
        )

    # Dry-run by default for every other combination.
    paper_kwargs = {
        k: v
        for k, v in kwargs.items()
        if k
        in {
            "cost_model",
            "stop_loss_pct",
            "equity_usd",
            "seed",
            "jitter_ticks",
            "stake_usd",
            "threshold_price",
        }
    }
    return PaperExecutionAdapter(profile=profile, **paper_kwargs)
