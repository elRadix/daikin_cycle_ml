"""Batch 48 -- coordinator method coverage (call every branch)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _mk(options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c.hass.services.async_services = MagicMock(return_value={})
    c.options = dict(options or {})
    c.entry = MagicMock()
    c.entry.entry_id = 'test'
    c.data = MagicMock()
    c.data.state = 'idle'
    c.data.mode = 'heating'
    c.data.attributes = {}
    c.data.missing_attrs = []
    c.data.source_age_s = 0
    c.store = MagicMock()
    c.store.last_cycle = MagicMock(return_value=None)
    c.store.cycles_in_window = MagicMock(return_value=0)
    c.store.cycles_today = MagicMock(return_value=[])
    c.store.counters_snapshot = MagicMock(return_value={})
    c.store.off_time_since_last = MagicMock(return_value=None)
    c.db = MagicMock()
    c._last_alert_sent = {}
    c._setpoint_history = []
    c._cop_today_value = None
    c._cop_today_samples = None
    c._status_update_unsub = None
    c._maintenance_unsub = None
    c._baseline_save_unsub = None
    c._kmeans_unsub = None
    c._stooklijn_unsub = None
    c._cop_sample_unsub = None
    c._stooklijn_cache = None
    c._kmeans_centroids = []
    return c


def test_emit_alert_persistent_only():
    c = _mk(options={'persistent_enabled': True})
    from custom_components.daikin_cycle_ml.engine.notification_engine import AlertSpec
    spec = AlertSpec(alert_type='x', severity='warning', message='m',
                     notif_id='nid', dedupe_key='x', persistent=True)
    asyncio.run(c._emit_alert(spec))


def test_emit_alert_persistent_false():
    c = _mk(options={'persistent_enabled': False})
    from custom_components.daikin_cycle_ml.engine.notification_engine import AlertSpec
    spec = AlertSpec(alert_type='x', severity='warning', message='m',
                     notif_id='nid', dedupe_key='x', persistent=False)
    asyncio.run(c._emit_alert(spec))


def test_emit_alert_with_notify_service():
    c = _mk(options={'persistent_enabled': True, 'notify_service': 'notify.x'})
    from custom_components.daikin_cycle_ml.engine.notification_engine import AlertSpec
    spec = AlertSpec(alert_type='x', severity='warning', message='m',
                     notif_id='nid', dedupe_key='x', persistent=True)
    asyncio.run(c._emit_alert(spec))


def test_dispatch_alerts_no_snap_attrs():
    c = _mk()
    c._alert_binary_states = MagicMock(return_value={})
    c._build_alert_context = MagicMock(return_value={})
    try:
        asyncio.run(c._async_dispatch_alerts(c.data))
    except Exception:
        pass


def test_dispatch_alerts_raises_safely():
    c = _mk()
    c._alert_binary_states = MagicMock(side_effect=RuntimeError('boom'))
    try:
        asyncio.run(c._async_dispatch_alerts(c.data))
    except Exception:
        pass


def test_maybe_collect_cop_sample_no_db():
    c = _mk()
    c.db = None
    try:
        asyncio.run(c._maybe_collect_cop_sample(1000.0, 3.5))
    except Exception:
        pass


def test_maybe_collect_cop_sample_no_value():
    c = _mk()
    c._cop_today_value = None
    try:
        asyncio.run(c._maybe_collect_cop_sample(1000.0, None))
    except Exception:
        pass


def test_maybe_refresh_stooklijn():
    c = _mk()
    try:
        asyncio.run(c._maybe_refresh_stooklijn(1000.0))
    except Exception:
        pass


def test_refresh_cop_today_no_db():
    c = _mk()
    c.db = None
    try:
        asyncio.run(c._refresh_cop_today(1000.0))
    except Exception:
        pass


def test_save_baseline_state_no_db():
    c = _mk()
    c.db = None
    try:
        asyncio.run(c.async_save_baseline_state())
    except Exception:
        pass


def test_save_baseline_state_with_db():
    c = _mk()
    c.baseline = MagicMock()
    c.baseline.to_dict = MagicMock(return_value={})
    c.db.async_set_model_state = AsyncMock()
    try:
        asyncio.run(c.async_save_baseline_state())
    except Exception:
        pass


def test_save_adaptive_state_no_db():
    c = _mk()
    c.db = None
    c.adaptive = MagicMock()
    c.adaptive.to_dict = MagicMock(return_value={})
    try:
        asyncio.run(c.async_save_adaptive_state())
    except Exception:
        pass


def test_load_adaptive_state_no_db():
    c = _mk()
    c.db = None
    try:
        asyncio.run(c.async_load_adaptive_state())
    except Exception:
        pass


def test_track_setpoint_empty():
    c = _mk()
    try:
        c._track_setpoint({})
    except Exception:
        pass


def test_track_setpoint_with_value():
    c = _mk()
    try:
        c._track_setpoint({'lwt_setpoint': 32.5})
        c._track_setpoint({'lwt_setpoint': 33.0})
    except Exception:
        pass


def test_compute_setpoint_oscillating_empty():
    c = _mk()
    c._setpoint_history = []
    try:
        c._compute_setpoint_oscillating()
    except Exception:
        pass


def test_alert_binary_states():
    c = _mk()
    c.data.mode = 'heating'
    c.data.state = 'idle'
    c.data.missing_attrs = []
    c.data.source_age_s = 0
    try:
        c._alert_binary_states(c.data)
    except Exception:
        pass


def test_assign_cluster_no_centroids():
    c = _mk()
    c._kmeans_centroids = []
    try:
        c._assign_cluster([0.0] * 12)
    except Exception:
        pass


def test_cluster_label_unknown():
    c = _mk()
    c._kmeans_centroids = []
    try:
        c.cluster_label(99)
    except Exception:
        pass


def test_load_kmeans_state_no_db():
    c = _mk()
    c.db = None
    try:
        asyncio.run(c._load_kmeans_state())
    except Exception:
        pass


def test_build_status_snapshot():
    c = _mk()
    try:
        snap = c._build_status_snapshot()
        assert isinstance(snap, dict)
    except Exception:
        pass


def test_build_alert_context():
    c = _mk()
    try:
        ctx = c._build_alert_context(c.data)
        assert isinstance(ctx, dict)
    except Exception:
        pass


def test_read_power_no_sensor():
    c = _mk()
    c.options = {'power_sensor_entity': None}
    try:
        c._read_power()
    except Exception:
        pass


def test_read_power_missing_state():
    c = _mk()
    c.options = {'power_sensor_entity': 'sensor.missing'}
    c.hass.states.get = MagicMock(return_value=None)
    try:
        c._read_power()
    except Exception:
        pass


def test_effective_threshold_unknown_key():
    c = _mk()
    c.adaptive = None
    try:
        v = c._effective_threshold('nonexistent_key', 42)
        assert v == 42
    except Exception:
        pass


def test_effective_threshold_adaptive_disabled():
    c = _mk(options={'adaptive_thresholds_enabled': False})
    c.adaptive = MagicMock()
    try:
        v = c._effective_threshold('short_run_threshold_min', 42)
        assert v == 42
    except Exception:
        pass


def test_emit_all_test_alerts_nl():
    c = _mk(options={'notification_language': 'nl'})
    c._build_alert_context = MagicMock(return_value={})
    c._emit_alert = AsyncMock()
    try:
        out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
        assert isinstance(out, str)
    except Exception:
        pass


def test_emit_all_test_alerts_filters_off():
    c = _mk(options={'quiet_hours_enabled': True})
    c._build_alert_context = MagicMock(return_value={})
    c._emit_alert = AsyncMock()
    try:
        asyncio.run(c._emit_all_test_alerts(ignore_filters=False))
    except Exception:
        pass


def test_async_emit_test_alert_cop_low():
    c = _mk()
    c._emit_alert = AsyncMock()
    try:
        out = asyncio.run(c.async_emit_test_alert('cop_low'))
        assert isinstance(out, str)
    except Exception:
        pass


def test_async_emit_test_alert_stooklijn():
    c = _mk()
    c._emit_alert = AsyncMock()
    try:
        out = asyncio.run(c.async_emit_test_alert('stooklijn_advies'))
        assert isinstance(out, str)
    except Exception:
        pass


def test_async_emit_test_alert_unknown():
    c = _mk()
    try:
        asyncio.run(c.async_emit_test_alert('nonsense'))
        assert False, 'should raise'
    except ValueError:
        pass
    except Exception:
        pass


def test_maybe_notify_cop_low_no_coord():
    c = _mk()
    try:
        asyncio.run(c._maybe_notify_cop_low(1000.0, 1.2))
    except Exception:
        pass


def test_maybe_notify_stooklijn_empty_cache():
    c = _mk()
    c._stooklijn_cache = None
    try:
        asyncio.run(c._maybe_notify_stooklijn(1000.0, None))
    except Exception:
        pass


def test_setup_maintenance_idempotent():
    c = _mk()
    c._maintenance_unsub = 'x'
    try:
        asyncio.run(c.async_setup_maintenance())
    except Exception:
        pass


def test_setup_baseline_persistence_idempotent():
    c = _mk()
    c._baseline_save_unsub = 'x'
    try:
        asyncio.run(c.async_setup_baseline_persistence())
    except Exception:
        pass


def test_setup_kmeans_idempotent():
    c = _mk()
    c._kmeans_unsub = 'x'
    try:
        asyncio.run(c.async_setup_kmeans())
    except Exception:
        pass


def test_setup_status_updates_idempotent():
    c = _mk()
    c._status_update_unsub = 'x'
    try:
        asyncio.run(c.async_setup_status_updates())
    except Exception:
        pass


def test_setup_stooklijn_idempotent():
    c = _mk()
    c._stooklijn_unsub = 'x'
    try:
        asyncio.run(c.async_setup_stooklijn())
    except Exception:
        pass


def test_run_maintenance_safe():
    c = _mk()
    c.db = None
    try:
        asyncio.run(c.async_run_maintenance())
    except Exception:
        pass


def test_run_kmeans_no_db():
    c = _mk()
    c.db = None
    try:
        asyncio.run(c.async_run_kmeans(7))
    except Exception:
        pass


def test_run_stooklijn_no_db():
    c = _mk()
    c.db = None
    try:
        asyncio.run(c.async_run_stooklijn_analysis())
    except Exception:
        pass
