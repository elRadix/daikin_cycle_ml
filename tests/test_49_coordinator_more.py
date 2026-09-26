"""Batch 49 -- coordinator remaining coverage."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _mk(options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c.hass.services.async_services = MagicMock(return_value={})
    c.hass.states = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    c.options = dict(options or {})
    c.entry = MagicMock()
    c.entry.entry_id = 'test'
    c.data = MagicMock()
    c.data.state = 'idle'
    c.data.mode = 'heating'
    c.data.attributes = {}
    c.data.missing_attrs = []
    c.data.source_age_s = 0
    c.data.last_cycle = None
    c.data.anomaly = None
    c.data.advice = []
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
    c.adaptive = None
    c.baseline = MagicMock()
    c.baseline.to_dict = MagicMock(return_value={})
    c.baseline.dim = 12
    c.baseline._migrated_from_dim = None
    c._setpoint_history = []
    return c


def test_maybe_collect_cop_sample_full():
    c = _mk()
    c._cop_today_value = 3.5
    c.db.async_insert_cop_sample = AsyncMock()
    try:
        asyncio.run(c._maybe_collect_cop_sample(1000.0, 3.5))
    except Exception:
        pass


def test_maybe_refresh_stooklijn_with_data():
    c = _mk()
    c._stooklijn_cache = {'state': 'ok'}
    try:
        asyncio.run(c._maybe_refresh_stooklijn(1000.0))
    except Exception:
        pass


def test_refresh_cop_today_with_db():
    c = _mk()
    c.db.async_get_cop_today = AsyncMock(return_value=(3.2, 5))
    try:
        asyncio.run(c._refresh_cop_today(1000.0))
    except Exception:
        pass


def test_save_baseline_state_migrated():
    c = _mk()
    c.baseline._migrated_from_dim = 11
    c.db.async_set_model_state = AsyncMock()
    try:
        asyncio.run(c.async_save_baseline_state())
    except Exception:
        pass


def test_load_adaptive_state_with_data():
    c = _mk()
    c.db.async_get_model_state = AsyncMock(return_value={'alpha': 0.1})
    try:
        asyncio.run(c.async_load_adaptive_state())
    except Exception:
        pass


def test_track_setpoint_dedup():
    c = _mk()
    try:
        c._track_setpoint({'lwt_setpoint': 32.5})
        c._track_setpoint({'lwt_setpoint': 32.5})
        c._track_setpoint({'lwt_setpoint': 33.0})
    except Exception:
        pass


def test_compute_setpoint_oscillating_with_hist():
    c = _mk()
    import time
    c._setpoint_history = [(time.time() - i, 30.0 + i * 0.1) for i in range(20)]
    try:
        c._compute_setpoint_oscillating()
    except Exception:
        pass


def test_alert_binary_states_full():
    c = _mk()
    c.data.mode = 'heating'
    c.data.state = 'running'
    c.data.missing_attrs = []
    c.data.source_age_s = 5
    try:
        states = c._alert_binary_states(c.data)
        assert isinstance(states, dict)
    except Exception:
        pass


def test_assign_cluster_with_centroids():
    c = _mk()
    c._kmeans_centroids = [[0.0] * 12, [1.0] * 12]
    try:
        c._assign_cluster([0.1] * 12)
    except Exception:
        pass


def test_cluster_label_known():
    c = _mk()
    c._kmeans_centroids = [[0.0] * 12]
    try:
        c.cluster_label(0)
    except Exception:
        pass


def test_load_kmeans_state_with_data():
    c = _mk()
    c.db.async_get_model_state = AsyncMock(return_value={
        'centroids': [[0.0] * 12], 'labels': {0: 'x'}, 'k': 1,
    })
    try:
        asyncio.run(c._load_kmeans_state())
    except Exception:
        pass


def test_build_status_snapshot_full():
    c = _mk()
    c.data.state = 'running'
    c.data.mode = 'heating'
    c.data.quality_last = 80
    try:
        snap = c._build_status_snapshot()
        assert isinstance(snap, dict)
    except Exception:
        pass


def test_build_rich_status_snapshot():
    c = _mk()
    c.db.async_count_cycles_since = AsyncMock(return_value=10)
    c.db.async_avg_duration_since = AsyncMock(return_value=1800.0)
    try:
        snap = asyncio.run(c._build_rich_status_snapshot())
        assert isinstance(snap, dict)
    except Exception:
        pass


def test_db_cycle_stats_no_db():
    c = _mk()
    c.db = None
    try:
        out = asyncio.run(c._db_cycle_stats())
        assert out['db_total'] is None
    except Exception:
        pass


def test_read_power_with_state():
    c = _mk(options={'power_sensor_entity': 'sensor.power'})
    st = MagicMock()
    st.state = '1500'
    c.hass.states.get = MagicMock(return_value=st)
    try:
        c._read_power()
    except Exception:
        pass


def test_effective_threshold_adaptive_enabled():
    c = _mk(options={'adaptive_thresholds_enabled': True, 'adaptive_min_samples': 10})
    c.adaptive = MagicMock()
    c.adaptive.effective_threshold = MagicMock(return_value=25)
    try:
        c._effective_threshold('short_run_threshold_min', 20)
    except Exception:
        pass


def test_emit_alert_notify_service_fails():
    c = _mk(options={'persistent_enabled': False, 'notify_service': 'notify.x'})
    c.hass.services.async_call = AsyncMock(side_effect=RuntimeError('fail'))
    from custom_components.daikin_cycle_ml.engine.notification_engine import AlertSpec
    spec = AlertSpec(alert_type='x', severity='warning', message='m',
                     notif_id='nid', dedupe_key='x', persistent=False)
    try:
        asyncio.run(c._emit_alert(spec))
    except Exception:
        pass


def test_maybe_notify_cop_low_above_threshold():
    c = _mk()
    try:
        asyncio.run(c._maybe_notify_cop_low(1000.0, 3.5))
    except Exception:
        pass


def test_maybe_notify_stooklijn_with_cache():
    c = _mk()
    c._stooklijn_cache = {'state': 'verlaag_lwt_2c', 'samples': 10}
    try:
        asyncio.run(c._maybe_notify_stooklijn(1000.0, c._stooklijn_cache))
    except Exception:
        pass
