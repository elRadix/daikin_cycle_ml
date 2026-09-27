"""Batch 52b7: cop_sample mode fallback (I/U attrs)."""
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)


def _mk(mode="unknown", attrs=None):
    """Bare coordinator with class-attr defaults (R52)."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    snap = DataSnapshot()
    snap.mode = mode
    snap.attrs = dict(attrs or {})
    c.data = snap
    return c


def test_resolve_from_snap_mode():
    c = _mk(mode="heating", attrs={})
    assert c._resolve_cop_sample_mode() == "heating"


def test_resolve_from_iu_attrs_dhw():
    c = _mk(mode="unknown", attrs={"I/U operation mode": "DHW"})
    assert c._resolve_cop_sample_mode() == "dhw"


def test_resolve_from_iu_attrs_heating():
    c = _mk(mode="unknown", attrs={"I/U operation mode": "Heating"})
    assert c._resolve_cop_sample_mode() == "heating"


def test_resolve_unknown_when_nothing():
    c = _mk(mode="unknown", attrs={})
    assert c._resolve_cop_sample_mode() == "unknown"


def test_snap_mode_wins_over_attrs():
    c = _mk(mode="cooling", attrs={"I/U operation mode": "DHW"})
    assert c._resolve_cop_sample_mode() == "cooling"

def test_iu_dhw_via_standard_key():
    """Direct I/U lookup for DHW (52b7b)."""
    c = _mk(mode="unknown", attrs={"I/U operation mode": "DHW"})
    assert c._resolve_cop_sample_mode() == "dhw"


def test_iu_heating_via_standard_key():
    c = _mk(mode="unknown", attrs={"I/U operation mode": "Heating"})
    assert c._resolve_cop_sample_mode() == "heating"
