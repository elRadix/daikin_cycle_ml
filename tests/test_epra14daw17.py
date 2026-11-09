"""Exact-model support for the R32 EPRA14DAW17 / ETBH16EF9W7 pairing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.const import (
    DOMAIN,
    MODEL_BASISPROFIEL,
    MODEL_CHOICES,
    MODEL_EPRA14DAW17,
    MODEL_EPRA14EAV3,
    MODEL_LABELS,
    REQUIRED_ATTRIBUTES,
    SOURCE_SENSOR_ENTITY,
    family_for_model,
    models_in_family,
    resolve_model_key,
)
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.engine.model_datasheets import (
    get_datasheet,
    load_bundled,
    merge,
)
from custom_components.daikin_cycle_ml.engine.model_profiles import get_profile


def test_exact_model_is_selectable_without_aliasing_an_e_series_model():
    assert MODEL_EPRA14DAW17 in MODEL_CHOICES
    assert "Altherma 3 H HT" in MODEL_LABELS[MODEL_EPRA14DAW17]
    assert family_for_model(MODEL_EPRA14DAW17) == "epra"
    assert MODEL_EPRA14DAW17 in models_in_family("epra")
    assert resolve_model_key(MODEL_EPRA14DAW17) == MODEL_EPRA14DAW17
    assert resolve_model_key(MODEL_EPRA14DAW17) != MODEL_EPRA14EAV3


def test_r32_hydrosplit_keeps_epra_cycle_defaults():
    # The legacy EKHBRD/ERRQ profile's 5-hour cap and 10 K target are
    # not justified for this R32 hydrosplit or its configured emitters.
    profile = get_profile(MODEL_EPRA14DAW17)
    assert profile == get_profile(MODEL_BASISPROFIEL)
    assert profile["max_cycle_duration_min"] == 2880
    assert profile["good_dt_threshold_k"] == 5.0


def test_datasheet_uses_published_nominal_point_and_seasonal_metadata():
    spec = get_datasheet(merge(load_bundled(), {}), MODEL_EPRA14DAW17)
    assert spec is not None
    assert spec["family"] == "Hydrosplit HT"
    assert spec["source"] == "bundled"
    assert spec["kw"] == 5.9
    assert spec["lwt_min"] == 15
    assert spec["lwt_max"] == 70
    assert spec["nom_cop"] == 4.79
    assert spec["scop_w35"] == 4.71
    assert spec["scop_w55"] == 3.57
    assert spec["refrigerant"] == "R32"
    assert "charge_kg" not in spec
    assert spec["points"] == [
        {"label": "A7/W35", "t_out": 7, "t_lwc": 35, "cop": 4.79, "hc": 5.9}
    ]


async def test_published_point_flows_into_normalized_cop(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"model": MODEL_EPRA14DAW17, "source_sensor": SOURCE_SENSOR_ENTITY},
    )
    coordinator = DaikinCycleMLCoordinator(hass, entry)
    await coordinator._refresh_datasheet_state(
        now=1.0, lwt_now=35.0, t_out=7.0, cop_meas=4.79
    )
    cache = coordinator._datasheet_cache
    assert cache["datasheet"]["model"] == MODEL_EPRA14DAW17
    assert cache["cop_normalized_a7w35"] == pytest.approx(4.79)
    assert cache["cop_vs_datasheet_pct"] == pytest.approx(0.0)


async def test_reconfigure_to_exact_model_preserves_source_mapping_and_options(hass):
    attrs = dict.fromkeys(REQUIRED_ATTRIBUTES, 0)
    attrs["R1T-Outdoor air temp."] = attrs.pop("Outdoor air temp.(R1T)")
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "Online", attrs)
    attribute_map = {"Outdoor air temp.(R1T)": "R1T-Outdoor air temp."}
    options = {"power_sensor_entity": "sensor.heat_pump_power", "good_dt_threshold_k": 5}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_BASISPROFIEL,
            "attribute_map": attribute_map,
        },
        options=options,
    )
    entry.add_to_hass(hass)
    with patch("custom_components.daikin_cycle_ml._async_setup_database", new=AsyncMock()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "reconfigure_basic"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA14DAW17},
        )
        await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["model"] == MODEL_EPRA14DAW17
    assert entry.data["source_sensor"] == SOURCE_SENSOR_ENTITY
    assert entry.data["attribute_map"] == attribute_map
    assert entry.options == options
