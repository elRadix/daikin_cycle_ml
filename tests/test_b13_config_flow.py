"""B13 UI: comfort_min_c / comfort_max_c sliders + i18n parity."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLOptionsFlow,
)


CC = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"


def _run_device_step(options=None):
    flow = DaikinCycleMLOptionsFlow()
    fake_entry = SimpleNamespace(
        options=dict(options or {}),
        data={},
        entry_id="test_entry",
    )
    flow.hass = MagicMock()
    flow.handler = ["test_entry"]
    with patch.object(
        type(flow), "config_entry",
        new_callable=PropertyMock, return_value=fake_entry,
    ):
        return asyncio.run(flow.async_step_device())


def test_device_step_schema_has_comfort_keys():
    result = _run_device_step()
    assert result["step_id"] == "device"
    keys = [str(k) for k in result["data_schema"].schema.keys()]
    assert any("comfort_min_c" in k for k in keys)
    assert any("comfort_max_c" in k for k in keys)


def test_device_step_defaults():
    result = _run_device_step()
    out = result["data_schema"]({
        "compressor_rps_threshold": 3,
        "fallback_power_threshold_w": 200,
    })
    assert out["comfort_min_c"] == 20.0
    assert out["comfort_max_c"] == 24.0


def test_device_step_existing_options_override():
    result = _run_device_step(
        options={"comfort_min_c": 19.0, "comfort_max_c": 23.0}
    )
    out = result["data_schema"]({
        "compressor_rps_threshold": 3,
        "fallback_power_threshold_w": 200,
    })
    assert out["comfort_min_c"] == 19.0
    assert out["comfort_max_c"] == 23.0


def test_strings_en_nl_parity_device_b13():
    def _load(name):
        return json.loads((CC / name).read_text())

    s = _load("strings.json")
    en = _load("translations/en.json")
    nl = _load("translations/nl.json")

    dev = s["options"]["step"]["device"]
    dev_en = en["options"]["step"]["device"]
    dev_nl = nl["options"]["step"]["device"]

    s_keys = sorted(dev["data"].keys())
    assert s_keys == sorted(dev_en["data"].keys())
    assert s_keys == sorted(dev_nl["data"].keys())

    s_desc = sorted(dev["data_description"].keys())
    assert s_desc == sorted(dev_en["data_description"].keys())
    assert s_desc == sorted(dev_nl["data_description"].keys())

    assert "comfort_min_c" in s_keys
    assert "comfort_max_c" in s_desc


def test_comfort_keys_present_all_files():
    def _load(name):
        return json.loads((CC / name).read_text())

    for name in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = _load(name)["options"]["step"]["device"]
        assert "comfort_min_c" in d["data"], name
        assert "comfort_max_c" in d["data"], name
        assert "comfort_min_c" in d["data_description"], name
        assert "comfort_max_c" in d["data_description"], name
