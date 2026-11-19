"""#419: quality score on split cycles, runtime check, runs lost on restart.

prod-1 runs 24/7: DHW is a heating <-> DHW split (the compressor never
stops). After #415 the continuing cycle's off_s was ~0 s, which would score
and alert a "short off" on every DHW switch; the segments were "short
runs". quality_today averaged in a live score that penalised a 20 min open
run (closed 90 + live 50 -> 70). Before #417 an HA restart dropped the run
before it (2026-11-18: samples 23:04-23:25, cycle 429 from 23:34:26).
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_COP,
    ATTR_FLOW_SENSOR,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_OPERATION_MODE,
    ATTR_WATER_PUMP_OPERATION,
    STEADY_RUN_S,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
    score_and_count,
)
from custom_components.daikin_cycle_ml.diagnostics import _runtime_check
from custom_components.daikin_cycle_ml.engine import cycle_detector as cd
from custom_components.daikin_cycle_ml.engine.cycle_detector import CycleDetector
from custom_components.daikin_cycle_ml.storage.db import (
    BACKFILL_CHAIN_GAP_S,
    CycleDB,
    _lost_runs,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore
from tests.test_v2_restart_open_cycle_e2e import _full_attrs

# --- 1. split / cap segments -----------------------------------------------------


def _attrs(dhw: bool = False) -> dict[str, Any]:
    a = _full_attrs()
    a[ATTR_INV_FREQUENCY_RPS] = 28.0
    a[ATTR_3WAY_VALVE] = "ON" if dhw else "OFF"
    if dhw:
        a[ATTR_IU_OPERATION_MODE] = a[ATTR_OPERATION_MODE] = "DHW"
    return a


PW = 1500.0


def _off(dhw: bool = False) -> dict[str, Any]:
    a = _attrs(dhw)
    a.update({ATTR_INV_FREQUENCY_RPS: 0.0, ATTR_FLOW_SENSOR: 0.0,
              ATTR_WATER_PUMP_OPERATION: False})
    a.pop(ATTR_COP, None)
    return a


def _split_run() -> tuple[dict, dict]:
    """heating 0..600 s -> DHW (split at 660 s) -> stop at 4000 s."""
    d = CycleDetector({}, dhw_present=True)
    d.update(_attrs(), now=0.0, power_w=PW)
    d.update(_attrs(dhw=True), now=600.0, power_w=PW)   # debounce starts
    heat = d.update(_attrs(dhw=True), now=660.0, power_w=PW)  # split
    dhw = d.update(_off(dhw=True), now=4000.0, power_w=0.0)        # compressor stops
    return heat, dhw


def test_detector_marks_split_and_continuation():
    heat, dhw = _split_run()
    assert heat["ended_by"] == "split" and heat["continued"] is False
    assert dhw["ended_by"] == "stop" and dhw["continued"] is True
    assert dhw["mode"] == "dhw" and dhw["start_ts"] == heat["end_ts"]


def test_split_is_not_a_short_off_or_short_run():
    heat, dhw = _split_run()
    store = CycleStore(maxlen=10)
    opts = {"short_run_threshold_min": 20, "short_off_threshold_min": 5}
    score_and_count(heat, opts, store, heat["end_ts"])
    store.add_cycle(heat)
    score_and_count(dhw, opts, store, dhw["end_ts"])
    assert "off_s" not in dhw                       # no pause before DHW
    assert store.get("short_offs_today") == 0
    assert store.get("short_runs_today") == 0       # 11 min heating segment
    assert heat["quality_score"] == dhw["quality_score"] == 100


def test_real_short_run_and_pause_still_penalised():
    store = CycleStore(maxlen=10)
    store.add_cycle({"start_ts": 0.0, "end_ts": 600.0, "duration_s": 600,
                     "mode": "heating", "ended_by": "stop"})
    rec = {"start_ts": 720.0, "end_ts": 1320.0, "duration_s": 600,
           "mode": "heating", "ended_by": "stop", "continued": False}
    score_and_count(rec, {}, store, 1320.0)
    assert rec["off_s"] == 120.0
    assert store.get("short_offs_today") == store.get("short_runs_today") == 1
    assert rec["quality_score"] == 100 - 30 - 20        # short run + short off


def test_cap_close_continues_next_cycle(monkeypatch):
    monkeypatch.setattr(cd, "MAX_CYCLE_DURATION_S", 3600.0)
    d = CycleDetector({}, dhw_present=True)
    d.update(_attrs(), now=0.0, power_w=PW)
    capped = d.update(_attrs(), now=3700.0, power_w=PW)
    assert capped["ended_by"] == "cap" and d.state == "idle"
    d.update(_attrs(), now=3730.0, power_w=PW)       # reopens next tick
    nxt = d.update(_off(), now=5000.0,
                   power_w=0.0)
    assert nxt["continued"] is True and nxt["ended_by"] == "stop"


def test_continuation_survives_restore():
    heat, _ = _split_run()
    d = CycleDetector({}, dhw_present=True)
    d.update(_attrs(), now=0.0, power_w=PW)
    d.update(_attrs(dhw=True), now=600.0, power_w=PW)
    d.update(_attrs(dhw=True), now=660.0, power_w=PW)  # running DHW, continued
    payload = d.to_dict()
    assert payload["continued"] is True
    r = CycleDetector({}, dhw_present=True)
    r.restore_from_dict(payload, 700.0)
    assert r.update(_off(dhw=True), now=800.0, power_w=0.0)["continued"] is True


# --- 2. live score of a running cycle --------------------------------------------


def _live_coord(rec: dict[str, Any]) -> DaikinCycleMLCoordinator:
    c = object.__new__(DaikinCycleMLCoordinator)
    c.options = {"good_dt_threshold_k": 4.0}
    c._last_quality_live_ts = 0.0
    c.detector = SimpleNamespace(state="running", partial_record=lambda now: rec)
    return c


@pytest.mark.parametrize("dur,dt,buh,expected", [
    (1200, 2.1, False, 100),          # prod-1 06:42: 20 min, dT 2.1 (was 50)
    (STEADY_RUN_S * 4, 2.1, False, 100),  # dT_max can still grow
    (1200, 6.5, True, 90),            # BUH already used: final
])
async def test_live_score_running_cycle(dur, dt, buh, expected):
    rec = {"start_ts": 0.0, "end_ts": float(dur), "duration_s": dur,
           "mode": "heating", "dT_max": dt, "buh_used": buh}
    c = _live_coord(rec)
    snap = DataSnapshot()
    await c._maybe_refresh_quality_live(10_000.0, snap)
    assert snap.quality_live == expected


# --- 3. runtime check ------------------------------------------------------------


def _rt_coord(cycles: Any, det: Any) -> SimpleNamespace:
    return SimpleNamespace(
        store=SimpleNamespace(cycles_intersecting=lambda a, b: cycles),
        detector=SimpleNamespace(snapshot=det),
    )


def _midnight(t: float) -> float:
    lt = time.localtime(t)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def test_runtime_check_prod1_morning():
    # 2026-11-19 06:42: cycles 429 tail (00:00-00:43), 430 (01:02-06:02),
    # open run since 06:21; ESPAltherma 358.2 min
    now = _midnight(time.time()) + 6 * 3600 + 42 * 60
    m = _midnight(now)
    cycles = [
        {"start_ts": m - 1534, "end_ts": m + 2606},
        {"start_ts": m + 3776, "end_ts": m + 21764},
        {"start_ts": None, "end_ts": m},             # ignored
    ]
    det = lambda: {"state": "running", "start_ts": m + 22904}  # noqa: E731
    out = _runtime_check(_rt_coord(cycles, det),
                         SimpleNamespace(attrs={"Stats: Compressor run today (min)": 358.2}),
                         now)
    assert out["closed_min"] == pytest.approx(43.4 + 299.8, abs=0.1)
    assert out["open_cycle_min"] == pytest.approx(20.3, abs=0.1)
    assert out["native_min"] == 358.2
    assert 99.0 < out["coverage_pct"] < 103.0
    assert out["elapsed_min"] == pytest.approx(402.0, abs=0.1)


def test_runtime_check_errors_and_no_native():
    def boom(*_a: Any) -> Any:
        raise RuntimeError("x")

    c = SimpleNamespace(store=SimpleNamespace(cycles_intersecting=boom),
                        detector=SimpleNamespace(snapshot=boom))
    out = _runtime_check(c, SimpleNamespace(attrs={}))
    assert out["cycles_min"] == 0.0
    assert out["native_min"] is None and out["coverage_pct"] is None
    idle = _runtime_check(_rt_coord([], lambda: {"state": "idle"}),
                          SimpleNamespace(attrs={"Stats: Compressor run today (min)": 0}))
    assert idle["coverage_pct"] is None and idle["diff_min"] == 0.0


# --- 4. runs lost on restart -----------------------------------------------------

T0 = 1795030000.0                     # 2026-11-18 ~19:46 local (base)


def _s(off_min: float, mode: str = "heating", cop: float = 5.0):
    return (T0 + off_min * 60.0, mode, cop)


def test_lost_runs_prod1_restart():
    # cycle 428 22:35:46-22:43:46 -> T0+169.77..177.77 min; 429 from 23:34:26
    w428 = (T0 + 169.77 * 60, T0 + 177.77 * 60)
    w429 = (T0 + 228.43 * 60, T0 + 297.43 * 60)
    samples = [_s(175)] + [_s(198.27 + 5.5 * i) for i in range(5)]  # 23:04-23:26
    runs = _lost_runs([w428, w429], samples)
    assert len(runs) == 1
    start, end, mode, cops = runs[0]
    assert start == pytest.approx(T0 + 198.27 * 60)
    assert end == w429[0]                           # continued into the restart
    assert mode == "heating" and len(cops) == 5


def test_lost_runs_chain_rules():
    w = [(T0, T0 + 60), (T0 + 400 * 60, T0 + 401 * 60)]
    gap = BACKFILL_CHAIN_GAP_S / 60.0 + 1
    samples = (
        [_s(10 + 5 * i) for i in range(4)]                       # run A 15 min
        + [_s(25 + gap + 5 * i) for i in range(4)]               # gap -> run B
        + [_s(80 + 5 * i, "dhw") for i in range(4)]              # mode change
        + [_s(95, "unknown")]                                    # joins DHW
        + [_s(150), _s(152)]                                     # fragment
    )
    runs = _lost_runs(w, samples)
    assert [(r[2], len(r[3])) for r in runs] == [
        ("heating", 4), ("heating", 4), ("dhw", 5)]
    assert all(r[1] < w[1][0] for r in runs)                     # far from next
    assert _lost_runs([(T0, T0 + 60)], samples) == []            # one window
    overlap = [(T0, T0 + 900), (T0 + 600, T0 + 1200), (T0 + 400 * 60, T0 + 401 * 60)]
    # 16 min lies inside the merged window (0-20 min) and is not used
    assert _lost_runs(overlap, [_s(16), _s(21), _s(26), _s(31)]) == [
        (T0 + 21 * 60, T0 + 31 * 60, "heating", [5.0, 5.0, 5.0])]
    assert _lost_runs(w, [_s(30, "unknown"), _s(35, "unknown"), _s(41, "unknown")])[0][2] == "unknown"


async def test_v32_rebuilds_prod1_run(tmp_path):
    db = CycleDB(str(tmp_path / "v32.db"))
    await db.async_open()
    await db.async_initialize()
    await db.async_ensure_cop_samples_table()
    await db.async_create_cop_hourly_v14()
    try:
        for st, en in ((T0 + 169.77 * 60, T0 + 177.77 * 60),
                       (T0 + 228.43 * 60, T0 + 297.43 * 60)):
            await db.async_insert_cycle({
                "start_ts": st, "end_ts": en, "duration_s": int(en - st),
                "mode": "heating", "quality_score": 90, "is_transient": 0,
            })
        for ts, mode, cop in [_s(198.27 + 5.5 * i) for i in range(5)]:
            await db._require().execute(
                "INSERT INTO cop_samples (ts, cop, mode, source, "
                "is_transition_artifact) VALUES (?, ?, ?, 'interval', 0)",
                (ts, cop, mode),
            )
        await db._require().commit()
        stats = await db.async_migrate_to_v32()
        assert stats["runs_rebuilt"] == 1 and stats["completed"] is True
        assert stats["minutes_rebuilt"] == pytest.approx(30.2, abs=0.1)
        async with db._require().execute(
            "SELECT start_ts, end_ts, mode, is_reconstructed, cop_sample_count "
            "FROM cycles WHERE is_reconstructed = 1"
        ) as cur:
            row = tuple(await cur.fetchone())
        assert row[2:] == ("heating", 1, 5)
        day = time.strftime("%Y-%m-%d", time.localtime(row[0]))
        rows = [r for r in await db.async_daily_summary(days=36500) if r["day"] == day]
        assert rows and rows[0]["cycles"] >= 2
        assert await db.async_migrate_to_v32() == {"skipped": 1}
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
