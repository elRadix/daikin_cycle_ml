"""v1.12.5 #128: _resolve_cop_sample_mode prefers detector.state."""
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)


def _mk(mode="unknown", attrs=None, detector=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    snap = DataSnapshot()
    snap.mode = mode
    snap.attrs = dict(attrs or {})
    c.data = snap
    if detector is not None:
        c.detector = detector
    return c


def _det(state):
    d = MagicMock()
    d.state = state
    return d


def test_detector_dhw_wins_when_snap_unknown():
    c = _mk("unknown", {}, _det("dhw"))
    assert c._resolve_cop_sample_mode() == "dhw"


def test_detector_heating_wins_when_snap_dhw():
    c = _mk("dhw", {}, _det("heating"))
    assert c._resolve_cop_sample_mode() == "heating"


def test_detector_idle_falls_through_to_iu_attrs():
    c = _mk("unknown", {"I/U operation mode": "Heating"}, _det("idle"))
    assert c._resolve_cop_sample_mode() == "heating"


def test_no_detector_attr_falls_through():
    c = _mk("heating", {})
    assert c._resolve_cop_sample_mode() == "heating"


def test_detector_state_none_falls_through():
    c = _mk("heating", {}, _det(None))
    assert c._resolve_cop_sample_mode() == "heating"


def test_detector_dhw_beats_snap_heating():
    c = _mk("heating", {}, _det("dhw"))
    assert c._resolve_cop_sample_mode() == "dhw"
