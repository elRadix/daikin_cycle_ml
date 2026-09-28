"""Batch COV-4: edge-case coverage for four modules.

Targets:
  - engine/status_report.py       (88, 91-92, 97, 100-101, 200->203, 225-226, 399)
  - services.py                   (93, 165-170, 214-220)
  - engine/notification_engine.py (193-194, 207, 315-316)
  - sensor.py                     (359->exit, 366, 382, 385-387)

Style: direct function calls, MagicMock/AsyncMock, __new__ bypass.
No HA fixtures. R153-compliant.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.daikin_cycle_ml import services as svc
from custom_components.daikin_cycle_ml.engine import (
    notification_engine as ne,
)
from custom_components.daikin_cycle_ml.engine.status_report import (
    _fmt_float,
    _fmt_int,
    build_rich_alert,
    build_status_report,
    build_stooklijn_report,
)
from custom_components.daikin_cycle_ml.sensor import DaikinCycleMLSensor


# ============ status_report.py ============

def test_fmt_float_none():
    assert _fmt_float(None) == "\u2014"


def test_fmt_float_bad_type():
    assert _fmt_float("not-a-number") == "\u2014"


def test_fmt_int_none():
    assert _fmt_int(None) == "\u2014"


def test_fmt_int_bad_type():
    assert _fmt_int("abc") == "\u2014"


def test_status_report_stats_avg_none():
    snap = {
        "db_total": 100,
        "cycles_today": 5,
        "db_7d": 20,
        "db_30d": 50,
    }
    out = build_status_report(snap)
    assert isinstance(out, str)
    assert "100" in out


def test_stooklijn_report_bad_comfort():
    cache = {
        "state": "ok",
        "comfort_impact": "not-a-float",
        "besparing_cop_pct": "also-bad",
        "betrouwbaarheid": "3",
    }
    out = build_stooklijn_report(cache)
    assert isinstance(out, str)


def test_rich_alert_unknown_language():
    out = build_rich_alert("short_run", "warning", {}, language="fr")
    assert isinstance(out, str)


# ============ services.py ============

def test_resolve_optional_with_entry_id():
    hass = MagicMock()
    with patch.object(
        svc, "_resolve_coordinator", return_value="COORD"
    ) as p:
        assert svc._resolve_optional_coordinator(hass, "e1") == "COORD"
    p.assert_called_once_with(hass, "e1")


def test_do_recompute_baseline_extract_raises():
    coord = MagicMock()
    coord.db = MagicMock()
    sample = [{"id": 1, "mode": "heating", "duration_s": 600}]
    for name in (
        "async_fetch_cycles_since",
        "async_fetch_cycles",
        "async_get_cycles",
        "async_get_cycles_since",
        "async_recent_cycles",
    ):
        setattr(coord.db, name, AsyncMock(return_value=sample))
    coord.db.async_set_model_state = AsyncMock()
    with patch(
        "custom_components.daikin_cycle_ml.ml.features.is_valid_record",
        return_value=True,
    ), patch(
        "custom_components.daikin_cycle_ml.ml.features.extract_feature_vector",
        side_effect=RuntimeError("boom"),
    ):
        result = asyncio.run(svc._do_recompute_baseline(coord, 30))
    assert result["computed"] is True
    assert result["samples"] == 0


def test_handle_run_maintenance_calls_runner():
    hass = MagicMock()
    call = MagicMock()
    call.data = {
        svc.ATTR_ENTRY_ID: "e1",
        svc.ATTR_CYCLE_RETENTION_DAYS: 30,
        svc.ATTR_ALERT_RETENTION_DAYS: 7,
        svc.ATTR_VACUUM: False,
    }
    coord = MagicMock()
    coord.async_run_maintenance = AsyncMock(return_value={"ok": True})
    with patch.object(svc, "_resolve_coordinator", return_value=coord):
        result = asyncio.run(svc._handle_run_maintenance(hass, call))
    assert result == {"ok": True}


# ============ notification_engine.py ============

def test_format_message_invalid_template():
    out = ne._format_message("{unclosed", {"x": 1})
    assert out == "{unclosed"


def test_prefix_emoji_no_emoji_found():
    out = ne._prefix_emoji("msg", "unknown_type", "custom_sev", True)
    assert out == "msg"


def test_evaluate_alerts_non_schema_alert():
    binary = {"dhw_pendulum": True, "high_cycle_rate": True}
    opts = {
        "alert_group_pendulum": True,
        "alert_group_short_cycle": True,
        "alert_group_ml": True,
        "alert_group_setpoint": True,
        "alert_group_cop_stooklijn": True,
        "notify_emoji_enabled": True,
        "notification_language": "en",
    }
    out = ne.evaluate_alerts(binary, opts, 1000.0)
    assert isinstance(out, list)


# ============ sensor.py ============

def _mk_sensor(value_fn=None, attr_fn=None):
    s = DaikinCycleMLSensor.__new__(DaikinCycleMLSensor)
    s._key = "test_key"
    s.coordinator = MagicMock()
    s._value_fn = value_fn or (lambda snap, c: 1.0)
    s._attr_fn = attr_fn
    return s


def test_sensor_native_value_snap_none():
    s = _mk_sensor()
    s.snapshot = lambda: None
    assert s.native_value is None


def test_sensor_native_value_raises():
    def _raise(snap, c):
        raise RuntimeError("boom")

    s = _mk_sensor(value_fn=_raise)
    s.snapshot = lambda: MagicMock()
    assert s.native_value is None


def test_sensor_extra_attrs_attr_fn_none():
    s = _mk_sensor(attr_fn=None)
    s.snapshot = lambda: MagicMock()
    assert s.extra_state_attributes is None


def test_sensor_extra_attrs_snap_none():
    s = _mk_sensor(attr_fn=lambda snap, c: {"x": 1})
    s.snapshot = lambda: None
    assert s.extra_state_attributes is None


def test_sensor_extra_attrs_raises():
    def _raise(snap, c):
        raise RuntimeError("boom")

    s = _mk_sensor(attr_fn=_raise)
    s.snapshot = lambda: MagicMock()
    assert s.extra_state_attributes is None


def test_sensor_init_icon_none_branch():
    from custom_components.daikin_cycle_ml.entity import (
        DaikinCycleMLEntity,
    )
    s = DaikinCycleMLSensor.__new__(DaikinCycleMLSensor)
    coord = MagicMock()
    with patch.object(DaikinCycleMLEntity, "__init__", return_value=None):
        DaikinCycleMLSensor.__init__(
            s, coord, "k", "n", lambda snap, c: 1.0, icon=None
        )
    assert getattr(s, "_attr_icon", None) is None
