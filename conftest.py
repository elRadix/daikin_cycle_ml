"""Root conftest: ensure repo root on sys.path for both local + CI.

The pytest-homeassistant-custom-component plugin rewrites sys.path
during collection, dropping the repo root. Neither PYTHONPATH env
nor [tool.pytest.ini_options] pythonpath reliably survives that.

Inserting here -- in a root-level conftest -- runs after pytest
startup but before test collection, and is not overwritten.
"""
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
