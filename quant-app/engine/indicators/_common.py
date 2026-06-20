"""Shared helpers for indicators. Pure, no I/O."""

from __future__ import annotations

from typing import Optional

UP = "up"
DOWN = "down"


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp x to [lo, hi]."""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
