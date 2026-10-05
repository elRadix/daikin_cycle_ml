"""B13 UI: comfort_min_c / comfort_max_c sliders + i18n parity.

C11a-0: device step now uses section() with 3 sub-sections
  (sensors / detection / comfort). Inputs and i18n asserts updated.
"""
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
    """Top-level schema has 3 sections; comfort fields live in 'comfort'."""
    result = _run_device_step()
    assert result["step_id"] == "device"
    top_keys = [str(k) for k in result["data_schema"].schema.keys()]
    assert any("sensors" in k for k in top_keys)
    assert any("detection" in k for k in top_keys)
    assert any("comfort" in k for k in top_keys)


def test_device_step_defaults():
    """Empty section dicts get filled with defaults from inner schema."""
    result = _run_device_step()
    out = result["data_schema"]({
        "sensors": {},
        "detection": {
            "compressor_rps_threshold": 3,
            "fallback_power_threshold_w": 200,
        },
        "comfort": {},
    })
    assert out["comfort"]["comfort_min_c"] == 20.0
    assert out["comfort"]["comfort_max_c"] == 24.0


def test_device_step_existing_options_override():
    """Existing options become defaults inside the section's inner schema."""
    result = _run_device_step(
        options={"comfort_min_c": 19.0, "comfort_max_c": 23.0}
    )
    out = result["data_schema"]({
        "sensors": {},
        "detection": {
            "compressor_rps_threshold": 3,
            "fallback_power_threshold_w": 200,
        },
        "comfort": {},
    })
    assert out["comfort"]["comfort_min_c"] == 19.0
    assert out["comfort"]["comfort_max_c"] == 23.0


def test_strings_en_nl_parity_device_b13():
    """EN/NL/strings device: sections + inner data/data_description parity."""
    def _load(name):
        return json.loads((CC / name).read_text())

    s = _load("strings.json")
    en = _load("translations/en.json")
    nl = _load("translations/nl.json")

    dev = s["options"]["step"]["device"]
    dev_en = en["options"]["step"]["device"]
    dev_nl = nl["options"]["step"]["device"]

    s_secs = sorted(dev["sections"].keys())
    assert s_secs == sorted(dev_en["sections"].keys())
    assert s_secs == sorted(dev_nl["sections"].keys())
    assert s_secs == ["comfort", "detection", "sensors"]

    for sec in s_secs:
        s_keys = sorted(dev["sections"][sec]["data"].keys())
        assert s_keys == sorted(dev_en["sections"][sec]["data"].keys())
        assert s_keys == sorted(dev_nl["sections"][sec]["data"].keys())

        s_desc = sorted(dev["sections"][sec]["data_description"].keys())
        assert s_desc == sorted(dev_en["sections"][sec]["data_description"].keys())
        assert s_desc == sorted(dev_nl["sections"][sec]["data_description"].keys())

    assert "comfort_min_c" in dev["sections"]["comfort"]["data"]
    assert "comfort_max_c" in dev["sections"]["comfort"]["data_description"]


def test_comfort_keys_present_all_files():
    """comfort_min_c / comfort_max_c in comfort section across 3 files."""
    def _load(name):
        return json.loads((CC / name).read_text())

    for name in ("strings.json", "translations/en.json", "translations/nl.json"):
        dev = _load(name)["options"]["step"]["device"]
        assert "comfort" in dev["sections"], name
        comfort = dev["sections"]["comfort"]
        assert "comfort_min_c" in comfort["data"], name
        assert "comfort_max_c" in comfort["data"], name
        assert "comfort_min_c" in comfort["data_description"], name
        assert "comfort_max_c" in comfort["data_description"], name
