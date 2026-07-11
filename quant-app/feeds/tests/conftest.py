"""Shared pytest fixtures + path bootstrap so ``engine``/``feeds`` import when
pytest is run from anywhere under quant-app/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure quant-app/ (the package root holding both `engine` and `feeds`) is on
# sys.path regardless of pytest's rootdir / invocation cwd.
QUANT_APP = Path(__file__).resolve().parents[2]
if str(QUANT_APP) not in sys.path:
    sys.path.insert(0, str(QUANT_APP))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str):
    with open(FIXTURES / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def gamma_events():
    return load_fixture("gamma_events.json")


@pytest.fixture
def clob_book_up():
    return load_fixture("clob_book_up.json")


@pytest.fixture
def clob_book_down():
    return load_fixture("clob_book_down.json")


@pytest.fixture
def coinbase_spot():
    return load_fixture("coinbase_spot.json")


@pytest.fixture
def binance_spot():
    return load_fixture("binance_spot.json")
