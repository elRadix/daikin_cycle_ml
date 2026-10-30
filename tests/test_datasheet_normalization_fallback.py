"""v1.15.1 — outdoor-temp fallback for datasheet COP normalization."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _snap(snap_attrs: dict | None, last_record: dict | None) -> MagicMock:
    s = MagicMock()
    s.attrs = snap_attrs
    s.last_record = last_record
    return s


def _resolver() -> DaikinCycleMLCoordinator:
    return DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)


def test_primary_uses_last_record_outdoor_temp():
    c = _resolver()
    assert c._resolve_outdoor_temp(
        _snap({"R1T-Outdoor air temp.": 15.3}, {"outdoor_temp": 8.0})
    ) == 8.0


def test_fallback_uses_snap_attrs_when_last_record_lacks_temp():
    c = _resolver()
    assert c._resolve_outdoor_temp(
        _snap({"R1T-Outdoor air temp.": 15.3}, {})
    ) == 15.3


def test_fallback_handles_none_last_record():
    c = _resolver()
    assert c._resolve_outdoor_temp(
        _snap({"R1T-Outdoor air temp.": 5.5}, None)
    ) == 5.5


def test_returns_none_when_neither_source_has_temp():
    c = _resolver()
    assert c._resolve_outdoor_temp(_snap({}, {})) is None


def test_returns_none_when_snap_attrs_is_none():
    c = _resolver()
    assert c._resolve_outdoor_temp(
        _snap(None, {"outdoor_temp": 4.0})
    ) == 4.0


def test_returns_none_when_both_missing():
    c = _resolver()
    assert c._resolve_outdoor_temp(_snap(None, None)) is None
