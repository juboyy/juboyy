"""Ensure the package parent (`quant-app/`) is importable so `import strategies.*`,
`engine.*`, `crypto.*`, and `runtime_paths` resolve regardless of the pytest
invocation directory."""

import os
import sys

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
