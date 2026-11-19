"""#415: prod-1 v1.23.3 diagnostics (2026-11-19 06:42) + SQL + log.

1. off_s held the pause plus the cycle's own run time (cycle 430:
   1 170 + 17 987 = 19 158 s), so short_off never fired and good_off
   learned 130 min.
2. Two cop_hourly rows (n 1, mean 16.486 / 16.084) out of step with their
   10 normal samples survived v30.
3. Heating-curve tracking compared the live setpoint (28.6) with the last
   stored sample (36.9, previous run's stop ramp).
4. cop_vs_datasheet_low fired on run start / stop ramps (per tick).
5. Week / month p10 / p90 were min / max of the hours.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    COP_DS_MIN_SAMPLES,
    COP_DS_WINDOW_S,
    OFF_RELEARN_MARKER,
    STEADY_RUN_S,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    _window_mean,
    score_and_count,
)
from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample,
    analyze_stooklijn,
)
from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    AdaptiveThresholds,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB
from custom_components.daikin_cycle_ml.storage.store import CycleStore

# prod-1 cycles 429 / 430 (SQL 2026-11-19)
END_429 = 1795045406.0          # 00:43:26
START_430 = 1795046576.0        # 01:02:56
END_430 = 1795064563.0          # 06:02:43, duration 17 987 s

# --- 1. off_s -------------------------------------------------------------------


def _store_with_previous(end_ts: float) -> CycleStore:
    s = CycleStore(maxlen=10)
    s.add_cycle({"start_ts": end_ts - 4140, "end_ts": end_ts,
                 "duration_s": 4140, "mode": "heating"})
    return s


def test_prod1_cycle_430_off_s_is_the_pause():
    store = _store_with_previous(END_429)
    rec = {"start_ts": START_430, "end_ts": END_430,
           "duration_s": END_430 - START_430, "mode": "heating"}
    score_and_count(rec, {}, store, END_430)
    assert rec["off_s"] == pytest.approx(1170.0)       # was 19 158


def test_short_pause_counts_as_short_off_despite_long_run():
    store = _store_with_previous(1000.0)
    rec = {"start_ts": 1120.0, "end_ts": 1120.0 + 7200, "duration_s": 7200,
           "mode": "heating"}
    score_and_count(rec, {"short_off_threshold_min": 5}, store, 1120.0 + 7200)
    assert rec["off_s"] == 120.0
    assert store.get("short_offs_today") == 1


@pytest.mark.parametrize("start", [None, True, "x"])
def test_off_s_without_start_falls_back_to_close_time(start):
    store = _store_with_previous(1000.0)
    rec = {"start_ts": start, "duration_s": 60, "mode": "heating"}
    score_and_count(rec, {}, store, 1600.0)
    assert rec["off_s"] == 600.0


def test_replace_off_samples():
    at = AdaptiveThresholds(min_samples=2)
    at.observe_cycle("heating", 3600, 19158)               # inflated legacy value
    kept = at.replace_off_samples({
        "heating": [1170.0, 600.0, -5.0, True, "x"], "dhw": [], "cooling": [60.0],
    })
    assert kept == 3
    assert at.to_dict()["off_min"] == {"heating": [19.5, 10.0], "cooling": [1.0]}
    assert at.learn_good_off_min("heating") == 15


async def _mk_db(tmp_path) -> CycleDB:
    db = CycleDB(str(tmp_path / "t415.db"))
    await db.async_open()
    await db.async_initialize()
    await db.async_ensure_cop_samples_table()
    await db.async_create_cop_hourly_v14()
    return db


async def _close(db: CycleDB) -> None:
    await db.async_close()
    await asyncio.sleep(0.05)


async def test_cycle_off_gaps_from_db(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        for st, en, mode, tr in (
            (1000, 2000, "heating", 0),
            (2600, 2700, "heating", 1),          # transient: gap not used
            (3000, 9000, "dhw", 0),              # gap 300 s after the transient
            (9100, 9200, "heating", 0),
            (9150, 9300, "heating", 0),          # overlaps: negative gap skipped
        ):
            await db.async_insert_cycle({
                "start_ts": st, "end_ts": en, "duration_s": en - st,
                "mode": mode, "quality_score": 80, "is_transient": tr,
            })
        assert await db.async_cycle_off_gaps() == {"dhw": [300.0], "heating": [100.0]}
    finally:
        await _close(db)


def _relearn_coord(db: Any) -> DaikinCycleMLCoordinator:
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c.adaptive = AdaptiveThresholds(min_samples=1)
    c.adaptive.observe_cycle("heating", 3600, 19158)
    return c


async def test_relearn_once(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        for st, en in ((1000, 2000), (3170, 5000)):
            await db.async_insert_cycle({
                "start_ts": st, "end_ts": en, "duration_s": en - st,
                "mode": "heating", "quality_score": 80, "is_transient": 0,
            })
        c = _relearn_coord(db)
        assert await c._maybe_relearn_off_samples() is True
        assert c.adaptive.to_dict()["off_min"] == {"heating": [1170 / 60.0]}
        assert (await db.async_get_model_state(OFF_RELEARN_MARKER))["samples"] == 1
        stored = await db.async_get_model_state("adaptive_thresholds")
        assert stored["off_min"] == {"heating": [1170 / 60.0]}
        assert await c._maybe_relearn_off_samples() is False   # marker set
    finally:
        await _close(db)


async def test_relearn_without_db_or_on_error():
    c = _relearn_coord(None)
    assert await c._maybe_relearn_off_samples() is False
    db = SimpleNamespace(
        async_get_model_state=AsyncMock(return_value=None),
        async_cycle_off_gaps=AsyncMock(side_effect=RuntimeError("x")),
    )
    c = _relearn_coord(db)
    assert await c._maybe_relearn_off_samples() is False
    assert c.adaptive.to_dict()["off_min"] == {"heating": [19158 / 60.0]}


# --- 2. v31 + read guard + weighted p10/p90 --------------------------------------

H = 498008                       # 2026-10-24 10:00 (prod-1)


async def _hourly_row(db: CycleDB, hour: int, mode: str, n: int, mean: float,
                      p10: float | None = None, p90: float | None = None) -> None:
    await db._require().execute(
        "INSERT INTO cop_hourly (ts_hour, mode, n_samples, cop_mean, cop_p10, "
        "cop_p50, cop_p90, cop_std, updated_ts) VALUES (?,?,?,?,?,?,?,?,?)",
        (hour, mode, n, mean, mean if p10 is None else p10, mean,
         mean if p90 is None else p90, 0.0, 1.0),
    )


async def _sample(db: CycleDB, ts: float, cop: float, mode: str = "heating") -> None:
    await db._require().execute(
        "INSERT INTO cop_samples (ts, cop, mode, source, is_transition_artifact) "
        "VALUES (?, ?, ?, 'interval', 0)", (ts, cop, mode),
    )


async def _rows(db: CycleDB) -> dict[tuple[int, str], tuple[int, float]]:
    async with db._require().execute(
        "SELECT ts_hour, mode, n_samples, cop_mean FROM cop_hourly"
    ) as cur:
        return {(int(r[0]), r[1]): (int(r[2]), float(r[3]))
                for r in await cur.fetchall()}


async def test_v31_rebuilds_prod1_stale_hours(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        cops = [4.331, 4.2, 4.1, 4.0, 4.3, 4.25, 4.15, 4.05, 4.3, 4.2]
        for i, cop in enumerate(cops):                      # 10 normal samples
            await _sample(db, H * 3600 + 60 + i * 300, cop)
        await _hourly_row(db, H, "heating", 1, 16.486)      # stale row (prod-1)
        await _hourly_row(db, H + 1, "heating", 3, 5.0)     # no samples left
        await _sample(db, (H + 2) * 3600 + 60, 5.0)         # consistent row
        await _hourly_row(db, H + 2, "heating", 1, 5.0)
        await db._require().commit()

        stats = await db.async_migrate_to_v31()
        assert stats == {"hours_rebuilt": 1, "rows_deleted": 1, "completed": True}
        rows = await _rows(db)
        assert rows[(H, "heating")][0] == 10
        assert rows[(H, "heating")][1] == pytest.approx(sum(cops) / 10)
        assert (H + 1, "heating") not in rows
        assert rows[(H + 2, "heating")] == (1, 5.0)
        assert await db.async_migrate_to_v31() == {"skipped": 1}
    finally:
        await _close(db)


async def test_v31_empty_db(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        assert await db.async_migrate_to_v31() == {
            "hours_rebuilt": 0, "rows_deleted": 0, "completed": True}
    finally:
        await _close(db)


async def test_read_guard_skips_out_of_range_hours(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        await _hourly_row(db, H, "heating", 1, 16.486)
        await _hourly_row(db, H + 1, "heating", 10, 4.2)
        await _hourly_row(db, H + 2, "dhw", 1, 0.5)
        await _hourly_row(db, H + 3, "cooling", 5, 0.8)   # no floor for cooling
        await db._require().commit()
        got = await db.async_query_cop_hourly(since_ts=0.0)
        assert [(r["ts_hour"], r["mode"]) for r in got] == [
            (H + 1, "heating"), (H + 3, "cooling")]
    finally:
        await _close(db)


async def test_weighted_p10_p90_ignore_single_sample_hour(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        for i in range(10):
            await _hourly_row(db, H + i, "heating", 10, 6.0, p10=5.0, p90=7.0)
        await _hourly_row(db, H + 10, "heating", 1, 10.5, p10=10.5, p90=10.5)
        await db._require().commit()
        st = await db.async_cop_hourly_stats(since_ts=0.0)
        assert st["cop_max"] == 10.5
        assert st["cop_p90"] == pytest.approx((7.0 * 100 + 10.5) / 101)
        assert st["cop_p10"] == pytest.approx((5.0 * 100 + 10.5) / 101)
        assert st["cop_p10"] <= st["cop_mean"] <= st["cop_p90"] < st["cop_max"]
    finally:
        await _close(db)


# --- 3. curve tracking with same-moment values ----------------------------------


def _samples(lwt_last: float) -> list[CopSample]:
    now = time.time()
    out = [
        CopSample(cop=5.5, lwt=30.0, outdoor=9.0, flow_lmin=18, defrost=False,
                  data_quality="Good", power_stable=True, mode="heating",
                  ts=now - 3600 + i)
        for i in range(20)
    ]
    out.append(CopSample(cop=4.8, lwt=lwt_last, outdoor=9.0, flow_lmin=18,
                         defrost=False, data_quality="Good", power_stable=True,
                         mode="heating", ts=now - 60))
    return out


def test_tracking_legacy_uses_last_sample():
    adv = analyze_stooklijn(_samples(36.9), indoor_avg=20.5, setpoint_lwt=28.6)
    assert adv.tracking_error == pytest.approx(-8.3)          # prod-1 06:42


def test_tracking_uses_live_lwt():
    adv = analyze_stooklijn(_samples(36.9), indoor_avg=20.5, setpoint_lwt=28.6,
                            tracking_lwt=29.6)
    assert adv.tracking_error == pytest.approx(-1.0)
    assert adv.reason != "unit_tracking_behind"


def test_no_tracking_judgement_without_steady_live_lwt():
    adv = analyze_stooklijn(_samples(36.9), indoor_avg=20.5, setpoint_lwt=28.6,
                            tracking_lwt=None)
    assert adv.tracking_error is None
    assert adv.reason != "unit_tracking_behind"


R1T = "Leaving water temp. before BUH (R1T)"


def _steady_coord(state="running", mode="heating", age=STEADY_RUN_S + 60,
                  attrs=None) -> DaikinCycleMLCoordinator:
    now = 1_000_000.0
    c = object.__new__(DaikinCycleMLCoordinator)
    c.detector = SimpleNamespace(snapshot=lambda: {
        "state": state, "mode": mode, "start_ts": now - age,
    })
    c.data = SimpleNamespace(attrs={R1T: 29.6, "Defrost Operation": "OFF"}
                             if attrs is None else attrs)
    return c


NOW = 1_000_000.0


def test_steady_live_lwt():
    assert _steady_coord()._steady_live_lwt(NOW) == 29.6


@pytest.mark.parametrize("kw", [
    {"state": "idle"}, {"mode": "dhw"}, {"age": 300},
    {"attrs": {R1T: 29.6, "Defrost Operation": "ON"}},
])
def test_not_steady_gives_none(kw):
    assert _steady_coord(**kw)._steady_live_lwt(NOW) is None


def test_steady_start_not_a_number():
    c = _steady_coord()
    c.detector = SimpleNamespace(snapshot=lambda: {
        "state": "running", "mode": "heating", "start_ts": None})
    assert c._steady_live_lwt(NOW) is None


def test_steady_live_lwt_error_is_none():
    c = _steady_coord()
    c.detector = SimpleNamespace(snapshot=lambda: 1 / 0)
    assert c._steady_live_lwt(NOW) is None


# --- 4. datasheet alert on a rolling steady mean --------------------------------


def test_track_cop_ds_only_while_steady():
    c = _steady_coord()
    c._track_cop_ds_pct(NOW, -30.0)                 # steady: kept
    c._track_cop_ds_pct(NOW + 1, None)              # no value
    c._track_cop_ds_pct(NOW + 2, True)              # not a number
    assert list(c._cop_ds_window) == [(NOW, -30.0)]
    ramp = _steady_coord(age=120)                   # run start ramp
    ramp._track_cop_ds_pct(NOW, -45.0)
    assert list(ramp._cop_ds_window) == []


def test_track_cop_ds_prunes_old_and_survives_errors():
    c = _steady_coord()
    c._cop_ds_window = deque([(NOW - COP_DS_WINDOW_S - 1, -50.0)])
    c._track_cop_ds_pct(NOW, -5.0)
    assert list(c._cop_ds_window) == [(NOW, -5.0)]
    c.detector = SimpleNamespace(snapshot=lambda: 1 / 0)
    c._track_cop_ds_pct(NOW + 1, -5.0)
    assert list(c._cop_ds_window) == [(NOW, -5.0)]


def test_window_mean():
    win = deque((float(i), -6.0) for i in range(COP_DS_MIN_SAMPLES))
    assert _window_mean(win, COP_DS_MIN_SAMPLES) == -6.0
    assert _window_mean(deque(list(win)[:-1]), COP_DS_MIN_SAMPLES) is None
    assert _window_mean(None, COP_DS_MIN_SAMPLES) is None


def test_prod1_ramps_do_not_fire_steady_hour_does():
    # prod-1: steady -6 % with start / stop ramps far below
    c = _steady_coord()
    c._cop_ds_window = deque(
        [(float(i), -6.0) for i in range(110)] + [(200.0 + i, -40.0) for i in range(10)]
    )
    assert _window_mean(c._cop_ds_window, COP_DS_MIN_SAMPLES) > -10.0
    low = deque((float(i), -14.0) for i in range(60))
    assert _window_mean(low, COP_DS_MIN_SAMPLES) < -10.0
