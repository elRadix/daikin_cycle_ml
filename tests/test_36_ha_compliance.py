"""Batch 36 -- HA config flow compliance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
JSON_FILES = [
    "strings.json",
    "translations/en.json",
    "translations/nl.json",
]


def test_options_flow_with_reload():
    src = (ROOT / "config_flow.py").read_text()
    assert "OptionsFlowWithReload" in src
    assert "class DaikinCycleMLOptionsFlow(_OPTIONS_FLOW_BASE):" in src


def test_modern_create_entry():
    src = (ROOT / "config_flow.py").read_text()
    assert "async_create_entry(data=merged)" in src
    bad = "async_create_entry(title=" + chr(34) + chr(34) + ", data=merged)"
    assert bad not in src


def test_coordinator_has_test_alert():
    src = (ROOT / "coordinator.py").read_text()
    assert "async def async_emit_test_alert(" in src


def test_result_step_present():
    src = (ROOT / "config_flow.py").read_text()
    assert "async def async_step_test_notification_result(" in src


def test_version_bumped():
    const = (ROOT / "const.py").read_text()
    assert "0.8.0" in const
    mf = json.loads((ROOT / "manifest.json").read_text())
    assert mf["version"] == "0.8.0"


@pytest.mark.parametrize("rel", JSON_FILES)
def test_selector_alert_kind_options(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    opts = d["selector"]["alert_kind"]["options"]
    for k in ("status_summary", "pendulum_hourly", "pendulum_daily",
              "short_run", "short_off", "ml_anomaly", "setpoint_osc",
              "cop_low", "stooklijn_advies"):
        assert k in opts, rel + " missing " + k


@pytest.mark.parametrize("rel", JSON_FILES)
def test_test_notification_step_fields(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    s = d["options"]["step"]["test_notification"]
    assert "alert_kind" in (s.get("data") or {})
    assert "alert_kind" in (s.get("data_description") or {})
    assert "ignore_group_filters" in (s.get("data") or {})
    assert "ignore_group_filters" in (s.get("data_description") or {})


@pytest.mark.parametrize("rel", JSON_FILES)
def test_result_step_exists(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    s = d["options"]["step"]["test_notification_result"]
    assert s.get("title")
    assert "preview" in (s.get("description") or "")


@pytest.mark.parametrize("rel", JSON_FILES)
def test_menu_option_descriptions(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    mod = d["options"]["step"]["init"].get("menu_option_descriptions") or {}
    for k in ("device", "pendulum", "quality", "notifications",
              "ml", "maintenance", "test_notification"):
        assert k in mod, rel + " missing menu description " + k


@pytest.mark.parametrize("rel", JSON_FILES)
def test_all_data_fields_have_description(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    for scope in ("config", "options"):
        for sname, sdata in (d.get(scope, {}).get("step", {}) or {}).items():
            if not isinstance(sdata, dict):
                continue
            dk = set((sdata.get("data") or {}).keys())
            ddk = set((sdata.get("data_description") or {}).keys())
            miss = dk - ddk
            assert not miss, f"{rel} {scope}.{sname}: missing dd {sorted(miss)}"
