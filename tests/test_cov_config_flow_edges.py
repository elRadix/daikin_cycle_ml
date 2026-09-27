"""COV-1: config_flow.py edge-case coverage.

Targets missing lines/branches from branch coverage recon on 3d534b5:
  165, 287, 389, 399, 659, 719, 722-727, 729, 748-750, 157->166

Mock strategy for _get_coordinator_handle paths:
- config_entry is patched per-test with PropertyMock on the class inside
  a with-block (auto-reverted), because flow.config_entry resolves to
  None in full-suite context (cross-test _entries cleanup).
- For the exception path we use the direct-object fallback
  (hass.data[DOMAIN] = coord) which does not depend on config_entry.

Test-only. No source changes.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import config_flow as cf
from custom_components.daikin_cycle_ml.const import DOMAIN


# ---------- _flatten_notify_choice ----------

def test_flatten_active_choice_entity():
    assert cf._flatten_notify_choice(
        {"active_choice": "entity", "entity": "notify.x"}
    ) == "notify.x"


def test_flatten_active_choice_service():
    assert cf._flatten_notify_choice(
        {"active_choice": "service", "service": "notify.y"}
    ) == "notify.y"


def test_flatten_dict_fallback_entity():
    # line 165: no active_choice, entity is str
    assert cf._flatten_notify_choice({"entity": "notify.z"}) == "notify.z"


def test_flatten_dict_fallback_service():
    # line 165 via k="service"
    assert cf._flatten_notify_choice({"service": "notify.s"}) == "notify.s"


def test_flatten_dict_no_string_branch():
    # 157->166: dict but no valid string value
    assert cf._flatten_notify_choice({"entity": 123, "service": None}) == ""


def test_flatten_none_and_str():
    assert cf._flatten_notify_choice(None) == ""
    assert cf._flatten_notify_choice("notify.direct") == "notify.direct"


# ---------- fake coordinator ----------

class _FakeCoord:
    def __init__(self):
        self.async_emit_test_alert = AsyncMock(return_value="ok-msg")

    async def async_emit_status_update(self):
        return None


@pytest.fixture(autouse=True)
def _disable_options_reload(hass):
    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True),
    ), patch.object(
        hass.config_entries, "async_schedule_reload", new=lambda *a, **k: None,
    ):
        yield


async def _make_flow(hass, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"source_sensor": "sensor.x", "model": "epra12eav3"},
        options=options or {},
    )
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    flow = hass.config_entries.options._progress[r["flow_id"]]
    return flow, entry


def _patch_config_entry(flow, fake_entry):
    """Context manager to make flow.config_entry yield fake_entry."""
    return patch.object(
        type(flow), "config_entry",
        new_callable=PropertyMock,
        return_value=fake_entry,
    )


# ---------- _get_coordinator_handle fallback paths ----------

async def test_get_coord_handle_runtime_data(hass):
    # line 719
    flow, _entry = await _make_flow(hass)
    coord = _FakeCoord()
    fake = SimpleNamespace(runtime_data=coord)
    with _patch_config_entry(flow, fake):
        assert flow._get_coordinator_handle() is coord


async def test_get_coord_handle_dict_by_entry_id(hass):
    # lines 720-724
    flow, entry = await _make_flow(hass)
    coord = _FakeCoord()
    hass.data[DOMAIN] = {entry.entry_id: coord}
    fake = SimpleNamespace(runtime_data=None, entry_id=entry.entry_id)
    with _patch_config_entry(flow, fake):
        assert flow._get_coordinator_handle() is coord


async def test_get_coord_handle_dict_scan(hass):
    # lines 725-727
    flow, _entry = await _make_flow(hass)
    coord = _FakeCoord()
    hass.data[DOMAIN] = {"other-id": coord}
    fake = SimpleNamespace(runtime_data=None, entry_id="some-id")
    with _patch_config_entry(flow, fake):
        assert flow._get_coordinator_handle() is coord


async def test_get_coord_handle_dict_no_match(hass):
    # line 730 fallthrough
    flow, _entry = await _make_flow(hass)
    hass.data[DOMAIN] = {"other-id": "not-a-coord"}
    fake = SimpleNamespace(runtime_data=None, entry_id="some-id")
    with _patch_config_entry(flow, fake):
        assert flow._get_coordinator_handle() is None


async def test_get_coord_handle_direct_object(hass):
    # lines 728-729
    flow, _entry = await _make_flow(hass)
    coord = _FakeCoord()
    hass.data[DOMAIN] = coord
    fake = SimpleNamespace(runtime_data=None, entry_id="some-id")
    with _patch_config_entry(flow, fake):
        assert flow._get_coordinator_handle() is coord


# ---------- async_step_test_notification exception ----------

async def test_test_notification_exception(hass):
    # lines 748-750 (via direct-object fallback path, no config_entry dep)
    flow, _entry = await _make_flow(hass)
    coord = _FakeCoord()
    coord.async_emit_test_alert = AsyncMock(side_effect=RuntimeError("boom"))
    hass.data[DOMAIN] = coord
    fake = SimpleNamespace(runtime_data=None, entry_id="some-id")
    with _patch_config_entry(flow, fake):
        result = await flow.async_step_test_notification(
            user_input={"alert_kind": "status_summary"},
        )
    assert result["type"] == "form"
    assert flow._test_result["status"] == "failed"
    assert "boom" in flow._test_result["preview"]


# ---------- ConfigFlow direct ----------

async def test_config_flow_cycle_prefills_power_sensor(hass):
    # line 287
    flow = cf.DaikinCycleMLConfigFlow()
    flow.hass = hass
    flow._options = {"power_sensor_entity": "sensor.pump_power"}
    result = await flow.async_step_cycle()
    assert result["type"] == "form"


async def test_config_flow_notifications_form_with_current_ns(hass):
    # line 399
    flow = cf.DaikinCycleMLConfigFlow()
    flow.hass = hass
    flow._options = {"notify_service": "notify.existing"}
    result = await flow.async_step_notifications()
    assert result["type"] == "form"


async def test_config_flow_notifications_submit_flattens(hass):
    # line 389
    flow = cf.DaikinCycleMLConfigFlow()
    flow.hass = hass
    flow._options = {}
    try:
        await flow.async_step_notifications(
            user_input={
                "notify_service": {
                    "active_choice": "entity",
                    "entity": "notify.x",
                }
            },
        )
    except Exception:
        pass
    assert flow._options.get("notify_service") == "notify.x"


# ---------- OptionsFlow notifications form prefill ----------

async def test_options_notifications_form_with_current_ns(hass):
    # line 659
    flow, _entry = await _make_flow(
        hass, options={"notify_service": "notify.old"},
    )
    result = await flow.async_step_notifications()
    assert result["type"] == "form"
