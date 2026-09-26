"""Batch 31cd coverage boosters: clustering, db cluster methods, helper funcs."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import sensor as s_mod
from custom_components.daikin_cycle_ml import binary_sensor as bs_mod
from custom_components.daikin_cycle_ml.ml import clustering as cl
from custom_components.daikin_cycle_ml.storage.db import CycleDB


# ────────────────────────────────────────────────────────────
# Clustering module (correct API: kmeans returns ClusteringResult)
# ────────────────────────────────────────────────────────────

def test_kmeans_empty_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        cl.kmeans([], 2)


def test_kmeans_single_vector():
    result = cl.kmeans([[1.0, 2.0]], 1)
    assert isinstance(result, cl.ClusteringResult)
    assert len(result.centroids) == 1
    assert result.labels == [0]


def test_kmeans_two_well_separated():
    vecs = [[0.0, 0.0], [0.1, 0.1], [10.0, 10.0], [10.1, 10.1]]
    result = cl.kmeans(vecs, 2, seed=42)
    assert len(result.centroids) == 2
    assert result.labels[0] == result.labels[1]
    assert result.labels[2] == result.labels[3]
    assert result.labels[0] != result.labels[2]


def test_kmeans_k_larger_than_samples():
    result = cl.kmeans([[1.0]], 3, seed=1)
    # Should not crash; either fewer centroids or duplicated
    assert isinstance(result, cl.ClusteringResult)
    assert len(result.labels) == 1


def test_nearest_centroid_picks_closest():
    centroids = [[0.0, 0.0], [10.0, 10.0]]
    assert cl.nearest_centroid([1.0, 1.0], centroids) == 0
    assert cl.nearest_centroid([9.0, 9.0], centroids) == 1


def test_nearest_centroid_empty():
    assert cl.nearest_centroid([1.0], []) is None


def test_labels_to_dict_accepts_result():
    vecs = [[0.0, 0.0], [0.1, 0.1], [10.0, 10.0], [10.1, 10.1]]
    result = cl.kmeans(vecs, 2, seed=42)
    d = cl.labels_to_dict(result)
    assert isinstance(d, dict)
    # Actual API: metadata dict
    assert "centroids" in d
    assert "cluster_sizes" in d
    assert "k" in d
    assert d["k"] == 2
    assert sum(d["cluster_sizes"]) == 4


def test_classify_clusters_accepts_centroids():
    centroids = [[0.0, 0.0], [10.0, 10.0]]
    out = cl.classify_clusters(centroids)
    assert isinstance(out, dict)
    assert set(out.keys()) == {0, 1}
    # Values are strings (labels)
    assert all(isinstance(v, str) for v in out.values())


# ────────────────────────────────────────────────────────────
# DB cluster methods
# ────────────────────────────────────────────────────────────

async def test_db_ensure_cluster_column_idempotent(tmp_path):
    db = CycleDB(str(tmp_path / "c.db"))
    await db.async_open()
    await db.async_initialize()
    try:
        r1 = await db.async_ensure_cluster_column()
        r2 = await db.async_ensure_cluster_column()
        assert r1 in (True, False)
        assert r2 in (True, False)
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_db_update_cycle_cluster(tmp_path):
    db = CycleDB(str(tmp_path / "c2.db"))
    await db.async_open()
    await db.async_initialize()
    try:
        await db.async_ensure_cluster_column()
        row = {
            "start_ts": 1.0, "end_ts": 100.0, "duration_s": 99.0,
            "mode": "heating", "dT_max": 5.0, "dT_avg": 3.0,
            "rps_max": 50, "rps_avg": 35.0, "outdoor_temp": 8.0,
            "buh_used": 0, "defrost_used": 0, "quality_score": 85,
        }
        cid = await db.async_insert_cycle(row)
        assert cid is not None
        await db.async_update_cycle_cluster(cid, 2)
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_db_count_by_cluster(tmp_path):
    db = CycleDB(str(tmp_path / "c3.db"))
    await db.async_open()
    await db.async_initialize()
    try:
        await db.async_ensure_cluster_column()
        for mode in ("heating", "heating", "dhw"):
            await db.async_insert_cycle({
                "start_ts": 1.0, "end_ts": 100.0, "duration_s": 99.0,
                "mode": mode, "dT_max": 5.0, "dT_avg": 3.0,
                "rps_max": 50, "rps_avg": 35.0, "outdoor_temp": 8.0,
                "buh_used": 0, "defrost_used": 0, "quality_score": 85,
            })
        counts = await db.async_count_by_cluster()
        assert isinstance(counts, dict)
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ────────────────────────────────────────────────────────────
# Sensor helper functions
# ────────────────────────────────────────────────────────────

def test_avg_empty_and_none():
    assert s_mod._avg([]) is None
    assert s_mod._avg([None, None]) is None


def test_avg_mixed_values():
    assert s_mod._avg([1, 2, 3]) == 2
    assert s_mod._avg([1.0, "junk", 3.0]) == 2.0


def test_max_or_none():
    assert s_mod._max_or_none([]) is None
    assert s_mod._max_or_none([1, 5, 3]) == 5


def test_min_or_none():
    assert s_mod._min_or_none([]) is None
    assert s_mod._min_or_none([5, 1, 3]) == 1


def test_ratio_zero_denominator():
    assert s_mod._ratio(5, 0) is None
    assert s_mod._ratio(5, -1) is None


def test_ratio_normal():
    assert s_mod._ratio(1, 4) == 25.0


def test_dt_from_attrs_missing():
    assert s_mod._dt_from_attrs({}) is None
    assert s_mod._dt_from_attrs({"a": 1}) is None


def test_dt_from_attrs_computes():
    from custom_components.daikin_cycle_ml.const import (
        ATTR_INLET_WATER_R4T, ATTR_LEAVING_WATER_AFTER_BUH,
    )
    v = s_mod._dt_from_attrs({
        ATTR_LEAVING_WATER_AFTER_BUH: 40.0,
        ATTR_INLET_WATER_R4T: 35.0,
    })
    assert v == 5.0


def test_rps_from_attrs():
    from custom_components.daikin_cycle_ml.const import ATTR_INV_FREQUENCY_RPS
    assert s_mod._rps_from_attrs({}) is None
    assert s_mod._rps_from_attrs({ATTR_INV_FREQUENCY_RPS: 40}) == 40.0


def test_avg_off_time_single():
    assert s_mod._avg_off_time([]) is None
    assert s_mod._avg_off_time([{"start_ts": 0, "end_ts": 100}]) is None


def test_avg_off_time_multi():
    cycles = [
        {"start_ts": 0, "end_ts": 100},
        {"start_ts": 200, "end_ts": 300},
        {"start_ts": 400, "end_ts": 500},
    ]
    v = s_mod._avg_off_time(cycles)
    assert v == 100.0


def test_safe_float_bool_none():
    assert s_mod._safe_float(True) is None
    assert s_mod._safe_float(None) is None
    assert s_mod._safe_float("junk") is None
    assert s_mod._safe_float(5) == 5.0


def test_attrs_current_cycle_idle():
    s = MagicMock(state="idle", cycle_start_ts=0.0, attrs={})
    out = s_mod._attrs_current_cycle(s, MagicMock())
    assert out["duration_min"] is None
    assert out["dt_k"] is None
    assert out["rps"] is None


def test_attrs_source_health_no_success():
    s = MagicMock(last_success_ts=0.0, last_sample_ts=0.0,
                  missing_attrs=[], errors_total=0)
    out = s_mod._attrs_source_health(s, MagicMock())
    assert out["is_stale"] is False
    assert out["missing_attrs_count"] == 0


def test_attrs_stooklijn_empty():
    s = MagicMock(stooklijn_advies={})
    out = s_mod._attrs_stooklijn(s, MagicMock())
    assert out["samples"] is None
    assert out["buckets"] == {}


def test_attrs_cop_today_empty():
    s = MagicMock(cop_today={})
    out = s_mod._attrs_cop_today(s, MagicMock())
    assert out["samples_today"] is None


def test_attrs_learned_no_adaptive():
    s = MagicMock(mode="heating")
    c = MagicMock()
    c.adaptive.learn_good_off_min.return_value = 20
    c.adaptive.learn_target_cycles_per_day.return_value = 8
    c.options.get.return_value = False
    out = s_mod._attrs_learned(s, c)
    assert out["good_off_min"] == 20
    assert out["adaptive_enabled"] is False


def test_attrs_last_cycle_empty():
    s = MagicMock(cluster_id=None)
    c = MagicMock()
    c.store.last_cycle.return_value = None
    out = s_mod._attrs_last_cycle(s, c)
    assert out["duration_min"] is None
    assert out["cluster"] == "unknown"


def test_cluster_label_helper():
    s = MagicMock(cluster_id=5)
    c = MagicMock()
    c.cluster_label.return_value = "normal"
    assert s_mod._cluster_label(s, c) == "normal"


def test_cluster_label_none():
    s = MagicMock(cluster_id=None)
    c = MagicMock()
    assert s_mod._cluster_label(s, c) == "unknown"


def test_cluster_label_exception():
    s = MagicMock(cluster_id=5)
    c = MagicMock()
    c.cluster_label.side_effect = RuntimeError("x")
    assert s_mod._cluster_label(s, c) == "unknown"


# ────────────────────────────────────────────────────────────
# Binary sensor helpers
# ────────────────────────────────────────────────────────────

def test_buh_step_zero():
    s = MagicMock(attrs={})
    assert bs_mod._buh_step(s, None) == 0


def test_buh_step1():
    s = MagicMock(attrs={"BUH Step1": True})
    assert bs_mod._buh_step(s, None) == 1


def test_buh_step2():
    s = MagicMock(attrs={"BUH Step1": True, "BUH Step2": True})
    assert bs_mod._buh_step(s, None) == 2


def test_buh_active_true():
    s = MagicMock(attrs={"BUH Step1": True})
    assert bs_mod._is_buh_active(s, None) is True


def test_buh_active_false():
    s = MagicMock(attrs={})
    assert bs_mod._is_buh_active(s, None) is False


def test_buh_attrs_returns_step():
    s = MagicMock(attrs={"BUH Step2": True})
    out = bs_mod._buh_attrs(s, None)
    assert out == {"step": 2}


def test_attr_on_string_forms():
    assert bs_mod._attr_on({"x": "ON"}, "x") is True
    assert bs_mod._attr_on({"x": "on"}, "x") is True
    assert bs_mod._attr_on({"x": "OFF"}, "x") is False
    assert bs_mod._attr_on({"x": 1}, "x") is False
    assert bs_mod._attr_on({}, "x") is False


def test_attr_is_mode_case_insensitive():
    assert bs_mod._attr_is_mode({"m": "DHW"}, "m", "dhw") is True
    assert bs_mod._attr_is_mode({"m": "heating"}, "m", "heating") is True
    assert bs_mod._attr_is_mode({"m": 123}, "m", "dhw") is False


def test_is_dhw_active_3way_valve_fallback():
    s = MagicMock(attrs={"3way valve(On:DHW_Off:Space)": "ON"})
    c = MagicMock()
    assert bs_mod._is_dhw_active(s, c) is True


def test_is_dhw_active_iu_mode():
    s = MagicMock(attrs={"I/U operation mode": "DHW"})
    c = MagicMock()
    assert bs_mod._is_dhw_active(s, c) is True


def test_is_dhw_active_neither():
    s = MagicMock(attrs={})
    c = MagicMock()
    assert bs_mod._is_dhw_active(s, c) is False


def test_is_short_run_no_last_cycle():
    s = MagicMock()
    c = MagicMock()
    c.store.last_cycle.return_value = None
    assert bs_mod._is_short_run(s, c) is False


def test_is_short_run_non_numeric_duration():
    s = MagicMock()
    c = MagicMock()
    c.store.last_cycle.return_value = {"duration_s": "junk"}
    assert bs_mod._is_short_run(s, c) is False


def test_is_short_off_none():
    s = MagicMock()
    c = MagicMock()
    c.store.off_time_since_last.return_value = None
    assert bs_mod._is_short_off(s, c) is False


def test_is_source_stale_no_timestamp():
    s = MagicMock(last_success_ts=0.0)
    c = MagicMock()
    assert bs_mod._is_source_stale(s, c) is False


def test_binary_sensor_extra_state_attributes_no_attr_fn():
    b = object.__new__(bs_mod.DaikinCycleMLBinarySensor)
    b._attr_fn = None
    b._key = "x"
    b.coordinator = MagicMock()
    b.coordinator.data = MagicMock()
    assert b.extra_state_attributes is None


def test_sensor_extra_state_attributes_no_attr_fn():
    s = object.__new__(s_mod.DaikinCycleMLSensor)
    s._attr_fn = None
    s._key = "x"
    s.coordinator = MagicMock()
    s.coordinator.data = MagicMock()
    assert s.extra_state_attributes is None
