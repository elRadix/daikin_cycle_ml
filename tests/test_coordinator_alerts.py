"""Tests for coordinator alert dispatch (Batch 6b-3b)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _bare_coord(options=None, store=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c.store = store or CycleStore()
    c.entry = MagicMock()
    c.entry.entry_id = "test"
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    return c


# ---------- _alert_binary_states ----------

def test_states_empty_store_all_false():
    c = _bare_coord()
    out = c._alert_binary_states(DataSnapshot())
    assert out == {
        "short_run": False,
        "short_off": False,
        "pendulum_hourly": False,
        "pendulum_daily": False,
    }


def test_states_keys_four():
    c = _bare_coord()
    assert set(c._alert_binary_states(DataSnapshot()).keys()) == {
        "short_run", "short_off", "pendulum_hourly", "pendulum_daily"
    }


def test_states_short_run_true():
    st = CycleStore()
    st.add_cycle({"start_ts": 100, "duration_s": 300})  # 5min < 20min default
    c = _bare_coord(store=st)
    assert c._alert_binary_states(DataSnapshot())["short_run"] is True


def test_states_short_run_false_when_long():
    st = CycleStore()
    st.add_cycle({"start_ts": 100, "duration_s": 3600})
    c = _bare_coord(store=st)
    assert c._alert_binary_states(DataSnapshot())["short_run"] is False


def test_states_pendulum_hourly_true():
    import time
    st = CycleStore()
    now = time.time()
    for i in range(4):
        st.add_cycle({"start_ts": now - i, "duration_s": 30})
    c = _bare_coord(options={"pendulum_cycles_per_hour": 4}, store=st)
    assert c._alert_binary_states(DataSnapshot())["pendulum_hourly"] is True


# ---------- _async_dispatch_alerts ----------

async def test_dispatch_no_alerts_no_service_calls():
    c = _bare_coord()
    await c._async_dispatch_alerts(DataSnapshot())
    c.hass.services.async_call.assert_not_called()


async def test_dispatch_short_run_creates_persistent():
    st = CycleStore()
    st.add_cycle({"start_ts": 100, "duration_s": 300})
    c = _bare_coord(store=st)
    await c._async_dispatch_alerts(DataSnapshot())
    calls = c.hass.services.async_call.call_args_list
    domains_services = [(call.args[0], call.args[1]) for call in calls]
    assert ("persistent_notification", "create") in domains_services


async def test_dispatch_uses_notify_service():
    st = CycleStore()
    st.add_cycle({"start_ts": 100, "duration_s": 300})
    c = _bare_coord(
        options={"notify_service": "notify.telegram_test"}, store=st
    )
    await c._async_dispatch_alerts(DataSnapshot())
    called = [
        (call.args[0], call.args[1])
        for call in c.hass.services.async_call.call_args_list
    ]
    assert ("notify", "telegram_test") in called


async def test_dispatch_updates_last_sent():
    st = CycleStore()
    st.add_cycle({"start_ts": 100, "duration_s": 300})
    c = _bare_coord(store=st)
    await c._async_dispatch_alerts(DataSnapshot())
    assert "short_run" in c._last_alert_sent
    assert c._last_alert_sent["short_run"] > 0


async def test_dispatch_second_call_suppressed_by_aggregation():
    st = CycleStore()
    st.add_cycle({"start_ts": 100, "duration_s": 300})
    c = _bare_coord(store=st)
    await c._async_dispatch_alerts(DataSnapshot())
    n_first = c.hass.services.async_call.call_count
    await c._async_dispatch_alerts(DataSnapshot())
    assert c.hass.services.async_call.call_count == n_first


async def test_dispatch_never_raises_on_service_error():
    st = CycleStore()
    st.add_cycle({"start_ts": 100, "duration_s": 300})
    c = _bare_coord(store=st)
    c.hass.services.async_call = AsyncMock(side_effect=RuntimeError("boom"))
    # must not raise
    await c._async_dispatch_alerts(DataSnapshot())


async def test_dispatch_quiet_hours_suppresses():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        _in_quiet_hours,
    )
    # Just assert integration: quiet true blocks warning alerts
    st = CycleStore()
    st.add_cycle({"start_ts": 100, "duration_s": 300})
    c = _bare_coord(
        options={
            "quiet_hours_enabled": True,
            "quiet_hours_start": "00:00",
            "quiet_hours_end": "23:59",
        },
        store=st,
    )
    await c._async_dispatch_alerts(DataSnapshot())
    # During quiet hours no persistent notification should have fired
    assert c.hass.services.async_call.call_count == 0
