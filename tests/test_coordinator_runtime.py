"""Batch 25 tests: runtime coordinator functions (status, adaptive, kmeans)."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)


def _bare(options=None, db=None, store=None, data=None, baseline=None,
          adaptive=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c._setpoint_history = None
    c._last_setpoint = None
    c._status_update_unsub = None
    c._kmeans_centroids = []
    c._cluster_labels = {}
    c.db = db
    c.store = store if store is not None else MagicMock()
    c.data = data
    c.baseline = baseline if baseline is not None else MagicMock()
    c.adaptive = adaptive
    c.hass = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c.hass.services.async_services = MagicMock(return_value={})
    return c


# ============ _build_status_snapshot ============

def test_status_snapshot_empty_store():
    st = MagicMock()
    st.counters_snapshot.return_value = {}
    st.last_cycle.return_value = None
    base = MagicMock()
    base.total_samples.return_value = 0
    base.modes.return_value = []
    c = _bare(store=st, baseline=base, data=DataSnapshot())
    snap = c._build_status_snapshot()
    assert snap["mode"] == "unknown"
    assert snap["state"] == "idle"
    assert snap["baseline_samples"] == 0
    assert snap["last_cycle_ago_min"] is None
    assert snap["quality_last"] is None


def test_status_snapshot_with_counters_and_last_cycle():
    st = MagicMock()
    st.counters_snapshot.return_value = {"cycles_today": 7}
    st.last_cycle.return_value = {
        "end_ts": time.time() - 600,  # 10 min ago
        "quality_score": 72,
    }
    base = MagicMock()
    base.total_samples.return_value = 42
    base.modes.return_value = ["Heating", "DHW"]
    c = _bare(options={"target_cycles_per_day": 12},
              store=st, baseline=base, data=DataSnapshot())
    snap = c._build_status_snapshot()
    assert snap["cycles_today"] == 7
    assert snap["target_cpd"] == 12
    assert snap["quality_last"] == 72
    assert snap["last_cycle_ago_min"] is not None
    assert 9 <= snap["last_cycle_ago_min"] <= 11
    assert snap["baseline_modes"] == ["Heating", "DHW"]


def test_status_snapshot_with_anomaly_and_advice():
    st = MagicMock()
    st.counters_snapshot.return_value = {}
    st.last_cycle.return_value = None
    base = MagicMock()
    base.total_samples.return_value = 5
    base.modes.return_value = ["Heating"]
    anom = MagicMock()
    anom.severity = "warning"
    adv = MagicMock()
    adv.title = "Check setpoint"
    snap_in = DataSnapshot(mode="Heating", anomaly=anom, advice=[adv])
    c = _bare(store=st, baseline=base, data=snap_in)
    out = c._build_status_snapshot()
    assert out["anomaly_severity"] == "warning"
    assert out["top_advice"] == "Check setpoint"


def test_status_snapshot_store_throws_falls_back():
    st = MagicMock()
    st.counters_snapshot.side_effect = RuntimeError("boom")
    st.last_cycle.side_effect = RuntimeError("boom")
    base = MagicMock()
    base.total_samples.return_value = 0
    base.modes.return_value = []
    c = _bare(store=st, baseline=base, data=DataSnapshot())
    snap = c._build_status_snapshot()
    assert snap["cycles_today"] is None
    assert snap["last_cycle_ago_min"] is None


def test_status_snapshot_advice_text_attr_fallback():
    st = MagicMock()
    st.counters_snapshot.return_value = {}
    st.last_cycle.return_value = None
    base = MagicMock()
    base.total_samples.return_value = 0
    base.modes.return_value = []
    adv = MagicMock(spec=["text"])
    adv.text = "legacy"
    c = _bare(store=st, baseline=base, data=DataSnapshot(advice=[adv]))
    snap = c._build_status_snapshot()
    assert snap["top_advice"] == "legacy"


def test_status_snapshot_bad_end_ts_safe():
    st = MagicMock()
    st.counters_snapshot.return_value = {}
    st.last_cycle.return_value = {"end_ts": "junk", "quality_score": 50}
    base = MagicMock()
    base.total_samples.return_value = 0
    base.modes.return_value = []
    c = _bare(store=st, baseline=base, data=DataSnapshot())
    snap = c._build_status_snapshot()
    assert snap["last_cycle_ago_min"] is None
    assert snap["quality_last"] == 50


# ============ async_setup_status_updates ============

async def test_setup_status_updates_already_scheduled_no_op():
    c = _bare(options={"status_update_enabled": True})
    c._status_update_unsub = object()
    with patch("custom_components.daikin_cycle_ml.coordinator.async_track_time_interval") as tracker:
        await c.async_setup_status_updates()
    tracker.assert_not_called()


async def test_setup_status_updates_disabled_by_option():
    c = _bare(options={"status_update_enabled": False})
    with patch("custom_components.daikin_cycle_ml.coordinator.async_track_time_interval") as tracker:
        await c.async_setup_status_updates()
    tracker.assert_not_called()
    assert c._status_update_unsub is None


async def test_setup_status_updates_valid_schedules():
    c = _bare(options={"status_update_enabled": True,
                       "status_update_interval_hours": 6})
    with patch("custom_components.daikin_cycle_ml.coordinator.async_track_time_interval") as tracker:
        tracker.return_value = "UNSUB"
        await c.async_setup_status_updates()
    tracker.assert_called_once()
    assert c._status_update_unsub == "UNSUB"


async def test_setup_status_updates_bad_hours_fallback():
    c = _bare(options={"status_update_enabled": True,
                       "status_update_interval_hours": "junk"})
    with patch("custom_components.daikin_cycle_ml.coordinator.async_track_time_interval") as tracker:
        tracker.return_value = "UNSUB"
        await c.async_setup_status_updates()
    tracker.assert_called_once()


async def test_setup_status_updates_hours_below_min():
    c = _bare(options={"status_update_enabled": True,
                       "status_update_interval_hours": 0})
    with patch("custom_components.daikin_cycle_ml.coordinator.async_track_time_interval") as tracker:
        tracker.return_value = "UNSUB"
        await c.async_setup_status_updates()
    tracker.assert_called_once()


# ============ _async_status_update_callback ============

async def test_callback_calls_emit():
    c = _bare()
    c.async_emit_status_update = AsyncMock(return_value="ok")
    await c._async_status_update_callback(None)
    c.async_emit_status_update.assert_awaited_once()


async def test_callback_swallows_exception():
    c = _bare()
    c.async_emit_status_update = AsyncMock(side_effect=RuntimeError("boom"))
    await c._async_status_update_callback(None)  # must not raise


# ============ async_emit_status_update ============

async def test_emit_status_persistent_only():
    st = MagicMock()
    st.counters_snapshot.return_value = {}
    st.last_cycle.return_value = None
    base = MagicMock()
    base.total_samples.return_value = 0
    base.modes.return_value = []
    c = _bare(options={"notify_emoji_enabled": False},
              store=st, baseline=base, data=DataSnapshot())
    msg = await c.async_emit_status_update()
    assert isinstance(msg, str)
    assert msg
    # Only persistent_notification called
    assert c.hass.services.async_call.await_count == 1
    args = c.hass.services.async_call.await_args.args
    assert args[0] == "persistent_notification"


async def test_emit_status_with_notify_service():
    st = MagicMock()
    st.counters_snapshot.return_value = {}
    st.last_cycle.return_value = None
    base = MagicMock()
    base.total_samples.return_value = 0
    base.modes.return_value = []
    c = _bare(options={"notify_emoji_enabled": False,
                       "notify_service": "notify.mobile_app_test"},
              store=st, baseline=base, data=DataSnapshot())
    await c.async_emit_status_update()
    assert c.hass.services.async_call.await_count == 2


async def test_emit_status_persistent_throws_still_returns():
    st = MagicMock()
    st.counters_snapshot.return_value = {}
    st.last_cycle.return_value = None
    base = MagicMock()
    base.total_samples.return_value = 0
    base.modes.return_value = []
    c = _bare(options={"notify_emoji_enabled": False},
              store=st, baseline=base, data=DataSnapshot())

    call_count = [0]

    async def flaky(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("persistent fail")

    c.hass.services.async_call = AsyncMock(side_effect=flaky)
    msg = await c.async_emit_status_update()
    assert isinstance(msg, str)


async def test_emit_status_notify_service_throws_still_returns():
    st = MagicMock()
    st.counters_snapshot.return_value = {}
    st.last_cycle.return_value = None
    base = MagicMock()
    base.total_samples.return_value = 0
    base.modes.return_value = []
    c = _bare(options={"notify_emoji_enabled": False,
                       "notify_service": "notify.broken"},
              store=st, baseline=base, data=DataSnapshot())

    call_count = [0]

    async def flaky(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("notify fail")

    c.hass.services.async_call = AsyncMock(side_effect=flaky)
    msg = await c.async_emit_status_update()
    assert isinstance(msg, str)


# ============ async_save_adaptive_state ============

async def test_save_adaptive_no_db():
    c = _bare(db=None)
    assert await c.async_save_adaptive_state() is False


async def test_save_adaptive_ok():
    db = MagicMock()
    db.async_set_model_state = AsyncMock(return_value=True)
    ad = MagicMock()
    ad.to_dict.return_value = {"x": 1}
    c = _bare(db=db, adaptive=ad)
    assert await c.async_save_adaptive_state() is True
    db.async_set_model_state.assert_awaited_once()


async def test_save_adaptive_db_throws():
    db = MagicMock()
    db.async_set_model_state = AsyncMock(side_effect=RuntimeError("boom"))
    ad = MagicMock()
    ad.to_dict.return_value = {}
    c = _bare(db=db, adaptive=ad)
    assert await c.async_save_adaptive_state() is False


# ============ async_load_adaptive_state ============

async def test_load_adaptive_no_db():
    c = _bare(db=None)
    assert await c.async_load_adaptive_state() is False


async def test_load_adaptive_no_data():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=None)
    c = _bare(db=db)
    assert await c.async_load_adaptive_state() is False


async def test_load_adaptive_ok():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={"dims": {}})
    c = _bare(db=db)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.AdaptiveThresholds"
    ) as AT:
        AT.from_dict.return_value = "NEW"
        assert await c.async_load_adaptive_state() is True
        assert c.adaptive == "NEW"


async def test_load_adaptive_db_throws():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=RuntimeError("boom"))
    c = _bare(db=db)
    assert await c.async_load_adaptive_state() is False


# ============ _load_kmeans_state ============

async def test_load_kmeans_no_db():
    c = _bare(db=None)
    assert await c._load_kmeans_state() is False


async def test_load_kmeans_no_data():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=None)
    c = _bare(db=db)
    assert await c._load_kmeans_state() is False


async def test_load_kmeans_empty_centroids():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={"centroids": []})
    c = _bare(db=db)
    assert await c._load_kmeans_state() is False


async def test_load_kmeans_legacy_8dim_reset():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        return_value={"centroids": [[1.0] * 8, [2.0] * 8]}
    )
    c = _bare(db=db)
    assert await c._load_kmeans_state() is False
    assert c._kmeans_centroids == []


async def test_load_kmeans_ok_11dim():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        return_value={"centroids": [[1.0] * 11, [2.0] * 11]}
    )
    c = _bare(db=db)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.classify_clusters"
    ) as cc:
        cc.return_value = {"labels": "set"}
        assert await c._load_kmeans_state() is True
        assert len(c._kmeans_centroids) == 2
        assert c._cluster_labels == {"labels": "set"}


async def test_load_kmeans_db_throws():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=RuntimeError("boom"))
    c = _bare(db=db)
    assert await c._load_kmeans_state() is False
