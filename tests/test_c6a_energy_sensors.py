"""v1.6.0-C6a-1a: energy sensors (electrical + thermal kWh)."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.util import slugify

from custom_components.daikin_cycle_ml import sensor as s_mod

C6A1A_KEYS = {
    "electrical_energy_heating_today",
    "electrical_energy_dhw_today",
    "electrical_energy_cooling_today",
    "electrical_energy_total_today",
    "thermal_energy_heating_today",
    "thermal_energy_cooling_today",
}


def _c(snap: Any = None) -> Any:
    m = MagicMock()
    m.energy_snapshot = snap if snap is not None else {}
    return m


def _full() -> dict[str, dict[str, float]]:
    return {
        "heating": {"th": 12.5, "el": 3.2},
        "dhw": {"th": 4.0, "el": 1.5},
        "cooling": {"th": 0.0, "el": 0.0},
    }


def _defs() -> dict[str, dict[str, Any]]:
    return {d["key"]: d for d in s_mod.SENSOR_DEFS}


def test_defs_contains_all_keys() -> None:
    assert C6A1A_KEYS.issubset({d["key"] for d in s_mod.SENSOR_DEFS})


def test_defs_keys_unique() -> None:
    ks = [d["key"] for d in s_mod.SENSOR_DEFS]
    assert len(ks) == len(set(ks))


def test_energy_metadata() -> None:
    for k in C6A1A_KEYS:
        d = _defs()[k]
        assert d["device_class"] == SensorDeviceClass.ENERGY
        assert d["state_class"] == SensorStateClass.TOTAL_INCREASING
        assert d["unit"] == "kWh"


def test_value_and_attr_fn_callable() -> None:
    for k in C6A1A_KEYS:
        d = _defs()[k]
        assert callable(d["value_fn"])
        assert callable(d["attr_fn"])


def test_r246_slugify_matches_key() -> None:
    for k in C6A1A_KEYS:
        assert slugify(_defs()[k]["name"]) == k


def test_value_heating_el() -> None:
    assert s_mod._value_energy_kwh("heating", "el")(None, _c(_full())) == 3.2


def test_value_heating_th() -> None:
    assert s_mod._value_energy_kwh("heating", "th")(None, _c(_full())) == 12.5


def test_value_dhw_el() -> None:
    assert s_mod._value_energy_kwh("dhw", "el")(None, _c(_full())) == 1.5


def test_value_cooling_el() -> None:
    assert s_mod._value_energy_kwh("cooling", "el")(None, _c(_full())) == 0.0


def test_value_cooling_th() -> None:
    assert s_mod._value_energy_kwh("cooling", "th")(None, _c(_full())) == 0.0


def test_value_empty_snapshot() -> None:
    assert s_mod._value_energy_kwh("heating", "el")(None, _c({})) == 0.0


def test_value_none_snapshot() -> None:
    assert s_mod._value_energy_kwh("heating", "el")(None, _c(None)) == 0.0


def test_value_missing_mode() -> None:
    assert (
        s_mod._value_energy_kwh("dhw", "el")(
            None, _c({"heating": {"th": 1.0, "el": 0.5}})
        )
        == 0.0
    )


def test_value_missing_kind() -> None:
    assert (
        s_mod._value_energy_kwh("heating", "el")(None, _c({"heating": {"th": 5.0}}))
        == 0.0
    )


def test_value_rounds_three_decimals() -> None:
    assert (
        s_mod._value_energy_kwh("heating", "el")(
            None, _c({"heating": {"th": 0, "el": 3.14159}})
        )
        == 3.142
    )


def test_total_el_sums_modes() -> None:
    assert s_mod._value_energy_total_kwh("el")(None, _c(_full())) == 4.7


def test_total_th_sums_modes() -> None:
    assert s_mod._value_energy_total_kwh("th")(None, _c(_full())) == 16.5


def test_total_empty_returns_zero() -> None:
    assert s_mod._value_energy_total_kwh("el")(None, _c({})) == 0.0


def test_attrs_shape() -> None:
    a = s_mod._attrs_energy_snapshot(None, _c(_full()))
    assert set(a.keys()) == {
        "heating_th_kwh",
        "heating_el_kwh",
        "dhw_th_kwh",
        "dhw_el_kwh",
        "cooling_th_kwh",
        "cooling_el_kwh",
        "total_th_kwh",
        "total_el_kwh",
    }


def test_attrs_values() -> None:
    a = s_mod._attrs_energy_snapshot(None, _c(_full()))
    assert a["heating_th_kwh"] == 12.5
    assert a["heating_el_kwh"] == 3.2
    assert a["dhw_th_kwh"] == 4.0
    assert a["dhw_el_kwh"] == 1.5
    assert a["total_th_kwh"] == 16.5
    assert a["total_el_kwh"] == 4.7


def test_attrs_empty() -> None:
    a = s_mod._attrs_energy_snapshot(None, _c({}))
    assert all(v == 0.0 for v in a.values())


def test_value_returns_float() -> None:
    assert isinstance(
        s_mod._value_energy_kwh("heating", "el")(None, _c(_full())),
        float,
    )
