"""v1.19.7 fix #14: alerts persisted to DB.

Pre-fix: async_insert_alert exists in CycleDB but has zero call sites.
Alerts fire (persistent_notification) but no history in the alerts table.

Post-fix: each successfully emitted alert is inserted into alerts table.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml import coordinator as co
from custom_components.daikin_cycle_ml.engine.notification_engine import AlertSpec


@pytest.fixture(autouse=True)
def _stub_notify_full_model(monkeypatch):
    """Stub read-only property _notify_full_model at class level."""
    from unittest.mock import PropertyMock
    monkeypatch.setattr(
        co.DaikinCycleMLCoordinator,
        "_notify_full_model",
        PropertyMock(return_value=""),
    )


def _mk_alert(alert_type="short_run", severity="warning", message="test msg"):
    return AlertSpec(
        alert_type=alert_type, severity=severity, message=message,
        notif_id=f"daikin_test_{alert_type}",
        dedupe_key=alert_type, persistent=True, context=None,
    )


def _mk_coord(db=None):
    c = co.DaikinCycleMLCoordinator.__new__(co.DaikinCycleMLCoordinator)
    c.options = {}
    c.store = MagicMock()
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    c._alert_store = None
    c._alert_save_unsub = None
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._refresh_7d_rollups = AsyncMock()
    c._alert_binary_states = MagicMock(return_value={})
    c._build_alert_context = MagicMock(return_value={})
    c._boiler_kwargs_for_alerts = MagicMock(return_value={})
    c._schedule_alert_save = MagicMock()
    if db is not None:
        c.db = db
    # else: no .db attribute at all (realistic for __new__ stubs)
    return c


@pytest.mark.asyncio
async def test_alert_persisted_after_dispatch(monkeypatch):
    """Real dispatch with 1 alert -> async_insert_alert called with correct args."""
    db = MagicMock()
    db.async_insert_alert = AsyncMock(return_value=1)
    c = _mk_coord(db=db)

    alert = _mk_alert()
    monkeypatch.setattr(co, "evaluate_alerts", lambda *a, **k: [alert])

    await c._async_dispatch_alerts(MagicMock())

    db.async_insert_alert.assert_awaited_once()
    kwargs = db.async_insert_alert.await_args.kwargs
    assert kwargs["alert_type"] == "short_run"
    assert kwargs["severity"] == "warning"
    assert kwargs["message"] == "test msg"
    assert isinstance(kwargs["ts"], float)


@pytest.mark.asyncio
async def test_db_none_does_not_crash_dispatch(monkeypatch):
    """Coordinator with db=None: alerts fire, DB call skipped, no exception."""
    c = _mk_coord(db=None)  # sets db = None
    alert = _mk_alert()
    monkeypatch.setattr(co, "evaluate_alerts", lambda *a, **k: [alert])

    await c._async_dispatch_alerts(MagicMock())

    # persistent_notification was called
    assert c.hass.services.async_call.await_count >= 1


@pytest.mark.asyncio
async def test_db_attr_missing_does_not_crash_dispatch(monkeypatch):
    """Coordinator without .db attribute at all (bare __new__): no crash."""
    c = _mk_coord(db=None)
    if hasattr(c, "db"):
        delattr(c, "db")
    alert = _mk_alert()
    monkeypatch.setattr(co, "evaluate_alerts", lambda *a, **k: [alert])

    await c._async_dispatch_alerts(MagicMock())

    # dispatch completed without raising
    assert True


@pytest.mark.asyncio
async def test_db_insert_raises_does_not_break_dispatch(monkeypatch):
    """DB insert failure: alert still delivered, dispatch does not raise."""
    db = MagicMock()
    db.async_insert_alert = AsyncMock(side_effect=RuntimeError("db locked"))
    c = _mk_coord(db=db)
    alert = _mk_alert()
    monkeypatch.setattr(co, "evaluate_alerts", lambda *a, **k: [alert])

    await c._async_dispatch_alerts(MagicMock())

    # alert still went through persistent_notification
    assert c.hass.services.async_call.await_count >= 1
    # and _last_alert_sent was updated (dispatch loop continues)
    assert "short_run" in c._last_alert_sent


@pytest.mark.asyncio
async def test_multiple_alerts_each_persisted(monkeypatch):
    """Two alerts: two separate insert calls."""
    db = MagicMock()
    db.async_insert_alert = AsyncMock(return_value=1)
    c = _mk_coord(db=db)
    alerts = [_mk_alert("short_run"), _mk_alert("dhw_pendulum")]
    monkeypatch.setattr(co, "evaluate_alerts", lambda *a, **k: alerts)

    await c._async_dispatch_alerts(MagicMock())

    assert db.async_insert_alert.await_count == 2
    types = {kw.kwargs["alert_type"] for kw in db.async_insert_alert.await_args_list}
    assert types == {"short_run", "dhw_pendulum"}


@pytest.mark.asyncio
async def test_no_alerts_means_no_db_write(monkeypatch):
    """No alerts to emit: async_insert_alert never called."""
    db = MagicMock()
    db.async_insert_alert = AsyncMock(return_value=1)
    c = _mk_coord(db=db)
    monkeypatch.setattr(co, "evaluate_alerts", lambda *a, **k: [])

    await c._async_dispatch_alerts(MagicMock())

    db.async_insert_alert.assert_not_awaited()
