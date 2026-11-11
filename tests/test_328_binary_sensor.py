"""#328 Phase 6: binary_sensor.dhw_installed reflects coord.dhw_present.

Semantics:
  on  = DHW tank present / expected (valve, tank sensor, history, override=always)
  off = no DHW tank (override=never, or auto-detect tier4)
"""
import pytest
from unittest.mock import MagicMock
from custom_components.daikin_cycle_ml.binary_sensor import BINARY_SENSOR_DEFS


def _entry():
    return next((d for d in BINARY_SENSOR_DEFS if d.get("key") == "dhw_installed"), None)


def test_dhw_installed_registered_in_defs():
    """Entity must exist in BINARY_SENSOR_DEFS so HA creates it."""
    e = _entry()
    assert e is not None, "dhw_installed not found in BINARY_SENSOR_DEFS"
    assert "state_fn" in e, "dhw_installed entry has no state_fn"
    assert "name" in e, "dhw_installed entry has no name"


def test_dhw_installed_state_on_when_dhw_present():
    e = _entry()
    assert e is not None
    coord = MagicMock(); coord.dhw_present = True
    snap = MagicMock()
    assert e["state_fn"](snap, coord) is True


def test_dhw_installed_state_off_when_no_dhw():
    e = _entry()
    assert e is not None
    coord = MagicMock(); coord.dhw_present = False
    snap = MagicMock()
    assert e["state_fn"](snap, coord) is False


def test_dhw_installed_safe_when_coord_lacks_attribute():
    """__new__-bypassed fixtures have no dhw_present — default True (safe)."""
    e = _entry()
    assert e is not None
    coord = object()   # bare object, no dhw_present attr
    snap = MagicMock()
    assert e["state_fn"](snap, coord) is True


def test_dhw_installed_has_no_problem_device_class():
    """Must not use PROBLEM class — 'on' means OK (installed), not problem."""
    e = _entry()
    assert e is not None
    dc = e.get("device_class")
    # Allow None or specific non-PROBLEM classes only
    from homeassistant.components.binary_sensor import BinarySensorDeviceClass
    assert dc != BinarySensorDeviceClass.PROBLEM, (
        "PROBLEM device_class would invert semantics: on=problem vs on=installed"
    )
