"""Coverage for coordinator.py exception + guard paths (v0.4.0)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator, DataSnapshot,
)
from custom_components.daikin_cycle_ml.ml.features import VECTOR_LEN
from custom_components.daikin_cycle_ml.ml.multi_baseline import (
    MultiBaseline,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _bare(options=None, db=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c.store = CycleStore()
    c.entry = MagicMock()
    c.entry.entry_id = 'test'
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    c._errors_total = 0
    c.baseline = MultiBaseline(VECTOR_LEN)
    c.db = db
    return c


def _rec(i=0):
    return {
        'start_ts': 100.0 + i, 'end_ts': 200.0 + i,
        'duration_s': 100, 'mode': 'heating',
        'dT_max': 5.0, 'dT_avg': 3.0,
        'rps_max': 40, 'rps_avg': 30, 'outdoor_temp': 8.0,
        'buh_used': 0, 'defrost_used': 0,
    }


async def test_maintenance_callback_exception():
    c = _bare()
    c.async_run_maintenance = AsyncMock(
        side_effect=RuntimeError('boom'))
    await c._async_maintenance_callback(None)


async def test_maintenance_read_state_exception():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        side_effect=RuntimeError('boom'))
    db.async_run_maintenance = AsyncMock(return_value={'deleted': 0})
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    c.options = {'retention_enabled': True}
    out = await c.async_run_maintenance(force=True)
    assert out['ok'] is True


async def test_maintenance_write_state_exception():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_run_maintenance = AsyncMock(return_value={'deleted': 0})
    db.async_set_model_state = AsyncMock(
        side_effect=RuntimeError('boom'))
    c = _bare(db=db)
    c.options = {'retention_enabled': True}
    out = await c.async_run_maintenance(force=True)
    assert out['ok'] is True


async def test_kmeans_callback_not_sunday():
    c = _bare()
    c.async_run_kmeans = AsyncMock()
    await c._async_kmeans_callback(datetime(2026, 9, 21))
    c.async_run_kmeans.assert_not_called()


async def test_kmeans_callback_sunday():
    c = _bare()
    c.async_run_kmeans = AsyncMock()
    await c._async_kmeans_callback(datetime(2026, 9, 27))
    c.async_run_kmeans.assert_called_once()


async def test_kmeans_run_failure():
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(
        return_value=[_rec(0), _rec(1), _rec(2)])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    p = 'custom_components.daikin_cycle_ml.ml.clustering.kmeans'
    with patch(p, side_effect=RuntimeError('boom')):
        out = await c.async_run_kmeans(days=7)
    assert out['ok'] is False
    assert out['reason'] == 'kmeans_failed'


async def test_kmeans_save_state_failure():
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(
        return_value=[_rec(0), _rec(1), _rec(2)])
    db.async_set_model_state = AsyncMock(
        side_effect=RuntimeError('boom'))
    c = _bare(db=db)
    out = await c.async_run_kmeans(days=7)
    assert out['ok'] is True


async def test_update_data_outer_exception():
    c = _bare()
    c.source_entity = 'sensor.test'
    c.detector = MagicMock()
    c.hass.states.get = MagicMock(return_value=MagicMock())
    p = 'custom_components.daikin_cycle_ml.coordinator.read'
    with patch(p, side_effect=RuntimeError('boom')):
        snap = await c._async_update_data()
    assert snap.errors == 1
    assert c._errors_total == 1


async def test_process_cycle_ml_failure():
    c = _bare()
    p = ('custom_components.daikin_cycle_ml.coordinator'
         '.extract_feature_vector')
    with patch(p, side_effect=RuntimeError('boom')):
        await c._process_new_cycle(_rec(), DataSnapshot())


async def test_process_cycle_cluster_assign():
    db = MagicMock()
    db.async_insert_cycle = AsyncMock(return_value=42)
    db.async_insert_features = AsyncMock()
    db.async_update_cycle_cluster = AsyncMock()
    c = _bare(db=db)
    c._assign_cluster = MagicMock(return_value=1)
    snap = DataSnapshot()
    await c._process_new_cycle(_rec(), snap)
    assert snap.cluster_id == 1


def test_effective_threshold_enabled():
    c = _bare()
    c.options = {'adaptive_thresholds_enabled': True}
    c.data = DataSnapshot(mode='heating')
    c.adaptive = MagicMock()
    c.adaptive.suggest = MagicMock(
        return_value={'short_run_min': 25})
    assert c._effective_threshold('short_run_min', 20) == 25


def test_effective_threshold_enabled_unknown_key():
    c = _bare()
    c.options = {'adaptive_thresholds_enabled': True}
    c.data = DataSnapshot(mode='heating')
    c.adaptive = MagicMock()
    c.adaptive.suggest = MagicMock(return_value={})
    assert c._effective_threshold('short_run_min', 20) == 20


async def test_dispatch_alerts_failure():
    c = _bare()
    c._alert_binary_states = MagicMock(
        side_effect=RuntimeError('boom'))
    await c._async_dispatch_alerts(DataSnapshot())


async def test_emit_alert_notify_failure():
    c = _bare(options={'notify_service': 'notify.test'})
    alert = MagicMock()
    alert.persistent = False
    alert.message = 'test'
    alert.notif_id = 'x'
    alert.alert_type = 'short_run'
    c.hass.services.async_call = AsyncMock(
        side_effect=RuntimeError('boom'))
    await c._emit_alert(alert)
