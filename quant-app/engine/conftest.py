"""Ensure the package parent (`quant-app/`) is importable as `engine` when pytest
is invoked from inside `engine/` (per the project's run instructions)."""

import os
import sys

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
