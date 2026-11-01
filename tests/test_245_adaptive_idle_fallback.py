"""v1.19.2 (#245) — adaptive threshold fallback when HP is idle.

Prior to this fix, `snap.mode` was "unknown" whenever the HP was idle
(90-99% of the time). Adaptive-threshold lookups using `snap.mode`
directly therefore queried `_run_min["unknown"]`, which is always empty,
and returned None — even with 74+ heating samples recorded.

This test file covers:
  - AdaptiveThresholds.dominant_mode() in isolation
  - DaikinCycleMLCoordinator._resolve_adaptive_mode() fallback chain
  - End-to-end sensor value + alert threshold behavior at idle
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    AdaptiveThresholds,
)


def _build_adaptive(
    min_samples: int = 3,
    heating_runs: list[float] | None = None,
    dhw_runs: list[float] | None = None,
) -> AdaptiveThresholds:
    at = AdaptiveThresholds(min_samples=min_samples)
    for dur_min in heating_runs or []:
        at.observe_cycle("heating", dur_min * 60.0)
    for dur_min in dhw_runs or []:
        at.observe_cycle("dhw", dur_min * 60.0)
    return at


def _make_coord(
    adaptive: AdaptiveThresholds,
    *,
    data: Any = None,
    enabled: bool = True,
) -> Any:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.adaptive = adaptive
    c.options = {"adaptive_thresholds_enabled": enabled}
    c.data = data
    return c


def _fake_data(mode: str, last_mode: str | None = None) -> Any:
    d = MagicMock()
    d.mode = mode
    d.last_record = {"mode": last_mode} if last_mode is not None else None
    return d


class TestDominantMode:
    def test_empty_returns_none(self) -> None:
        at = AdaptiveThresholds(min_samples=1)
        assert at.dominant_mode() is None

    def test_heating_dominant(self) -> None:
        at = _build_adaptive(heating_runs=[10, 20, 30], dhw_runs=[5])
        assert at.dominant_mode() == "heating"

    def test_dhw_dominant(self) -> None:
        at = _build_adaptive(heating_runs=[10], dhw_runs=[5, 15, 25])
        assert at.dominant_mode() == "dhw"


class TestResolveAdaptiveMode:
    def test_running_heating(self) -> None:
        at = AdaptiveThresholds(min_samples=1)
        c = _make_coord(at, data=_fake_data("heating", "dhw"))
        assert c._resolve_adaptive_mode() == "heating"

    def test_running_dhw(self) -> None:
        at = AdaptiveThresholds(min_samples=1)
        c = _make_coord(at, data=_fake_data("dhw", "heating"))
        assert c._resolve_adaptive_mode() == "dhw"

    def test_idle_uses_last_record(self) -> None:
        at = AdaptiveThresholds(min_samples=1)
        c = _make_coord(at, data=_fake_data("unknown", "heating"))
        assert c._resolve_adaptive_mode() == "heating"

    def test_idle_falls_back_to_dominant(self) -> None:
        at = _build_adaptive(heating_runs=[10, 20, 30])
        c = _make_coord(at, data=_fake_data("unknown", "unknown"))
        assert c._resolve_adaptive_mode() == "heating"

    def test_idle_no_samples_returns_none(self) -> None:
        at = AdaptiveThresholds(min_samples=1)
        c = _make_coord(at, data=_fake_data("unknown", None))
        assert c._resolve_adaptive_mode() is None

    def test_data_none_returns_none(self) -> None:
        at = AdaptiveThresholds(min_samples=1)
        c = _make_coord(at, data=None)
        assert c._resolve_adaptive_mode() is None

    def test_adaptive_raises_returns_none(self) -> None:
        at = MagicMock()
        at.dominant_mode = MagicMock(side_effect=RuntimeError("boom"))
        c = _make_coord(at, data=_fake_data("unknown", None))
        assert c._resolve_adaptive_mode() is None


class TestEndToEnd:
    def test_sensor_value_learned_when_idle(self) -> None:
        at = _build_adaptive(heating_runs=[10, 20, 30])
        c = _make_coord(at, data=_fake_data("unknown", "heating"))
        mode = c._resolve_adaptive_mode()
        assert mode == "heating"
        assert at.learn_short_run_min(mode) is not None

    def test_effective_threshold_uses_learned_when_idle(self) -> None:
        at = _build_adaptive(heating_runs=[10, 20, 30])
        c = _make_coord(at, data=_fake_data("unknown", "heating"))
        # Default is 20 — learned p20 of 10/20/30 should differ
        val = c._effective_threshold("short_run_threshold_min", 20)
        assert val != 20

    def test_effective_threshold_returns_default_when_disabled(self) -> None:
        at = _build_adaptive(heating_runs=[10, 20, 30])
        c = _make_coord(at, data=_fake_data("unknown", "heating"), enabled=False)
        assert c._effective_threshold("short_run_threshold_min", 99) == 99

    def test_effective_threshold_returns_default_when_no_samples(self) -> None:
        at = AdaptiveThresholds(min_samples=1)
        c = _make_coord(at, data=_fake_data("unknown", None))
        assert c._effective_threshold("short_run_threshold_min", 42) == 42
