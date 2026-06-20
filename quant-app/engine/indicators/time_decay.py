"""
time_decay — time-to-close decay (`04 §6`).

    in_window = min_entry_seconds_left <= seconds_left <=
                (entry_window_target_sec + entry_window_tolerance_sec)   ⇒ [60,150]
    time_decay_score = clamp(1 - |seconds_left - target| / tolerance, 0, 1)
        (1 at 120s, →0 at 90s/150s edges)

Null handling: missing seconds_left ⇒ in_window False, score None (gate fails).
"""

from __future__ import annotations

from typing import Dict, Optional

from ._common import clamp


def time_decay(
    seconds_left: Optional[int],
    min_entry_seconds_left: int = 60,
    entry_window_target_sec: int = 120,
    entry_window_tolerance_sec: int = 30,
) -> Dict[str, object]:
    if seconds_left is None:
        return {"in_window": False, "time_decay_score": None, "seconds_left": None}

    upper = entry_window_target_sec + entry_window_tolerance_sec
    in_window = min_entry_seconds_left <= seconds_left <= upper

    if entry_window_tolerance_sec > 0:
        score = clamp(
            1.0 - abs(seconds_left - entry_window_target_sec) / entry_window_tolerance_sec,
            0.0,
            1.0,
        )
    else:
        score = 1.0 if seconds_left == entry_window_target_sec else 0.0

    return {
        "in_window": in_window,
        "time_decay_score": score,
        "seconds_left": seconds_left,
    }
