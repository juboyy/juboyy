"""Make the ``crypto`` package importable when pytest runs from inside crypto/.

Adds the quant-app root (parent of crypto/) to sys.path so ``import crypto.*``
resolves regardless of the pytest invocation directory.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CRYPTO_DIR = os.path.dirname(_HERE)
_QUANT_APP = os.path.dirname(_CRYPTO_DIR)

for p in (_QUANT_APP, _CRYPTO_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)
