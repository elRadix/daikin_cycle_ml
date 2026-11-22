"""#339: diagnostics fields that were empty in every diagnostics file.

The v1.29.1 file of the corpus still showed adaptive.thresholds {},
detector {state, mode, dhw_present}, buh.step null,
cop_analysis.bucket_edges null and source_resolution {} (monolithic and
individual sources), and no feature vector. Each field now comes from where
the integration actually keeps the value; the helpers that were excluded from
coverage (# pragma: no cover) are tested here instead.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.diagnostics import (
    _adaptive_summary,
    _baseline_summary,
    _bucket_edges,
    _buh_snapshot,
    _cluster_summary,
    _cop_summary,
    _db_extra,
    _detector_snapshot,
    _features_db,
    _safe_size,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import CycleDetector
from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import AdaptiveThresholds
from custom_components.daikin_cycle_ml.ml.features import FEATURE_NAMES
from custom_components.daikin_cycle_ml.storage.db import CycleDB
from tests.test_435_no_dhw_detection import ATTRS_435, SRC, _entry
from tests.test_db import _rec

CORPUS = Path(__file__).parent / "fixtures/diagnostics/erla11dav3_1_29_1_855f04b147_202611220955.json"


def test_the_corpus_file_shows_the_gaps_this_fixes():
    d = json.loads(CORPUS.read_text())
    assert d["adaptive"]["thresholds"] == {} and d["buh"] == {"step": None}
    assert d["source_resolution"] == {} and "rps_threshold" not in d["detector"]


# ---------- A1 adaptive thresholds per mode ----------

def test_adaptive_thresholds_per_mode_with_samples():
    ad = AdaptiveThresholds(min_samples=3)
    for v in (30, 40, 50, 60):
        ad.observe_cycle("heating", v * 60, 1200.0)
    coord = MagicMock(adaptive=ad, options={"adaptive_thresholds_enabled": True})
    out = _adaptive_summary(coord)
    assert out["enabled"] is True and set(out["thresholds"]) == set(out["modes"])
    for m, th in out["thresholds"].items():
        assert set(th["samples"]) == {"run", "off", "days"}, m


def test_adaptive_none_and_failure():
    assert _adaptive_summary(MagicMock(adaptive=None)) == {}
    bad = MagicMock()
    bad.total_samples.side_effect = RuntimeError("x")
    out = _adaptive_summary(MagicMock(adaptive=bad))
    assert out == {"total_samples": 0, "modes": []}


# ---------- A2 feature vector from the database ----------

@pytest.fixture
async def db(tmp_path):
    d = CycleDB(tmp_path / "f.db")
    await d.async_open()
    await d.async_initialize()
    try:
        yield d
    finally:
        await d.async_close()


async def test_latest_feature_vector_from_the_database(db):
    assert await db.async_get_latest_feature_vector() is None
    ids = [await db.async_insert_cycle(_rec(1000.0 + i * 3600)) for i in range(3)]
    await db.async_insert_features(ids[0], [1.0] * len(FEATURE_NAMES))
    await db.async_insert_features(ids[1], [2.0] * len(FEATURE_NAMES))
    row = await db.async_get_latest_feature_vector()
    assert row == {"cycle_id": ids[1], "vector": [2.0] * len(FEATURE_NAMES)}
    out = await _features_db(MagicMock(db=db))
    assert out["last_cycle_id"] == ids[1] and out["names"] == list(FEATURE_NAMES)
    conn = db._require()
    await conn.execute("INSERT OR REPLACE INTO features (cycle_id, vector_json) VALUES (?, 'not json')", (ids[2],))
    await conn.commit()
    assert await db.async_get_latest_feature_vector() is None


async def test_feature_vector_falls_back_to_the_store():
    store = MagicMock()
    store.last_cycle.return_value = {"id": 3, "feature_vector": [1.0]}
    broken = MagicMock(is_open=True)
    broken.async_get_latest_feature_vector = AsyncMock(side_effect=RuntimeError("locked"))
    assert (await _features_db(MagicMock(db=broken, store=store)))["last_cycle_id"] == 3
    closed = MagicMock(is_open=False)
    assert (await _features_db(MagicMock(db=closed, store=store)))["vector"] == [1.0]


# ---------- A3 detector ----------

def test_detector_shows_its_real_fields():
    det = CycleDetector({"compressor_rps_threshold": 12})
    det._start_ts = 1000.0          # a running cycle, as restore_from_dict leaves it
    out = _detector_snapshot(MagicMock(detector=det))
    assert out["rps_threshold"] == 12 and out["start_ts"] == 1000.0 and out["run_duration_s"] > 0
    assert {"pending_mode", "continued", "defrost_hold_s", "dhw_present"} <= set(out)

    class Dated:
        _state = "idle"
        _start_ts = __import__("datetime").datetime(2026, 11, 22, 8, 0)
    assert _detector_snapshot(MagicMock(detector=Dated()))["start_ts"] == "2026-11-22T08:00:00"
    assert _detector_snapshot(MagicMock(detector=object()))["missing"] is True


# ---------- A4 backup heater step ----------

@pytest.mark.parametrize(("s1", "s2", "step"), [
    ("OFF", "OFF", 0), ("ON", "OFF", 1), ("ON", "ON", 2), ("OFF", "ON", 2), (1, 0, 1), (0.0, 1.0, 2), (None, None, None),
    ([], "OFF", 0),
])
def test_buh_step_from_the_source(s1, s2, step):
    attrs = {k: v for k, v in (("BUH Step1", s1), ("BUH Step2", s2)) if v is not None}
    out = _buh_snapshot(MagicMock(last_attrs=attrs, _buh_step1_s=120.0, _buh_step2_s=0.0))
    assert out == {"step": step, "step1_s": 120.0, "step2_s": 0.0}
    assert _buh_snapshot(MagicMock(last_attrs=None, _buh_step1_s=None, _buh_step2_s=None))["step"] is None


# ---------- A5 bucket edges ----------

def test_bucket_edges_from_the_keys():
    assert _bucket_edges({"-10-": {}, "-2-0": {}, "0-2": {}, "20+": {}}) == [None, -10.0, -2.0, 0.0, 2.0, 20.0, None]
    assert _bucket_edges({"4-6": {}}) == [4.0, 6.0]
    assert _bucket_edges({}) is None and _bucket_edges(None) is None and _bucket_edges({"x": {}}) is None


async def test_cop_summary_carries_the_edges():
    coord = MagicMock(_stooklijn_cache={"state": "keep", "buckets": {"0-2": {}, "2-4": {}}}, _cop_today_cache={})
    coord.db.async_count_cop_samples = AsyncMock(return_value=5)
    out = await _cop_summary(coord)
    assert out["bucket_edges"] == [0.0, 2.0, 4.0] and out["total_samples"] == 5


# ---------- A6 source resolution for every source type ----------

async def test_source_resolution_for_a_monolithic_source(hass):
    coord = DaikinCycleMLCoordinator(hass, _entry(hass))
    hass.states.async_set(SRC, "unknown", ATTRS_435)
    await coord._async_update_data()
    r = coord._source_resolution
    assert r["mode"] == "monolithic" and r["entity"] == SRC and r["attributes"] > 20 and r["missing_required"] == 0


# ---------- formerly "no cover" helpers ----------

async def test_db_extra_paths():
    assert await _db_extra(None) == {}
    db = MagicMock(is_open=True)
    db.async_daily_summary = AsyncMock(side_effect=RuntimeError("x"))
    db.async_get_model_state = AsyncMock(side_effect=[1.0, RuntimeError("y"), {"b": 1}])
    out = await _db_extra(db)
    assert "daily_summary" not in out and out["last_maintenance_ts"] == 1.0 and "kmeans_state" not in out


def test_baseline_summary_paths():
    assert _baseline_summary(MagicMock(baseline=None)) == {}
    v2 = MagicMock()
    v2.summary.return_value = {"modes": {"heating": {"n": 3}}}
    v2.total_samples.return_value = 3
    assert _baseline_summary(MagicMock(baseline=v2))["total_samples"] == 3
    v2.summary.side_effect = RuntimeError("x")
    assert _baseline_summary(MagicMock(baseline=v2))["total_samples"] == 0

    class Old:
        def total_samples(self):
            return 4
    assert _baseline_summary(MagicMock(baseline=Old()))["total_samples"] == 4

    class Broken:
        def total_samples(self):
            raise RuntimeError("x")
    assert _baseline_summary(MagicMock(baseline=Broken()))["total_samples"] == 0


async def test_cluster_summary_paths():
    coord = MagicMock(_kmeans_centroids=[[1.0, 2.0]], _cluster_labels={0: "normal"}, _kmeans_stale={"heating": True})
    coord.db.async_count_by_cluster = AsyncMock(return_value={0: 5})
    out = await _cluster_summary(coord)
    assert out["counts"] == {"0": 5} and out["stale"] == {"heating": True} and out["centroids"] == 1
    coord.db.async_count_by_cluster = AsyncMock(side_effect=RuntimeError("x"))
    assert (await _cluster_summary(coord))["counts"] == {}


def test_safe_size(tmp_path):
    f = tmp_path / "a.db"
    f.write_bytes(b"1234")
    assert _safe_size(f) == 4 and _safe_size(tmp_path / "missing.db") == 0
