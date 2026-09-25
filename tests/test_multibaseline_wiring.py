"""Tests for Batch 11c MultiBaseline wiring + persistence + kmeans."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.ml.features import VECTOR_LEN
from custom_components.daikin_cycle_ml.ml.multi_baseline import MultiBaseline
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _coord(db=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {}
    c.store = CycleStore()
    c.entry = MagicMock()
    c.entry.entry_id = "test"
    c.hass = MagicMock()
    c._last_alert_sent = {}
    c._errors_total = 0
    c._maintenance_unsub = None
    c._baseline_save_unsub = None
    c._kmeans_unsub = None
    c.baseline = MultiBaseline(VECTOR_LEN)
    c.db = db
    return c


def _rec(start_ts=100.0, mode="Heating"):
    return {
        "start_ts": start_ts,
        "end_ts": start_ts + 3600,
        "duration_s": 3600,
        "mode": mode,
        "dT_max": 7.5, "dT_avg": 5.2,
        "rps_max": 60, "rps_avg": 42.5,
        "outdoor_temp": 8.0,
        "buh_used": 0, "defrost_used": 0,
    }


# ---------- MultiBaseline wrappers ----------

def test_z_scores_returns_zero_list_when_insufficient():
    mb = MultiBaseline(2)
    assert mb.z_scores("Heating", [1.0, 2.0]) == [0.0, 0.0]


def test_max_abs_z_zero_when_insufficient():
    mb = MultiBaseline(1)
    mb.update("Heating", [1.0])
    assert mb.max_abs_z("Heating", [1.0]) == 0.0


def test_max_abs_z_positive_after_fit():
    mb = MultiBaseline(1)
    for v in [10.0, 11.0, 9.0, 10.0, 11.0]:
        mb.update("Heating", [v])
    assert mb.max_abs_z("Heating", [1000.0]) > 5.0


def test_is_anomaly_true_on_wild():
    mb = MultiBaseline(1)
    for v in [10.0, 11.0, 9.0, 10.0, 11.0]:
        mb.update("Heating", [v])
    assert mb.is_anomaly("Heating", [1000.0]) is True


def test_is_anomaly_false_on_normal():
    mb = MultiBaseline(1)
    for v in [10.0, 11.0, 9.0, 10.0, 11.0]:
        mb.update("Heating", [v])
    assert mb.is_anomaly("Heating", [10.5]) is False


def test_top_dim_returns_extreme_index():
    mb = MultiBaseline(2)
    for v in [[1.0, 10.0], [2.0, 11.0], [1.5, 9.5], [1.7, 10.2]]:
        mb.update("Heating", v)
    assert mb.top_dim("Heating", [50.0, 10.0]) == 0


def test_top_dim_none_when_insufficient():
    mb = MultiBaseline(2)
    assert mb.top_dim("Heating", [1.0, 2.0]) is None


def test_sample_count_per_mode():
    mb = MultiBaseline(1)
    mb.update("Heating", [1.0])
    mb.update("Heating", [2.0])
    mb.update("DHW", [10.0])
    assert mb.sample_count("Heating") == 2
    assert mb.sample_count("DHW") == 1
    assert mb.sample_count("unknown") == 0


def test_reset_none_clears_all_modes():
    mb = MultiBaseline(1)
    mb.update("Heating", [1.0])
    mb.update("DHW", [2.0])
    mb.reset()
    assert mb.modes() == []
    assert mb.total_samples() == 0


def test_reset_single_mode_removes_only_that():
    mb = MultiBaseline(1)
    mb.update("Heating", [1.0])
    mb.update("DHW", [2.0])
    mb.reset("Heating")
    assert "Heating" not in mb.modes()
    assert "DHW" in mb.modes()


def test_reset_unknown_mode_noop():
    mb = MultiBaseline(1)
    mb.update("Heating", [1.0])
    mb.reset("nonexistent")
    assert "Heating" in mb.modes()


# ---------- Coordinator persistence ----------

async def test_setup_baseline_persistence_no_db():
    c = _coord(db=None)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_interval"
    ) as m:
        m.return_value = MagicMock()
        await c.async_setup_baseline_persistence()
        assert c._baseline_save_unsub is not None
        assert m.call_count == 1


async def test_setup_baseline_persistence_empty_state():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=None)
    c = _coord(db=db)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_interval"
    ) as m:
        m.return_value = MagicMock()
        await c.async_setup_baseline_persistence()
        assert c.baseline.total_samples() == 0


async def test_setup_baseline_persistence_restores_state():
    saved = MultiBaseline(VECTOR_LEN)
    saved.update("Heating", [1.0] * VECTOR_LEN)
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=saved.to_dict())
    c = _coord(db=db)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_interval"
    ) as m:
        m.return_value = MagicMock()
        await c.async_setup_baseline_persistence()
        assert c.baseline.total_samples() == 1
        assert "Heating" in c.baseline.modes()


async def test_setup_baseline_persistence_handles_exception():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=RuntimeError("boom"))
    c = _coord(db=db)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_interval"
    ) as m:
        m.return_value = MagicMock()
        await c.async_setup_baseline_persistence()


async def test_setup_baseline_persistence_idempotent():
    c = _coord(db=None)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_interval"
    ) as m:
        m.return_value = MagicMock()
        await c.async_setup_baseline_persistence()
        first = c._baseline_save_unsub
        await c.async_setup_baseline_persistence()
        assert c._baseline_save_unsub is first
        assert m.call_count == 1


async def test_save_baseline_state_no_db():
    c = _coord(db=None)
    out = await c.async_save_baseline_state()
    assert out is False


async def test_save_baseline_state_ok():
    db = MagicMock()
    db.async_set_model_state = AsyncMock()
    c = _coord(db=db)
    c.baseline.update("Heating", [1.0] * VECTOR_LEN)
    out = await c.async_save_baseline_state()
    assert out is True
    assert db.async_set_model_state.await_count == 1
    assert db.async_set_model_state.await_args[0][0] == "baseline_state"


async def test_save_baseline_state_error_returns_false():
    db = MagicMock()
    db.async_set_model_state = AsyncMock(side_effect=RuntimeError("boom"))
    c = _coord(db=db)
    out = await c.async_save_baseline_state()
    assert out is False


async def test_baseline_save_callback_swallows_exception():
    c = _coord(db=None)
    c.async_save_baseline_state = AsyncMock(side_effect=RuntimeError("x"))
    await c._async_baseline_save_callback(None)


# ---------- Coordinator kmeans ----------

async def test_setup_kmeans_schedules():
    c = _coord()
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_change"
    ) as m:
        m.return_value = MagicMock()
        await c.async_setup_kmeans()
        assert m.call_count == 1
        assert c._kmeans_unsub is not None


async def test_setup_kmeans_idempotent():
    c = _coord()
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_change"
    ) as m:
        m.return_value = MagicMock()
        await c.async_setup_kmeans()
        await c.async_setup_kmeans()
        assert m.call_count == 1


async def test_run_kmeans_no_db():
    c = _coord(db=None)
    out = await c.async_run_kmeans()
    assert out["ok"] is False
    assert out["reason"] == "no_db"


async def test_run_kmeans_fetch_error():
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(side_effect=RuntimeError("boom"))
    c = _coord(db=db)
    out = await c.async_run_kmeans()
    assert out["ok"] is False
    assert out["reason"] == "fetch_failed"


async def test_run_kmeans_too_few():
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(return_value=[])
    c = _coord(db=db)
    out = await c.async_run_kmeans()
    assert out["ok"] is False
    assert out["reason"] == "too_few"
    assert out["n"] == 0


async def test_run_kmeans_happy():
    recs = [_rec(100.0 + i * 5000) for i in range(9)]
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(return_value=recs)
    db.async_set_model_state = AsyncMock()
    c = _coord(db=db)
    out = await c.async_run_kmeans(days=7)
    assert out["ok"] is True
    assert out["k"] == 3
    assert out["n"] >= 3
    assert db.async_set_model_state.await_count == 1
    assert db.async_set_model_state.await_args[0][0] == "kmeans_state"


async def test_run_kmeans_saves_ts():
    recs = [_rec(100.0 + i * 5000) for i in range(5)]
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(return_value=recs)
    db.async_set_model_state = AsyncMock()
    c = _coord(db=db)
    await c.async_run_kmeans()
    payload = db.async_set_model_state.await_args[0][1]
    assert "ts" in payload


async def test_kmeans_callback_swallows_exception():
    c = _coord(db=None)
    c.async_run_kmeans = AsyncMock(side_effect=RuntimeError("x"))
    await c._async_kmeans_callback(None)


# ---------- Services recompute ----------

async def test_recompute_no_db():
    from custom_components.daikin_cycle_ml.services import (
        _do_recompute_baseline,
    )
    c = MagicMock()
    c.db = None
    out = await _do_recompute_baseline(c, 7)
    assert out["computed"] is False
    assert out["reason"] == "no_db"


async def test_recompute_no_baseline():
    from custom_components.daikin_cycle_ml.services import (
        _do_recompute_baseline,
    )
    c = MagicMock()
    c.db = MagicMock()
    c.baseline = None
    out = await _do_recompute_baseline(c, 7)
    assert out["computed"] is False
    assert out["reason"] == "no_baseline"


async def test_recompute_fetch_error():
    from custom_components.daikin_cycle_ml.services import (
        _do_recompute_baseline,
    )
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(side_effect=RuntimeError("boom"))
    c = MagicMock()
    c.db = db
    c.baseline = MultiBaseline(VECTOR_LEN)
    out = await _do_recompute_baseline(c, 7)
    assert out["computed"] is False
    assert out["reason"] == "fetch_failed"


async def test_recompute_no_data():
    from custom_components.daikin_cycle_ml.services import (
        _do_recompute_baseline,
    )
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(return_value=[])
    c = MagicMock()
    c.db = db
    c.baseline = MultiBaseline(VECTOR_LEN)
    out = await _do_recompute_baseline(c, 7)
    assert out["computed"] is False
    assert out["reason"] == "no_data"
    assert out["samples"] == 0


async def test_recompute_happy():
    from custom_components.daikin_cycle_ml.services import (
        _do_recompute_baseline,
    )
    recs = [_rec(100.0 + i * 5000, mode="Heating") for i in range(3)]
    recs += [_rec(50000.0 + i * 5000, mode="DHW") for i in range(2)]
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(return_value=recs)
    db.async_set_model_state = AsyncMock()
    c = MagicMock()
    c.db = db
    c.baseline = MultiBaseline(VECTOR_LEN)
    out = await _do_recompute_baseline(c, 7)
    assert out["computed"] is True
    assert out["samples"] >= 1
    assert db.async_set_model_state.await_count == 1
    assert db.async_set_model_state.await_args[0][0] == "baseline_state"


async def test_recompute_resets_before_update():
    from custom_components.daikin_cycle_ml.services import (
        _do_recompute_baseline,
    )
    recs = [_rec(100.0 + i * 5000) for i in range(3)]
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(return_value=recs)
    db.async_set_model_state = AsyncMock()
    c = MagicMock()
    c.db = db
    c.baseline = MultiBaseline(VECTOR_LEN)
    c.baseline.update("Heating", [999.0] * VECTOR_LEN)
    c.baseline.update("Heating", [999.0] * VECTOR_LEN)
    out = await _do_recompute_baseline(c, 7)
    assert out["computed"] is True
    assert c.baseline.total_samples() == out["samples"]
