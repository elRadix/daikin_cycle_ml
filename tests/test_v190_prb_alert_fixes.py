"""v1.9.0 PR B — critical alert pipeline fixes.

Covers ALERTS_V2.md sections 4.1, 4.2, 4.2b, 4.3, 4.6, Q2.
Refs #66.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml import const
from custom_components.daikin_cycle_ml import services as svc
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
    NOTIF_ID_BY_TYPE,
    AlertSpec,
    evaluate_alerts,
)

_ROOT = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"


# ============================================================
# 4.1 pendulum_daily alert_type collision
# ============================================================

def test_pendulum_daily_has_distinct_alert_type():
    assert BINARY_ALERT_MAP["pendulum_hourly"][0] == "pendulum_hourly"
    assert BINARY_ALERT_MAP["pendulum_daily"][0] == "pendulum_daily"


def test_pendulum_daily_notif_id_distinct():
    assert (
        NOTIF_ID_BY_TYPE["pendulum_daily"]
        != NOTIF_ID_BY_TYPE["pendulum_hourly"]
    )
    assert "daily" in NOTIF_ID_BY_TYPE["pendulum_daily"]
    assert "hourly" in NOTIF_ID_BY_TYPE["pendulum_hourly"]


def test_pendulum_daily_fires_when_both_true():
    out = evaluate_alerts(
        {"pendulum_hourly": True, "pendulum_daily": True}, {}, now=1e9
    )
    types = sorted(a.alert_type for a in out)
    assert types == ["pendulum_daily", "pendulum_hourly"]


def test_pendulum_daily_fires_alone():
    out = evaluate_alerts({"pendulum_daily": True}, {}, now=1e9)
    assert len(out) == 1
    assert out[0].alert_type == "pendulum_daily"


def test_pendulum_group_gate_applies_to_both():
    out = evaluate_alerts(
        {"pendulum_hourly": True, "pendulum_daily": True},
        {"alert_group_pendulum": False},
        now=1e9,
    )
    assert out == []


def test_pendulum_emoji_map_updated():
    assert "pendulum_hourly" in const.ALERT_TYPE_EMOJI
    assert "pendulum_daily" in const.ALERT_TYPE_EMOJI
    assert (
        const.ALERT_TYPE_EMOJI["pendulum_hourly"] == const.EMOJI_PENDULUM
    )
    assert (
        const.ALERT_TYPE_EMOJI["pendulum_daily"] == const.EMOJI_PENDULUM
    )


def test_pendulum_group_map_updated():
    assert (
        const.ALERT_GROUP_MAP["pendulum_hourly"]
        == const.ALERT_GROUP_PENDULUM
    )
    assert (
        const.ALERT_GROUP_MAP["pendulum_daily"]
        == const.ALERT_GROUP_PENDULUM
    )
    assert "pendulum" not in const.ALERT_GROUP_MAP


def test_no_bare_notif_id_pendulum_constant():
    assert not hasattr(const, "NOTIF_ID_PENDULUM")
    assert hasattr(const, "NOTIF_ID_PENDULUM_HOURLY")
    assert hasattr(const, "NOTIF_ID_PENDULUM_DAILY")


# ============================================================
# 4.2 / 4.2b trigger/display key mismatch (source-level guards)
# ============================================================

def test_short_off_trigger_uses_short_off_key():
    src = (_ROOT / "coordinator.py").read_text(encoding="utf-8")
    assert (
        'short_off_th = self._effective_threshold(\n'
        '            "short_off_threshold_min",'
    ) in src
    assert (
        'short_off_th = self._effective_threshold(\n'
        '            "good_off_threshold_min",'
    ) not in src


def test_pendulum_daily_trigger_uses_pendulum_key():
    src = (_ROOT / "coordinator.py").read_text(encoding="utf-8")
    assert (
        'pend_day = self._effective_threshold(\n'
        '            "pendulum_cycles_per_day",'
    ) in src
    assert (
        'pend_day = self._effective_threshold(\n'
        '            "target_cycles_per_day",'
    ) not in src


# ============================================================
# 4.3 ml_anomaly mode overwrite (source-level guard)
# ============================================================

def test_ml_anomaly_mode_overwrite_removed():
    src = (_ROOT / "coordinator.py").read_text(encoding="utf-8")
    assert 'ctx["ml_anomaly"]["mode"] = str(' not in src


# ============================================================
# 4.6 cop_low payload leak
# ============================================================

@pytest.mark.asyncio
async def test_emit_alert_no_context_leak():
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )

    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {"notify_service": "notify.test"}
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._notify_fail_streak = 0
    c._notify_fail_target = ""

    spec = AlertSpec(
        alert_type="cop_low",
        severity="warning",
        message="COP is low",
        notif_id="daikin_cycle_ml_cop_low",
        dedupe_key="cop_low",
        persistent=False,
        context={"cop": 2.1, "samples": 8},
    )
    await c._emit_alert(spec)

    calls = c.hass.services.async_call.await_args_list
    assert len(calls) == 1
    args = calls[0].args
    assert args[0] == "notify"
    assert args[1] == "test"
    payload = args[2]
    assert payload == {"message": "COP is low"}
    assert "cop" not in payload
    assert "samples" not in payload


# ============================================================
# Q2 send_test_notification extension
# ============================================================

def _mk_hass_with_coord(coord):
    hass = MagicMock()
    entry = MagicMock()
    entry.runtime_data = coord
    hass.config_entries.async_get_entry.return_value = entry
    return hass


@pytest.mark.asyncio
async def test_send_test_notification_alert_kind_routes():
    coord = MagicMock()
    coord.async_emit_test_alert = AsyncMock(return_value="[rendered]")
    hass = _mk_hass_with_coord(coord)

    call = MagicMock()
    call.data = {"entry_id": "e1", "alert_kind": "short_run"}

    out = await svc._handle_send_test_notification(hass, call)

    coord.async_emit_test_alert.assert_awaited_once_with(
        "short_run", ignore_filters=False
    )
    assert out["ok"] is True
    assert out["alert_kind"] == "short_run"
    assert out["message"] == "[rendered]"


@pytest.mark.asyncio
async def test_send_test_notification_ignore_filters_flag():
    coord = MagicMock()
    coord.async_emit_test_alert = AsyncMock(return_value="[rendered]")
    hass = _mk_hass_with_coord(coord)

    call = MagicMock()
    call.data = {
        "entry_id": "e1",
        "alert_kind": "all_alerts",
        "ignore_filters": True,
    }

    out = await svc._handle_send_test_notification(hass, call)

    coord.async_emit_test_alert.assert_awaited_once_with(
        "all_alerts", ignore_filters=True
    )
    assert out["ok"] is True


@pytest.mark.asyncio
async def test_send_test_notification_alert_kind_resolver_error_propagates():
    from homeassistant.exceptions import HomeAssistantError

    hass = MagicMock()
    hass.config_entries.async_get_entry.return_value = None

    call = MagicMock()
    call.data = {"alert_kind": "short_run"}

    with pytest.raises(HomeAssistantError):
        await svc._handle_send_test_notification(hass, call)


@pytest.mark.asyncio
async def test_send_test_notification_backcompat_passthrough(monkeypatch):
    from custom_components.daikin_cycle_ml.engine import (
        notification_engine as ne,
    )

    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(ne, "async_send_notification", sent)

    coord = MagicMock()
    coord.options = {"notify_service": "notify.telegram"}
    hass = _mk_hass_with_coord(coord)

    call = MagicMock()
    call.data = {"entry_id": "e1", "message": "hello"}

    out = await svc._handle_send_test_notification(hass, call)

    sent.assert_awaited_once()
    assert out["ok"] is True
    assert out["message"] == "hello"
    assert out["target"] == "notify.telegram"
    assert "alert_kind" not in out


# ============================================================
# i18n parity for new service fields
# ============================================================

@pytest.mark.parametrize(
    "rel",
    ["strings.json", "translations/en.json", "translations/nl.json"],
)
def test_i18n_has_new_service_fields(rel):
    d = json.loads((_ROOT / rel).read_text(encoding="utf-8"))
    fields = d["services"]["send_test_notification"]["fields"]
    assert "alert_kind" in fields
    assert "ignore_filters" in fields
    assert fields["alert_kind"]["name"]
    assert fields["ignore_filters"]["name"]
    assert len(fields["alert_kind"]["description"]) > 10
    assert len(fields["ignore_filters"]["description"]) > 10


def test_services_yaml_has_new_fields():
    src = (_ROOT / "services.yaml").read_text(encoding="utf-8")
    assert "    alert_kind:\n" in src
    assert "    ignore_filters:\n" in src
    assert "all_alerts" in src
