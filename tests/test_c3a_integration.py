"""Integration tests for C3a datasheet sensor pipeline."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import sensor
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)


def _snap(**over):
    base = dict(
        datasheet=None,
        datasheet_model=None,
        cop=None,
        cop_normalized_a7w35=None,
        cop_vs_datasheet_pct=None,
    )
    base.update(over)
    return DataSnapshot(**base)


def test_value_hp_specs_returns_model():
    s = _snap(datasheet_model="erla11dav3")
    assert sensor._value_hp_specs(s, None) == "erla11dav3"


def test_value_hp_specs_none():
    assert sensor._value_hp_specs(_snap(), None) is None


def test_value_cop_normalized_none():
    assert sensor._value_cop_normalized_a7w35(_snap(), None) is None


def test_value_cop_normalized_value():
    s = _snap(cop_normalized_a7w35=4.321)
    assert sensor._value_cop_normalized_a7w35(s, None) == 4.321


def test_value_cop_vs_datasheet_none():
    assert sensor._value_cop_vs_datasheet_pct(_snap(), None) is None


def test_value_cop_vs_datasheet_value():
    s = _snap(cop_vs_datasheet_pct=-12.5)
    assert sensor._value_cop_vs_datasheet_pct(s, None) == -12.5


def test_attrs_hp_specs_no_datasheet():
    a = sensor._attrs_hp_specs(_snap(datasheet_model="erla12dav3"), None)
    assert a["configured"] is False
    assert a["model"] == "erla12dav3"


def test_attrs_hp_specs_full():
    ds = {
        "model": "erla11dav3", "source": "bundled",
        "family": "Split", "kw": 11,
        "lwt_min": 15, "lwt_max": 60,
        "outdoor_min_c": -25, "outdoor_max_c": 35,
        "nom_cop": 4.83, "scop_w35": 4.63, "scop_w55": 3.23,
        "refrigerant": "R32", "gwp": 675, "charge_kg": 3.8,
        "buh_above_c": 55, "defrost_below_c": 5, "off_above_c": 20,
        "points": [{"label": "A7/W35", "t_out": 7, "t_lwc": 35,
                    "cop": 4.83, "hc": 10.56}],
    }
    a = sensor._attrs_hp_specs(
        _snap(datasheet_model="erla11dav3", datasheet=ds), None
    )
    assert a["configured"] is True
    assert a["kw"] == 11
    assert a["buh_above_c"] == 55
    assert a["points"][0]["cop"] == 4.83
    assert a["source"] == "bundled"


def test_attrs_cop_normalized_empty():
    a = sensor._attrs_cop_normalized_a7w35(_snap(), None)
    assert a["model"] is None and a["ref_cop_a7w35"] is None


def test_attrs_cop_normalized_full():
    ds = {"family": "Split", "kw": 11, "nom_cop": 4.83,
          "points": [{"label": "A7/W35", "cop": 4.83}]}
    s = _snap(datasheet=ds, datasheet_model="erla11dav3",
              cop=4.1, cop_normalized_a7w35=4.5)
    a = sensor._attrs_cop_normalized_a7w35(s, None)
    assert a["model"] == "erla11dav3"
    assert a["ref_cop_a7w35"] == 4.83
    assert a["cop_normalized_a7w35"] == 4.5
    assert a["cop_measured"] == 4.1


def test_band_none():
    a = sensor._attrs_cop_vs_datasheet_pct(_snap(), None)
    assert a["band"] is None


def test_band_on_spec():
    a = sensor._attrs_cop_vs_datasheet_pct(
        _snap(cop_vs_datasheet_pct=0.0), None
    )
    assert a["band"] == "on_spec"


def test_band_below_spec():
    a = sensor._attrs_cop_vs_datasheet_pct(
        _snap(cop_vs_datasheet_pct=-5.0), None
    )
    assert a["band"] == "below_spec"


def test_band_below_spec_boundary():
    a = sensor._attrs_cop_vs_datasheet_pct(
        _snap(cop_vs_datasheet_pct=-20.0), None
    )
    assert a["band"] == "below_spec"


def test_band_critical():
    a = sensor._attrs_cop_vs_datasheet_pct(
        _snap(cop_vs_datasheet_pct=-20.01), None
    )
    assert a["band"] == "critical"


def test_sensor_defs_has_c3a_keys():
    keys = {d["key"] for d in sensor.SENSOR_DEFS}
    for k in ("hp_specs", "cop_normalized_a7w35", "cop_vs_datasheet_pct"):
        assert k in keys, k


def test_sensor_defs_hp_specs_diagnostic():
    d = next(d for d in sensor.SENSOR_DEFS if d["key"] == "hp_specs")
    assert d.get("entity_category") == "diagnostic"


def test_sensor_defs_no_duplicate_keys():
    keys = [d["key"] for d in sensor.SENSOR_DEFS]
    assert len(keys) == len(set(keys))


def test_sensor_defs_count():
    assert len(sensor.SENSOR_DEFS) == 46


@pytest.mark.asyncio
async def test_refresh_no_datasheet_model():
    coord = MagicMock()
    coord._datasheet_merged = {}
    coord._datasheet_defaults = {}
    coord.entry.data = {"model": "basisprofiel"}
    coord._datasheet_cache = {}
    await DaikinCycleMLCoordinator._refresh_datasheet_state(
        coord, 1000.0, 40.0, 5.0, 3.5
    )
    assert coord._datasheet_cache["model"] == "basisprofiel"
    assert coord._datasheet_cache["datasheet"] is None
    assert coord._datasheet_cache["cop_normalized_a7w35"] is None


@pytest.mark.asyncio
async def test_refresh_with_real_datasheet():
    from custom_components.daikin_cycle_ml.engine.model_datasheets import (
        load_bundled,
    )
    coord = MagicMock()
    coord._datasheet_merged = load_bundled()
    coord._datasheet_user_loaded = True
    coord._datasheet_defaults = {}
    coord.entry.data = {"model": "erla11dav3"}
    coord._datasheet_cache = {}
    await DaikinCycleMLCoordinator._refresh_datasheet_state(
        coord, 1000.0, 40.0, 5.0, 3.5
    )
    cache = coord._datasheet_cache
    assert cache["model"] == "erla11dav3"
    assert cache["datasheet"] is not None
    assert cache["datasheet"]["model"] == "erla11dav3"
    assert cache["datasheet"]["buh_above_c"] == 55
    assert cache["datasheet"]["outdoor_min_c"] == -25
    assert cache["cop_normalized_a7w35"] is not None
    assert cache["cop_vs_datasheet_pct"] is not None


# ---------- entity_category branches ----------
def test_entity_category_diagnostic_branch():
    from unittest.mock import MagicMock

    from custom_components.daikin_cycle_ml.sensor import DaikinCycleMLSensor
    from homeassistant.const import EntityCategory
    coord = MagicMock()
    coord.entry.entry_id = "x"
    coord.entry.data = {"model": "basisprofiel"}
    s = DaikinCycleMLSensor(
        coord, key="k", name="K",
        value_fn=lambda s, c: None,
        entity_category="diagnostic",
    )
    assert s._attr_entity_category == EntityCategory.DIAGNOSTIC


def test_entity_category_config_branch():
    from unittest.mock import MagicMock

    from custom_components.daikin_cycle_ml.sensor import DaikinCycleMLSensor
    from homeassistant.const import EntityCategory
    coord = MagicMock()
    coord.entry.entry_id = "x"
    coord.entry.data = {"model": "basisprofiel"}
    s = DaikinCycleMLSensor(
        coord, key="k", name="K",
        value_fn=lambda s, c: None,
        entity_category="config",
    )
    assert s._attr_entity_category == EntityCategory.CONFIG


def test_entity_category_none_branch():
    from unittest.mock import MagicMock

    from custom_components.daikin_cycle_ml.sensor import DaikinCycleMLSensor
    coord = MagicMock()
    coord.entry.entry_id = "x"
    coord.entry.data = {"model": "basisprofiel"}
    s = DaikinCycleMLSensor(
        coord, key="k", name="K",
        value_fn=lambda s, c: None,
        entity_category=None,
    )
    assert getattr(s, "_attr_entity_category", None) is None


# ---------- coverage: early-return branches + _safe_float_opt ----------
def test_safe_float_opt_type_error():
    from custom_components.daikin_cycle_ml.coordinator import _safe_float_opt
    class Weird:
        def __float__(self): raise TypeError("nope")
    assert _safe_float_opt(Weird()) is None


def test_safe_float_opt_value_error():
    from custom_components.daikin_cycle_ml.coordinator import _safe_float_opt
    assert _safe_float_opt("not-a-number") is None


def test_safe_float_opt_valid():
    from custom_components.daikin_cycle_ml.coordinator import _safe_float_opt
    assert _safe_float_opt("3.5") == 3.5


def test_safe_float_opt_none():
    from custom_components.daikin_cycle_ml.coordinator import _safe_float_opt
    assert _safe_float_opt(None) is None


@pytest.mark.asyncio
async def test_refresh_entry_data_broken_triggers_except():
    """self.entry.data is not a dict -> Exception branch."""
    coord = MagicMock()
    coord._datasheet_merged = {}
    coord._datasheet_defaults = {}
    coord.entry.data = "not-a-dict"
    coord._datasheet_cache = {}
    await DaikinCycleMLCoordinator._refresh_datasheet_state(
        coord, 1000.0, 40.0, 5.0, 3.5
    )
    assert coord._datasheet_cache["model"] == "basisprofiel"


@pytest.mark.asyncio
async def test_refresh_no_a7w35_point():
    """datasheet present maar zonder A7/W35 punt -> ref is None -> early return."""
    coord = MagicMock()
    coord._datasheet_merged = {
        "test_model": {
            "family": "Split", "kw": 11, "lwt_min": 15, "lwt_max": 60,
            "nom_cop": 4.5,
            "points": [{"label": "A10/W35", "t_out": 10, "t_lwc": 35, "cop": 5.0}],
            "source": "bundled",
        }
    }
    coord._datasheet_defaults = {"buh_above_offset_c": -5}
    coord.entry.data = {"model": "test_model"}
    coord._datasheet_cache = {}
    await DaikinCycleMLCoordinator._refresh_datasheet_state(
        coord, 1000.0, 40.0, 5.0, 3.5
    )
    assert coord._datasheet_cache["cop_normalized_a7w35"] is None


@pytest.mark.asyncio
async def test_refresh_zero_ref_cop():
    """A7/W35 punt met cop=0 -> early return."""
    coord = MagicMock()
    coord._datasheet_merged = {
        "test_model": {
            "family": "Split", "kw": 11, "lwt_min": 15, "lwt_max": 60,
            "nom_cop": 4.5,
            "points": [{"label": "A7/W35", "t_out": 7, "t_lwc": 35, "cop": 0.0}],
            "source": "bundled",
        }
    }
    coord._datasheet_defaults = {"buh_above_offset_c": -5}
    coord.entry.data = {"model": "test_model"}
    coord._datasheet_cache = {}
    await DaikinCycleMLCoordinator._refresh_datasheet_state(
        coord, 1000.0, 40.0, 5.0, 3.5
    )
    assert coord._datasheet_cache["cop_normalized_a7w35"] is None


@pytest.mark.asyncio
async def test_refresh_dT_live_nonpositive():
    """lwt_now <= t_out-13 -> dT_live <= 0 -> early return."""
    coord = MagicMock()
    coord._datasheet_merged = {}
    coord._datasheet_defaults = {}
    coord.entry.data = {"model": "erla11dav3"}
    coord._datasheet_cache = {}
    # t_out = 100, lwt_now = 15 -> t_evap = 365.15, t_cond = 293.15 -> dT < 0
    await DaikinCycleMLCoordinator._refresh_datasheet_state(
        coord, 1000.0, 15.0, 100.0, 3.5
    )
    assert coord._datasheet_cache["cop_normalized_a7w35"] is None


@pytest.mark.asyncio
async def test_refresh_none_lwt():
    coord = MagicMock()
    coord._datasheet_merged = {}
    coord._datasheet_defaults = {}
    coord.entry.data = {"model": "erla11dav3"}
    coord._datasheet_cache = {}
    await DaikinCycleMLCoordinator._refresh_datasheet_state(
        coord, 1000.0, None, 5.0, 3.5
    )
    assert coord._datasheet_cache["cop_normalized_a7w35"] is None


@pytest.mark.asyncio
async def test_refresh_none_tout():
    coord = MagicMock()
    coord._datasheet_merged = {}
    coord._datasheet_defaults = {}
    coord.entry.data = {"model": "erla11dav3"}
    coord._datasheet_cache = {}
    await DaikinCycleMLCoordinator._refresh_datasheet_state(
        coord, 1000.0, 40.0, None, 3.5
    )
    assert coord._datasheet_cache["cop_normalized_a7w35"] is None


@pytest.mark.asyncio
async def test_refresh_none_cop():
    coord = MagicMock()
    coord._datasheet_merged = {}
    coord._datasheet_defaults = {}
    coord.entry.data = {"model": "erla11dav3"}
    coord._datasheet_cache = {}
    await DaikinCycleMLCoordinator._refresh_datasheet_state(
        coord, 1000.0, 40.0, 5.0, None
    )
    assert coord._datasheet_cache["cop_normalized_a7w35"] is None
