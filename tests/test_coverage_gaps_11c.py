"""Targeted coverage-gap tests for Batch 11c-3."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.ml.behaviour_baseline import BehaviourBaseline
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    _opt_float as ne_opt_float,
)
from custom_components.daikin_cycle_ml.engine.quality_scorer import (
    _opt as qs_opt,
)
from custom_components.daikin_cycle_ml.ml.baseline import (
    AdaptiveBaseline,
    Baseline,
)
from custom_components.daikin_cycle_ml.ml.features import VECTOR_LEN
from custom_components.daikin_cycle_ml.ml.multi_baseline import MultiBaseline

# ---------- baseline.py ----------


def test_baseline_z_scores_dim_mismatch_raises():
    b = Baseline(2)
    for _ in range(3):
        b.update([1.0, 2.0])
    with pytest.raises(ValueError):
        b.z_scores([1.0])


def test_baseline_top_dim_none_when_insufficient():
    b = Baseline(2)
    assert b.top_dim([1.0, 2.0]) is None


def test_adaptive_baseline_outlier_skip_z_property():
    ab = AdaptiveBaseline(2, outlier_skip_z=4.25)
    assert ab.outlier_skip_z == 4.25


# ---------- notification_engine.py ----------


def test_ne_opt_float_bad_string_returns_default():
    assert ne_opt_float({"x": "bad"}, "x", 2.0) == 2.0


def test_ne_opt_float_none_opts_returns_default():
    assert ne_opt_float(None, "x", 3.5) == 3.5


# ---------- quality_scorer.py ----------


def test_qs_opt_bad_value_returns_default():
    assert qs_opt({"threshold": "bad"}, "threshold", 7.5) == 7.5


def test_qs_opt_none_opts_returns_default():
    assert qs_opt(None, "k", 1.25) == 1.25


# ---------- services.py recompute edges ----------


# #443: the service delegates to coordinator.async_relearn_models (replay
# into a fresh BehaviourBaseline + adaptive runs + k-means retrain). The v1
# reset / update / to_dict error paths are gone; the replay itself is
# covered with a real DB in tests/test_443_ml_v2_wiring.py.


async def test_recompute_skips_invalid_records():
    from custom_components.daikin_cycle_ml.services import (
        _do_recompute_baseline,
    )

    c = MagicMock()
    c.db = MagicMock()
    c.baseline = BehaviourBaseline()  # #443
    c.async_relearn_models = AsyncMock(return_value={"cycles": 3, "samples": 0})
    out = await _do_recompute_baseline(c, 7)
    assert out["computed"] is True
    assert out["samples"] == 0
    c.async_relearn_models.assert_awaited_once_with(days=7)




async def test_recompute_relearn_exception_reported():
    from custom_components.daikin_cycle_ml.services import (
        _do_recompute_baseline,
    )

    c = MagicMock()
    c.db = MagicMock()
    c.baseline = BehaviourBaseline()
    c.async_relearn_models = AsyncMock(side_effect=RuntimeError("boom"))
    out = await _do_recompute_baseline(c, 7)
    assert out["computed"] is False
    assert out["error"] == "boom"


async def test_recompute_passes_relearn_stats():
    from custom_components.daikin_cycle_ml.services import (
        _do_recompute_baseline,
    )

    c = MagicMock()
    c.db = MagicMock()
    c.baseline = BehaviourBaseline()
    stats = {"cycles": 1, "samples": 1, "adaptive_runs": 1, "kmeans": {"ok": False}}
    c.async_relearn_models = AsyncMock(return_value=stats)
    out = await _do_recompute_baseline(c, 7)
    assert out == {"computed": True, "days": 7, **stats}


async def test_handle_run_maintenance_not_supported():
    from custom_components.daikin_cycle_ml.services import (
        ATTR_ENTRY_ID,
        _handle_run_maintenance,
    )

    coord = MagicMock(spec=[])
    hass = MagicMock()
    with patch(
        "custom_components.daikin_cycle_ml.services._resolve_coordinator",
        return_value=coord,
    ):
        call = MagicMock()
        call.data = {ATTR_ENTRY_ID: "test"}
        out = await _handle_run_maintenance(hass, call)
        assert out["ok"] is False
        assert out["reason"] == "not_supported"


# ---------- storage/db.py ----------


def test_db_path_property(tmp_path):
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "x.db")
    assert str(db.path).endswith("x.db")


async def test_db_open_idempotent(tmp_path):
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "y.db")
    await db.async_open()
    await db.async_open()
    assert db.is_open is True
    await db.async_close()


async def test_db_get_model_state_corrupt_json(tmp_path):
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "z.db")
    await db.async_open()
    await db.async_initialize()
    conn = db._require()
    await conn.execute(
        "INSERT OR REPLACE INTO model_state (key, value_json, updated_ts) VALUES (?,?,?)",
        ("bad", "not{json", 0.0),
    )
    await conn.commit()
    out = await db.async_get_model_state("bad", default="fb")
    assert out == "fb"
    await db.async_close()


async def test_db_daily_summary_empty(tmp_path):
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "d.db")
    await db.async_open()
    await db.async_initialize()
    await db.async_run_maintenance(cycle_retention_days=-1, alert_retention_days=-1, vacuum=False)
    rows = await db.async_daily_summary(days=9999)
    assert rows == []
    await db.async_close()


async def test_db_count_empty(tmp_path):
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "c.db")
    await db.async_open()
    await db.async_initialize()
    n = await db.async_count("cycles")
    assert n == 0
    await db.async_close()


async def test_db_run_maintenance_empty(tmp_path):
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "m.db")
    await db.async_open()
    await db.async_initialize()
    out = await db.async_run_maintenance(
        cycle_retention_days=90,
        alert_retention_days=30,
        vacuum=False,
    )
    assert isinstance(out, dict)
    await db.async_close()


async def test_db_insert_cycles_and_daily_summary(tmp_path):
    import time as _t

    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "s.db")
    await db.async_open()
    await db.async_initialize()
    now = _t.time()
    for i in range(3):
        await db.async_insert_cycle(
            {
                "start_ts": now - 3600 - i * 100,
                "end_ts": now - i * 100,
                "duration_s": 3600,
                "mode": "Heating",
                "dT_max": 5.0,
                "dT_avg": 4.0,
                "rps_max": 60,
                "rps_avg": 40.0,
                "outdoor_temp": 8.0,
                "buh_used": 1 if i == 0 else 0,
                "defrost_used": 1 if i == 1 else 0,
            }
        )
    await db.async_run_maintenance(cycle_retention_days=-1, alert_retention_days=-1, vacuum=False)
    rows = await db.async_daily_summary(days=9999)
    assert len(rows) >= 1
    await db.async_close()
