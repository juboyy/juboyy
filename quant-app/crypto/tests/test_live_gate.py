"""Live adapter refuses to operate without explicit arming + env creds.

These tests NEVER hit the network and NEVER require a real key. They assert the
gate: the live path is unreachable without armed=True + mode='live' + all env
creds present. ``py_clob_client`` is never imported because no test reaches
``_ensure_client``.
"""

import pytest

from crypto.factory import get_adapter
from crypto.paper import PaperExecutionAdapter
from crypto.polymarket import (
    LiveGateError,
    PolymarketExecutionAdapter,
)

# A complete fake env (dummy values, NOT a real key) to exercise the cred gate.
FULL_ENV = {
    "PM_PRIVATE_KEY": "0x" + "00" * 32,
    "PM_FUNDER": "0xFunderAddress0000000000000000000000000000",
    "PM_SIGNATURE_TYPE": "2",
    "PM_API_KEY": "dummy-key",
    "PM_API_SECRET": "dummy-secret",
    "PM_API_PASSPHRASE": "dummy-pass",
}


# --- factory defaults to paper ------------------------------------------
def test_factory_defaults_to_paper():
    a = get_adapter()
    assert isinstance(a, PaperExecutionAdapter)
    assert a.mode == "dry_run"


def test_factory_dry_run_even_if_armed():
    # armed alone (without live mode) must NOT yield a live adapter.
    a = get_adapter(mode="dry_run", armed=True)
    assert isinstance(a, PaperExecutionAdapter)


def test_factory_live_without_armed_is_paper():
    a = get_adapter(mode="live", armed=False)
    assert isinstance(a, PaperExecutionAdapter)


# --- live construction gate ---------------------------------------------
def test_live_refuses_when_disarmed():
    with pytest.raises(LiveGateError):
        PolymarketExecutionAdapter(armed=False, mode="live", env=FULL_ENV)


def test_live_refuses_when_not_live_mode():
    with pytest.raises(LiveGateError):
        PolymarketExecutionAdapter(armed=True, mode="dry_run", env=FULL_ENV)


def test_live_refuses_when_env_missing():
    # armed + live, but NO creds → refuse.
    with pytest.raises(LiveGateError) as exc:
        PolymarketExecutionAdapter(armed=True, mode="live", env={})
    msg = str(exc.value)
    assert "PM_PRIVATE_KEY" in msg


def test_live_refuses_partial_env():
    partial = dict(FULL_ENV)
    del partial["PM_API_SECRET"]
    with pytest.raises(LiveGateError) as exc:
        PolymarketExecutionAdapter(armed=True, mode="live", env=partial)
    assert "PM_API_SECRET" in str(exc.value)


def test_live_refuses_missing_funder():
    no_funder = {k: v for k, v in FULL_ENV.items() if k != "PM_FUNDER"}
    with pytest.raises(LiveGateError) as exc:
        PolymarketExecutionAdapter(armed=True, mode="live", env=no_funder)
    assert "PM_FUNDER" in str(exc.value)


def test_factory_live_armed_but_no_env_raises():
    # The factory delegates the cred gate to the live adapter.
    with pytest.raises(LiveGateError):
        get_adapter(mode="live", armed=True, env={})


# --- host allow-list -----------------------------------------------------
def test_live_refuses_custom_host():
    with pytest.raises(LiveGateError) as exc:
        PolymarketExecutionAdapter(
            armed=True, mode="live", env=FULL_ENV, clob_host="https://evil.example.com"
        )
    assert "host" in str(exc.value).lower()


# --- constructed live adapter never leaks the key -----------------------
def test_live_adapter_repr_never_leaks_key():
    a = PolymarketExecutionAdapter(armed=True, mode="live", env=FULL_ENV)
    r = repr(a)
    assert FULL_ENV["PM_PRIVATE_KEY"] not in r
    assert "0x00" not in r  # key bytes absent
    # funder is masked, not raw.
    assert FULL_ENV["PM_FUNDER"] not in r


def test_live_adapter_does_not_store_key_on_instance():
    a = PolymarketExecutionAdapter(armed=True, mode="live", env=FULL_ENV)
    # The private key must not be stored as any attribute value.
    for name, val in vars(a).items():
        if name == "_env":
            continue  # the injected env dict legitimately holds it (caller-owned)
        assert FULL_ENV["PM_PRIVATE_KEY"] not in repr(val)


def test_live_balance_masks_funder_and_omits_key():
    a = PolymarketExecutionAdapter(armed=True, mode="live", env=FULL_ENV)
    bal = a.balance()  # does not require network
    assert bal.signature_type == 2
    assert bal.funder_address_masked is not None
    assert FULL_ENV["PM_FUNDER"] not in (bal.funder_address_masked or "")
    assert "…" in bal.funder_address_masked
    # The serialized balance must not contain the key.
    assert FULL_ENV["PM_PRIVATE_KEY"] not in repr(bal.to_dict())


def test_live_operations_are_gated_stubs_not_network():
    # Even when armed+creds, the order paths are gated stubs. In this build
    # py_clob_client is NOT installed, so _ensure_client() raises LiveGateError
    # (lazy import fails) before any network call. Either way, no order is placed
    # and the failure is a clear gate error, never a real network submission.
    a = PolymarketExecutionAdapter(armed=True, mode="live", env=FULL_ENV)
    with pytest.raises((NotImplementedError, LiveGateError)):
        a.quote("btc-updown-2026-06-20-1405")
