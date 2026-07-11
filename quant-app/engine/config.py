"""
config.py — Default profile parameters for the deterministic engine.

These mirror `dashboard/config_defaults.json` and the parameter tables in
`docs/03_QUANT_STRATEGY.md` §7 and `docs/04_INDICATORS.md` §8. Everything here is
plain data: no I/O, no clock reads. A `Profile` is a frozen dataclass holding the
full parameter set; the two canonical profiles (`conservative`, `aggressive`) are
constructed from the same defaults the dashboard ships.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict


@dataclass(frozen=True)
class Profile:
    """A versioned bundle of strategy + scoring parameters.

    All fields have defaults taken from `03 §7` / `04 §8` / `config_defaults.json`.
    Construct `Profile.conservative()` / `Profile.aggressive()` for the canonical
    profiles, or override any field for tuning/backtest sweeps.
    """

    name: str = "conservative"

    # -- entry window / timing (03 §7, 04 §6) --
    entry_window_target_sec: int = 120
    entry_window_tolerance_sec: int = 30
    min_entry_seconds_left: int = 60
    exit_before_sec: int = 20

    # -- momentum (03 §7, 04 §1) --
    btc_move_usd_min: float = 70.0
    btc_move_usd_max_reference: float = 100.0

    # -- price gates (03 §3, 04 §8) --
    threshold_price: float = 0.70
    max_entry_ask: float = 0.92
    enter_score_min: float = 0.60

    # -- sizing (03 §4) --
    stake_usd: float = 5.0
    max_notional_usd: float = 8.0
    risk_per_trade_pct_equity: float = 8.0

    # -- risk caps (03 §6) --
    daily_max_loss_pct: float = 10.0
    max_trades_per_day: int = 12

    # -- stop loss (03 §6) --
    stop_loss_pct_from_entry: float = 0.25

    # -- hedge (03 §5) --
    hedge_enabled: bool = True
    hedge_trigger_side_price_gte: float = 0.95
    hedge_trigger_seconds_left_lte: int = 45
    hedge_notional_usd_min: float = 1.0
    hedge_notional_usd_max: float = 2.0

    # -- execution safety (03 §7, 04 §4/§7) --
    skip_if_quote_stale_sec_gt: float = 8.0
    skip_if_spread_gt: float = 0.03
    skip_if_top_ask_notional_usd_lt: float = 30.0
    dead_man_sec: float = 30.0
    poll_sec: int = 5

    # -- indicator references (04 §2/§3/§4/§8) --
    lookback_polls: int = 24
    rv_window: int = 24
    rv_cap_usd: float = 150.0
    spread_ref: float = 0.005
    notional_ref: float = 100.0
    skew_score_cap: float = 0.95
    imbalance_veto: float = -0.6

    # -- composite weights (04 §8) --
    w_mom: float = 0.35
    w_skew: float = 0.25
    w_liq: float = 0.15
    w_imb: float = 0.10
    w_time: float = 0.15
    w_vol: float = 0.20
    agreement_bonus: float = 0.05

    # -- scoring model id (05 Signal.model_version, 04 §9) --
    model_version: str = "rule-1.0"

    # -- cost model (03 §8) --
    slip_ticks: float = 1.0
    tick: float = 0.01
    gas_usdc: float = 0.02
    fee_bps: float = 0.0

    # -- bankroll (optional; 03 §4 risk cap) --
    equity_usd: float | None = None

    @classmethod
    def conservative(cls, **overrides) -> "Profile":
        return cls(name="conservative", **overrides)

    @classmethod
    def aggressive(cls, **overrides) -> "Profile":
        base = dict(
            name="aggressive",
            max_notional_usd=15.0,
            risk_per_trade_pct_equity=15.0,
            daily_max_loss_pct=15.0,
            max_trades_per_day=20,
            stop_loss_pct_from_entry=0.30,
            hedge_trigger_side_price_gte=0.93,
            hedge_trigger_seconds_left_lte=50,
            hedge_notional_usd_max=3.0,
        )
        base.update(overrides)
        return cls(**base)

    def as_dict(self) -> Dict:
        return asdict(self)


PROFILES = {
    "conservative": Profile.conservative,
    "aggressive": Profile.aggressive,
}


def get_profile(name: str = "conservative", **overrides) -> Profile:
    factory = PROFILES.get(name)
    if factory is None:
        raise ValueError(f"unknown profile {name!r}; choose from {sorted(PROFILES)}")
    return factory(**overrides)
