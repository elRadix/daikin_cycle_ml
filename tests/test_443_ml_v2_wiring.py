"""#443 ML v2 wiring: coordinator scoring, relearn / retrain, DB repair.

Uses a real CycleDB (tmp file) so the relearn reads what production
writes: cycles + features (LWT) + cop_samples with boiler flags.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_LEAVING_WATER_AFTER_BUH,
    ML_V2_RELEARN_MARKER,
)
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import AdaptiveThresholds
from custom_components.daikin_cycle_ml.ml.behaviour_baseline import (
    ML_VERSION,
    BehaviourBaseline,
)
from custom_components.daikin_cycle_ml.ml.features import FEATURE_NAMES
from custom_components.daikin_cycle_ml.services import _do_recompute_baseline
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _coord(db=None, options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c.db = db
    c.baseline = BehaviourBaseline()
    c.adaptive = AdaptiveThresholds()
    c._kmeans_v2 = {}
    c._kmeans_centroids = []
    c._cluster_labels = {}
    c.data = None
    return c


def _rec(start, dur_min=45.0, mode="heating", **kw):
    r = {"start_ts": start, "end_ts": start + dur_min * 60, "duration_s": int(dur_min * 60),
         "mode": mode, "dT_max": 6.0, "dT_avg": 5.0, "rps_max": 50, "rps_avg": 40.0,
         "outdoor_temp": 5.0, "buh_used": 0, "defrost_used": 0, "cop_avg": 4.0,
         "thermal_kw_avg": 6.0, "is_transient": 0}
    r.update(kw)
    return r


@pytest.fixture
async def db(tmp_path):
    d = CycleDB(str(tmp_path / "ml.db"))
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def _seed(db, n=60, now=None):
    now = now or time.time()
    lwt_i = FEATURE_NAMES.index("lwt_avg")
    ids = []
    for i in range(n):
        start = now - 20 * 86400 + i * 7200
        dur = 10.0 if i % 10 == 0 else 45.0 + (i % 7)
        rec = _rec(start, dur)
        cid = await db.async_insert_cycle(rec)
        vec = [0.0] * len(FEATURE_NAMES)
        vec[lwt_i] = 35.0
        await db.async_insert_features(cid, vec)
        ids.append(cid)
    for j in range(15):   # DHW + one transient + one co-fire
        await db.async_insert_cycle(_rec(now - 19 * 86400 + j * 7300, 35.0, mode="dhw"))
    await db.async_insert_cycle(_rec(now - 5 * 86400, 1.0, is_transient=1))
    await db.async_insert_cycle(_rec(now - 4.5 * 86400, 0.0))       # no run length
    await db.async_insert_cycle(_rec(now - 4 * 86400, 50.0, boiler_contribution_samples=4,
                                     cop_avg=7.5))
    return ids


# ---------- coordinator scoring ----------

def test_score_skips_transient_and_co_fire():
    c = _coord()
    r = c._ml_score_cycle(_rec(0, is_transient=1), "heating", cop_avg=4.0, lwt_avg=None)
    assert r.details["reason"] == "transient"
    r = c._ml_score_cycle(_rec(0, boiler_contribution_samples=2), "heating",
                          cop_avg=9.0, lwt_avg=None)
    assert r.details["reason"] == "co_fire"
    assert c.baseline.total_samples() == 0


def test_score_drops_duration_of_short_runs_and_segments():
    c = _coord(options={"short_run_threshold_min": 20})
    c._ml_score_cycle(_rec(0, 10.0), "heating", cop_avg=4.0, lwt_avg=35.0)
    g = c.baseline._groups["heating"]
    assert "duration_s" not in g and g["lwt_avg"].n == 1
    c._ml_score_cycle(_rec(0, 60.0), "heating", cop_avg=4.0, lwt_avg=None, segment=True)
    assert "duration_s" not in c.baseline._groups["heating"]
    c._ml_score_cycle(_rec(0, 60.0), "heating", cop_avg=4.0, lwt_avg=None)
    assert c.baseline._groups["heating"]["duration_s"].n == 1


def test_accumulate_skips_cop_on_co_fire_and_reads_espaltherma_lwt():
    c = _coord()
    c.detector = SimpleNamespace(state="running")
    c.indoor_temp_entity = None
    c._cycle_lwt_sum = c._cycle_indoor_sum = 0.0
    c._cycle_lwt_count = c._cycle_indoor_count = 0
    c._cycle_cop_w_sum = c._cycle_cop_weight_sum = c._cycle_cop_sq_w_sum = 0.0
    c._cycle_cop_count = 0
    c._read_cop = lambda: 4.0
    c._read_power_w = lambda: 1000.0
    attrs = {ATTR_LEAVING_WATER_AFTER_BUH: 36.5}
    c._accumulate_cycle_samples(attrs, boiler_on=True)
    assert c._cycle_lwt_count == 1 and c._cycle_lwt_sum == 36.5
    assert c._cycle_cop_count == 0
    c._accumulate_cycle_samples(attrs)
    assert c._cycle_cop_count == 1


def test_assign_cluster_none_without_model_or_for_transients():
    c = _coord()
    vals = {"duration_s": 2700.0}
    assert c._assign_cluster("heating", vals) is None
    c._kmeans_v2 = {"modes": {"heating": {"dims": ["duration_s"], "mu": [3.8], "sd": [0.2],
                                          "centroids": [[0.0]], "labels": ["normal"],
                                          "id_base": 0}}}
    assert c._assign_cluster("heating", vals) == 0
    assert c._assign_cluster("heating", vals, record={"is_transient": 1}) is None
    assert c._assign_cluster("heating", vals,
                             record={"boiler_contribution_samples": 1}) is None


def test_short_run_min_fallback():
    assert _coord(options={"short_run_threshold_min": "x"})._short_run_min() == 20.0
    assert _coord(options={"short_run_threshold_min": 25})._short_run_min() == 25.0


# ---------- relearn / retrain on a real DB ----------

async def test_relearn_replays_cycles_and_retrains(db):
    await _seed(db)
    c = _coord(db)
    assert await c._maybe_ml_v2_relearn() is True
    marker = await db.async_get_model_state(ML_V2_RELEARN_MARKER)
    assert marker["completed"] is True and marker["ml_version"] == ML_VERSION
    assert marker["kmeans"]["ok"] is True
    assert marker["repair"]["cycles"] == 1
    # transient + co-fire not learned; heating + dhw are
    assert c.baseline.modes() == ["dhw", "heating"]
    assert c.baseline._groups["heating"]["lwt_avg"].n == 60   # LWT from features
    state = await db.async_get_model_state("baseline_state")
    assert state["type"] == "behaviour"
    km = await db.async_get_model_state("kmeans_state")
    assert km["version"] == 2 and km["labels"] is None
    counts = await db.async_count_by_cluster()
    rows = await db.async_fetch_cycles_for_relearn(days=90)
    scored = [r for r in rows if not r["is_transient"] and not r["boiler_contribution_samples"]
              and r["duration_s"]]
    # transient, co-fire and the run without a length get no cluster
    assert sum(counts.values()) == len(scored) == len(rows) - 3
    assert len(c.adaptive.to_dict()["run_min"]["heating"]) == 61   # co-fire run kept
    # second start: marker current -> nothing to do
    assert await c._maybe_ml_v2_relearn() is False
    # a v1 state restored over it (downgrade) -> relearn again
    c.baseline = BehaviourBaseline.from_dict({"dim": 12})
    assert await c._maybe_ml_v2_relearn() is True


async def test_relearn_without_db_or_on_error():
    assert await _coord()._maybe_ml_v2_relearn() is False
    bad = MagicMock()
    bad.async_get_model_state = AsyncMock(side_effect=RuntimeError("locked"))
    assert await _coord(bad)._maybe_ml_v2_relearn() is False
    assert (await _coord().async_relearn_models()) == {"samples": 0}


async def test_load_kmeans_state_versions(db):
    c = _coord(db)
    assert await c._load_kmeans_state() is False                 # nothing stored
    await db.async_set_model_state("kmeans_state", {"centroids": [[1.0] * 12], "modes": {}})
    assert await c._load_kmeans_state() is False                 # v1 payload
    await db.async_set_model_state("kmeans_state", {"modes": {"heating": {}}, "version": 1})
    assert await c._load_kmeans_state() is False
    await _seed(db)
    await c.async_run_kmeans()
    c2 = _coord(db)
    assert await c2._load_kmeans_state() is True
    assert c2._cluster_labels and c2._kmeans_centroids
    assert await _coord()._load_kmeans_state() is False
    broken = MagicMock()
    broken.async_get_model_state = AsyncMock(side_effect=RuntimeError)
    assert await _coord(broken)._load_kmeans_state() is False


async def test_run_kmeans_failure_paths(db, monkeypatch):
    assert (await _coord().async_run_kmeans())["reason"] == "no_db"
    c = _coord(db)
    assert (await c.async_run_kmeans())["reason"] == "too_few"
    monkeypatch.setattr(db, "async_fetch_cycles_for_relearn",
                        AsyncMock(side_effect=RuntimeError("io")))
    assert (await c.async_run_kmeans())["reason"] == "fetch_failed"
    from custom_components.daikin_cycle_ml import coordinator as co
    monkeypatch.setattr(db, "async_fetch_cycles_for_relearn", AsyncMock(return_value=[]))
    monkeypatch.setattr(co.kmeans_v2, "train", MagicMock(side_effect=ValueError))
    assert (await c.async_run_kmeans())["reason"] == "kmeans_failed"


async def test_reassign_clusters_edges(db):
    assert await _coord()._reassign_clusters([{"id": 1}]) == 0
    assert await _coord(db)._reassign_clusters([{"id": None}, {"id": "2"}]) == 0


# ---------- DB helpers ----------

async def test_fetch_for_relearn_lwt_parsing(db):
    now = time.time()
    a = await db.async_insert_cycle(_rec(now - 100))
    b = await db.async_insert_cycle(_rec(now - 50000))
    await db.async_insert_cycle(_rec(now - 90000))           # no features row
    await db.async_insert_features(a, [0.0] * len(FEATURE_NAMES))    # lwt 0 = missing
    conn = db._require()
    await conn.execute("INSERT OR REPLACE INTO features VALUES (?, ?)", (b, "not json"))
    await conn.commit()
    rows = await db.async_fetch_cycles_for_relearn(days=2)
    assert [r["lwt_avg"] for r in rows] == [None, None, None]
    assert "_vec" not in rows[0]
    assert await db.async_set_cluster_ids([]) == 0


async def _sample(db, ts, cop, boiler, mode="heating"):
    await db.async_insert_cop_sample({"ts": ts, "cop": cop, "lwt": 35.0, "outdoor": 2.0,
                                      "flow_lmin": 15.0, "mode": mode,
                                      "boiler_active": boiler})


async def test_boiler_samples_kept_out_of_aggregates_and_rebuild(db):
    t0 = 3600.0 * 500000
    for i in range(4):
        await _sample(db, t0 + i * 60, 4.0, False)
        await _sample(db, t0 + 600 + i * 60, 8.0, True)
    avg, n = await db._sample_aggregates(t0, t0 + 3599, mode="heating")
    assert (avg, n) == (4.0, 4)
    await db._rebuild_cop_hourly_for_hours([int(t0 // 3600)])
    conn = db._require()
    async with conn.execute("SELECT n_samples, cop_mean FROM cop_hourly") as cur:
        assert [tuple(r) for r in await cur.fetchall()] == [(4, 4.0)]


async def test_repair_co_fire_cop(db):
    t0 = 3600.0 * 500000
    for i in range(3):
        await _sample(db, t0 + i * 60, 3.0, False)
        await _sample(db, t0 + 300 + i * 60, 9.0, True)
    await _sample(db, t0 + 7200, 9.0, True)                   # an all-boiler hour
    conn = db._require()
    await conn.execute(
        "INSERT INTO cop_hourly (ts_hour, mode, n_samples, cop_mean, updated_ts) "
        "VALUES (?, 'heating', 1, 9.0, 0)",
        (int(t0 // 3600) + 2,))
    await conn.commit()
    mixed = await db.async_insert_cycle(_rec(t0, 10.0, boiler_contribution_samples=3, cop_avg=6.0))
    only = await db.async_insert_cycle(_rec(t0 + 7100, 5.0, boiler_contribution_samples=1,
                                            cop_avg=9.0))
    stats = await db.async_repair_co_fire_cop()
    assert stats == {"hours": 2, "hours_rebuilt": 1, "cycles": 2}
    async with conn.execute("SELECT id, cop_avg FROM cycles ORDER BY id") as cur:
        cops = {r[0]: r[1] for r in await cur.fetchall()}
    assert cops == {mixed: 3.0, only: None}
    async with conn.execute("SELECT ts_hour, cop_mean FROM cop_hourly ORDER BY ts_hour") as cur:
        assert [tuple(r) for r in await cur.fetchall()] == [(int(t0 // 3600), 3.0)]
    assert await db.async_repair_co_fire_cop() == {"hours": 2, "hours_rebuilt": 1, "cycles": 2}


async def test_sample_aggregates_without_boiler_column(tmp_path):
    d = CycleDB(str(tmp_path / "old.db"))
    await d.async_open()
    conn = d._require()
    await conn.execute("DROP TABLE IF EXISTS cop_samples")
    await conn.execute("CREATE TABLE cop_samples (ts REAL, cop REAL, mode TEXT)")
    await conn.execute("INSERT INTO cop_samples VALUES (10, 3.0, 'heating')")
    await conn.commit()
    assert await d._sample_aggregates(0, 20) == (3.0, 1)
    assert d._boiler_col_known is False
    await d.async_close()


# ---------- service ----------

async def test_recompute_baseline_service(db):
    c = _coord(db)
    out = await _do_recompute_baseline(c, 30)
    assert out == {"computed": False, "reason": "no_data", "days": 30, "samples": 0}
    await _seed(db)
    out = await _do_recompute_baseline(c, 30)
    assert out["computed"] is True and out["samples"] >= 60 and out["kmeans"]["ok"]
    c.async_relearn_models = AsyncMock(side_effect=RuntimeError("x"))
    assert (await _do_recompute_baseline(c, 30))["reason"] == "fetch_failed"
    c.baseline = None
    assert (await _do_recompute_baseline(c, 30))["reason"] == "no_baseline"
    assert (await _do_recompute_baseline(_coord(), 30))["reason"] == "no_db"


# ---------- status report ----------

def test_rich_snapshot_reads_espaltherma_labels():
    c = _coord()
    snap = SimpleNamespace(attrs={ATTR_LEAVING_WATER_AFTER_BUH: 38.0})
    assert c._snap_attr(snap, "leaving_water_temp", ATTR_LEAVING_WATER_AFTER_BUH) == 38.0
