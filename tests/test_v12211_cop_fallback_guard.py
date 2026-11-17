"""v1.22.11 #388: COP fallback must pass the MAX_COP gate."""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _c():
    return object.__new__(DaikinCycleMLCoordinator)


def test_fallback_above_max_rejected():
    s = SimpleNamespace(cop=None, attrs={"Stats: COP estimated": 15.0})
    assert _c()._resolve_cop_for_datasheet(s) is None


def test_snap_above_max_rejected():
    s = SimpleNamespace(cop=12.5, attrs={})
    assert _c()._resolve_cop_for_datasheet(s) is None


def test_both_missing_returns_none():
    s = SimpleNamespace(cop=None, attrs={})
    assert _c()._resolve_cop_for_datasheet(s) is None


def test_valid_fallback_unchanged():
    s = SimpleNamespace(cop=None, attrs={"Stats: COP estimated": 6.02})
    assert _c()._resolve_cop_for_datasheet(s) == 6.02
