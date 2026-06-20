"""
staleness — heartbeat / quote-health master gate (`04 §7`).

    fresh = age_sec <= skip_if_quote_stale_sec_gt
    process_ok = running == true
    dead_man_tripped = (age_sec > dead_man_sec) or (not running)
    health_score = 1.0 if (fresh and process_ok) else 0.0

Null handling: missing age_sec ⇒ not fresh and dead_man_tripped True
(unknown age is treated as stale — fail safe).
"""

from __future__ import annotations

from typing import Dict, Optional


def staleness(
    age_sec: Optional[int],
    running: bool = True,
    skip_if_quote_stale_sec_gt: float = 8.0,
    dead_man_sec: float = 30.0,
) -> Dict[str, object]:
    process_ok = bool(running)

    if age_sec is None:
        fresh = False
        dead_man_tripped = True
    else:
        fresh = age_sec <= skip_if_quote_stale_sec_gt
        dead_man_tripped = (age_sec > dead_man_sec) or (not process_ok)

    health_score = 1.0 if (fresh and process_ok) else 0.0

    return {
        "fresh": fresh,
        "process_ok": process_ok,
        "dead_man_tripped": dead_man_tripped,
        "health_score": health_score,
    }
