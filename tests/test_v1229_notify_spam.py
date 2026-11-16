"""v1.22.9 #367: notify ServiceNotFound log-spam + dedupe."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from custom_components.daikin_cycle_ml import coordinator as co
from custom_components.daikin_cycle_ml.engine.notification_engine import AlertSpec
from homeassistant.exceptions import ServiceNotFound


@pytest.fixture(autouse=True)
def _stub_notify_full_model(monkeypatch):
    """_notify_full_model is a read-only property on the coordinator."""
    monkeypatch.setattr(
        co.DaikinCycleMLCoordinator,
        "_notify_full_model",
        PropertyMock(return_value=""),
    )


def _mk_coord(svc: str = "notify.test_missing") -> co.DaikinCycleMLCoordinator:
    c = co.DaikinCycleMLCoordinator.__new__(co.DaikinCycleMLCoordinator)
    c.options = {"notify_service": svc}
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._notify_fail_logged = set()
    return c


def _mk_alert(msg: str = "test") -> AlertSpec:
    return AlertSpec(
        alert_type="short_run",
        severity="warning",
        message=msg,
        notif_id="daikin_test_short_run",
        dedupe_key="short_run",
        persistent=False,
    )


@pytest.mark.asyncio
async def test_dispatch_notify_success():
    c = _mk_coord()
    ok = await c._dispatch_notify("notify.ok", "msg")
    assert ok is True
    assert c._notify_fail_streak == 0
    assert c._notify_fail_target == ""
    assert c._notify_fail_logged == set()


@pytest.mark.asyncio
async def test_dispatch_notify_service_not_found():
    c = _mk_coord()
    c.hass.services.async_call = AsyncMock(
        side_effect=ServiceNotFound("notify", "missing")
    )
    ok = await c._dispatch_notify("notify.missing", "msg")
    assert ok is False
    assert c._notify_fail_streak == 1
    assert c._notify_fail_target == "notify.missing"
    assert "notify.missing" in c._notify_fail_logged


@pytest.mark.asyncio
async def test_dispatch_notify_dedup_warning(caplog):
    c = _mk_coord()
    c.hass.services.async_call = AsyncMock(
        side_effect=ServiceNotFound("notify", "missing")
    )
    with caplog.at_level(logging.WARNING):
        await c._dispatch_notify("notify.missing", "m1")
        await c._dispatch_notify("notify.missing", "m2")
        await c._dispatch_notify("notify.missing", "m3")
    warnings = [
        r for r in caplog.records
        if r.name == "custom_components.daikin_cycle_ml.coordinator"
        and "not found" in r.getMessage().lower()
    ]
    assert len(warnings) == 1
    assert c._notify_fail_streak == 3


@pytest.mark.asyncio
async def test_dispatch_notify_recovery_resets():
    c = _mk_coord()
    c.hass.services.async_call = AsyncMock(
        side_effect=ServiceNotFound("notify", "missing")
    )
    await c._dispatch_notify("notify.missing", "m1")
    assert "notify.missing" in c._notify_fail_logged
    c.hass.services.async_call = AsyncMock()
    ok = await c._dispatch_notify("notify.missing", "m2")
    assert ok is True
    assert c._notify_fail_logged == set()
    assert c._notify_fail_streak == 0


@pytest.mark.asyncio
async def test_emit_alert_uses_dispatch_notify():
    c = _mk_coord()
    c._dispatch_notify = AsyncMock(return_value=True)
    await c._emit_alert(_mk_alert("hello"))
    c._dispatch_notify.assert_awaited_once()
    assert c._dispatch_notify.await_args.kwargs.get("context") == "alert"


@pytest.mark.asyncio
async def test_emit_alert_skips_no_service():
    c = _mk_coord(svc="")
    c._dispatch_notify = AsyncMock()
    await c._emit_alert(_mk_alert())
    c._dispatch_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_update_uses_dispatch_notify():
    c = _mk_coord(svc="notify.stat")
    c._dispatch_notify = AsyncMock(return_value=True)
    c._build_rich_status_snapshot = AsyncMock(return_value={})
    await c.async_emit_status_update()
    c._dispatch_notify.assert_awaited_once()
    assert c._dispatch_notify.await_args.kwargs.get("context") == "status"


def test_notify_health_property():
    c = _mk_coord()
    c._notify_fail_streak = 2
    c._notify_fail_target = "notify.x"
    c._notify_fail_logged = {"notify.x"}
    h = c.notify_health
    assert h["fail_streak"] == 2
    assert h["fail_target_configured"] is True
    assert h["fail_logged_count"] == 1
    assert h["currently_failing"] is True


@pytest.mark.asyncio
async def test_dispatch_notify_generic_exception():
    """Non-ServiceNotFound failures also warn + dedupe (covers line 5460)."""
    c = _mk_coord()
    c.hass.services.async_call = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    ok = await c._dispatch_notify("notify.x", "msg")
    assert ok is False
    assert c._notify_fail_streak == 1
    assert c._notify_fail_target == "notify.x"
    assert "notify.x" in c._notify_fail_logged


@pytest.mark.asyncio
async def test_emit_alert_persistent_true(monkeypatch):
    """Cover persistent_notification branch in _emit_alert (5485->5492)."""
    c = _mk_coord(svc="")
    c._dispatch_notify = AsyncMock()
    alert = AlertSpec(
        alert_type="short_run",
        severity="warning",
        message="hi",
        notif_id="daikin_test_short_run",
        dedupe_key="short_run",
        persistent=True,
    )
    await c._emit_alert(alert)
    c.hass.services.async_call.assert_awaited_once()
    args = c.hass.services.async_call.await_args.args
    assert args[0] == "persistent_notification"
    assert args[1] == "create"


@pytest.mark.asyncio
async def test_dispatch_notify_invalid_svc_returns_false():
    """Cover 5460: invalid svc short-circuits without calling async_call."""
    c = _mk_coord()
    c.hass.services.async_call = AsyncMock()
    assert await c._dispatch_notify("nodot", "msg") is False
    assert await c._dispatch_notify("", "msg") is False
    c.hass.services.async_call.assert_not_awaited()
    assert c._notify_fail_streak == 0


@pytest.mark.asyncio
async def test_dispatch_notify_generic_repeat_no_double_log(caplog):
    """Cover branch 5485->5492: 2nd generic failure (svc already logged)."""
    c = _mk_coord()
    c.hass.services.async_call = AsyncMock(side_effect=RuntimeError("boom"))
    with caplog.at_level(logging.WARNING):
        await c._dispatch_notify("notify.x", "m1")
        await c._dispatch_notify("notify.x", "m2")
    assert c._notify_fail_streak == 2
    warn = [r for r in caplog.records if "notify.x" in r.getMessage()]
    assert len(warn) == 1
