"""Batch 52a -- dhw_active guard + dt_k idle.

Bug A: _is_dhw_active mag niet puur op 3-way valve triggeren
       (klep rust in DHW-positie op Daikin units).
Bug C: dt_k moet None zijn als state idle is.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.daikin_cycle_ml.binary_sensor import _is_dhw_active
from custom_components.daikin_cycle_ml.const import (
    ATTR_IU_OPERATION_MODE,
    MODE_DHW,
)
from custom_components.daikin_cycle_ml.sensor import _attrs_current_cycle


def _snap(state="running", iu="DHW", threeway="ON"):
    s = MagicMock()
    s.state = state
    s.attrs = {
        ATTR_IU_OPERATION_MODE: iu,
        "3way valve": threeway,
    }
    s.cycle_start_ts = 0.0
    return s


def test_dhw_inactive_when_mode_not_dhw():
    s = _snap(state="running", iu="Heating")
    assert _is_dhw_active(s, MagicMock()) is False


def test_dhw_inactive_when_only_valve_on():
    """Klep-only (rust-positie) mag GEEN dhw_active triggeren."""
    s = _snap(state="idle", iu="OFF", threeway="ON")
    with patch(
        "custom_components.daikin_cycle_ml.binary_sensor._is_buh_active",
        return_value=False,
    ):
        assert _is_dhw_active(s, MagicMock()) is False


def test_dhw_active_when_compressor_running():
    s = _snap(state="running", iu="DHW")
    with patch(
        "custom_components.daikin_cycle_ml.binary_sensor._is_buh_active",
        return_value=False,
    ):
        assert _is_dhw_active(s, MagicMock()) is True


def test_dhw_active_with_buh_support():
    """Compressor off maar BUH aan tijdens DHW -> nog steeds actief."""
    s = _snap(state="idle", iu="DHW")
    with patch(
        "custom_components.daikin_cycle_ml.binary_sensor._is_buh_active",
        return_value=True,
    ):
        assert _is_dhw_active(s, MagicMock()) is True


def test_dhw_inactive_idle_no_buh():
    s = _snap(state="idle", iu="DHW")
    with patch(
        "custom_components.daikin_cycle_ml.binary_sensor._is_buh_active",
        return_value=False,
    ):
        assert _is_dhw_active(s, MagicMock()) is False


def test_dtk_none_when_idle():
    s = _snap(state="idle")
    with patch(
        "custom_components.daikin_cycle_ml.sensor._dt_from_attrs",
        return_value=11.2,
    ), patch(
        "custom_components.daikin_cycle_ml.sensor._rps_from_attrs",
        return_value=0.0,
    ):
        attrs = _attrs_current_cycle(s, MagicMock())
    assert attrs["dt_k"] is None
    assert attrs["duration_min"] is None


def test_dtk_present_when_running():
    s = _snap(state="running")
    with patch(
        "custom_components.daikin_cycle_ml.sensor._dt_from_attrs",
        return_value=7.5,
    ), patch(
        "custom_components.daikin_cycle_ml.sensor._rps_from_attrs",
        return_value=45.0,
    ):
        attrs = _attrs_current_cycle(s, MagicMock())
    assert attrs["dt_k"] == 7.5
