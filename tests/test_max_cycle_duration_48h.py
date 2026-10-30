"""v1.15.1 — MAX_CYCLE_DURATION_S must allow long modulating runs (>=24h)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from custom_components.daikin_cycle_ml.const import MAX_CYCLE_DURATION_S


def test_cap_is_at_least_24h():
    """Regression: 4h cap truncated 18h real runs on ESPAltherma 2 beta."""
    assert MAX_CYCLE_DURATION_S >= 24 * 3600.0


def test_cap_allows_18h8m_real_cycle():
    """rogervdh's ESPAltherma reading: 18h 8min single cycle."""
    eighteen_h_8m = 18 * 3600 + 8 * 60
    assert eighteen_h_8m < MAX_CYCLE_DURATION_S


def test_cap_still_finishes_runaway_at_48h():
    """R315 safety net still fires — not a functional cap, a runaway guard."""
    assert 48 * 3600.0 <= MAX_CYCLE_DURATION_S
