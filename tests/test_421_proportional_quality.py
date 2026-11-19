"""#421: proportional quality penalties + one-time rescore of all cycles.

Before #421 every penalty was all-or-nothing: a 2 min and an 8 min BUH
run both cost 10 points, a 44 min run the same 30 as a 5 min run, a 19
min pause the same as a 1 min pause; defrost was not considered.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
)
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.engine.cycle_detector import CycleDetector
from custom_components.daikin_cycle_ml.engine.quality_scorer import (
    BUH_UNKNOWN_S,
    DEFROST_UNKNOWN_S,
    PENALTY_BUH,
    PENALTY_DEFROST,
    rescore_history,
    score_breakdown,
    score_cycle,
)
from custom_components.daikin_cycle_ml.sensor import _attrs_last_cycle
from custom_components.daikin_cycle_ml.storage.db import CycleDB
from tests.test_419_quality_runtime import PW, _attrs, _off

GOOD = {"duration_s": 300 * 60, "dT_max": 6.5, "mode": "heating"}

# --- formula --------------------------------------------------------------------


@pytest.mark.parametrize("buh_min,expected", [
    (2, 99),      # 2 of 300 min = 0.7 % -> 0.7 point (was 10)
    (8, 97),      # 8 of 300 min = 2.7 % -> 2.7 points (was 10)
    (30, 90),     # 10 %
    (90, 80),     # 30 % -> capped at 20
])
def test_buh_penalty_follows_buh_time(buh_min, expected):
    rec = dict(GOOD, buh_used=True, buh_s=buh_min * 60.0)
    assert score_cycle(rec) == expected


def test_buh_unknown_time_and_no_duration():
    rec = dict(GOOD, buh_used=True)
    assert score_breakdown(rec)["buh"] == round(100 * BUH_UNKNOWN_S / GOOD["duration_s"], 1)
    assert score_breakdown({"buh_used": True})["buh"] == 0.0       # no share
    rec["buh_s"] = 0.0                                              # flag but 0 s
    assert score_breakdown(rec)["buh"] == round(100 * BUH_UNKNOWN_S / GOOD["duration_s"], 1)


@pytest.mark.parametrize("defrost_min,expected", [
    (6, 100),     # 2 % of a 5 h run: normal
    (15, 100),    # 5 %: still free
    (30, 95),     # 10 %: 5 points
    (60, 90),     # 20 %: capped at 10
])
def test_defrost_penalty_above_normal_share(defrost_min, expected):
    rec = dict(GOOD, defrost_used=True, defrost_s=defrost_min * 60.0)
    assert score_cycle(rec) == expected
    assert score_breakdown(rec)["defrost"] <= PENALTY_DEFROST


def test_running_and_segment_flags():
    rec = {"duration_s": 600, "dT_max": 1.0}
    assert score_breakdown(rec, running=True)["short_run"] == 0.0
    assert score_breakdown(rec, running=True)["low_dt"] == 0.0
    assert score_breakdown(rec, segment=True)["short_run"] == 0.0
    assert score_breakdown(rec, segment=True)["low_dt"] > 0
    assert score_breakdown(rec, short_cycle_ratio=50, options={
        "short_cycle_ratio_threshold": 0})["short_ratio"] == 0.0


def test_score_is_100_minus_breakdown():
    rec = {"duration_s": 1800, "dT_max": 3.0, "buh_used": True, "buh_s": 90.0,
           "defrost_used": True, "defrost_s": 300.0}
    pen = score_breakdown(rec, off_time_s=600, short_cycle_ratio=40)
    assert score_cycle(rec, off_time_s=600, short_cycle_ratio=40) == round(100 - sum(pen.values()))
    assert pen["buh"] == 5.0                     # 1.5 of 30 min
    assert pen["defrost"] == PENALTY_DEFROST      # 16.7 % - 5 % free -> capped


# --- detector: BUH / defrost time -------------------------------------------------


def test_detector_counts_buh_and_defrost_seconds():
    d = CycleDetector({}, dhw_present=True)
    d.update(_attrs(), now=0.0, power_w=PW)
    d.update(dict(_attrs(), **{ATTR_BUH_STEP1: True}), now=30.0, power_w=PW)
    d.update(dict(_attrs(), **{ATTR_BUH_STEP1: True, ATTR_BUH_STEP2: True}),
             now=60.0, power_w=PW)                       # step 2 counts double
    d.update(dict(_attrs(), **{ATTR_DEFROST_OPERATION: True}), now=90.0, power_w=PW)
    d.update(dict(_attrs(), **{ATTR_DEFROST_OPERATION: True}), now=900.0,
             power_w=PW)                                 # 13.5 min gap: not counted
    payload = d.to_dict()
    assert payload["buh_s"] == 90.0 and payload["defrost_s"] == 30.0
    r = CycleDetector({}, dhw_present=True)
    r.restore_from_dict(payload, 910.0)
    rec = r.update(_off(), now=930.0, power_w=0.0)
    assert rec["buh_s"] == 90.0 and rec["defrost_s"] == 30.0


def test_restore_without_times():
    d = CycleDetector({}, dhw_present=True)
    d.update(_attrs(), now=0.0, power_w=PW)
    p = d.to_dict()
    p["buh_s"] = None
    p["defrost_s"] = True
    r = CycleDetector({}, dhw_present=True)
    r.restore_from_dict(p, 10.0)
    assert r.to_dict()["buh_s"] == 0.0 and r.to_dict()["defrost_s"] == 0.0


# --- rescoring stored cycles --------------------------------------------------------

D0 = "2026-11-18"


def _t(h: float) -> float:
    return time.mktime(time.strptime(D0, "%Y-%m-%d")) + h * 3600


def _row(i: int, st: float, en: float, **kw: Any) -> dict[str, Any]:
    r = {"id": i, "start_ts": st, "end_ts": en, "duration_s": int(en - st),
         "mode": "heating", "dT_max": 6.0, "buh_used": 0, "buh_s": None,
         "defrost_used": 0, "defrost_s": None, "dhw_tank_temp": None,
         "is_transient": 0, "is_reconstructed": 0, "quality_score": 50}
    r.update(kw)
    return r


def test_rescore_history_prod1_day():
    rows = [
        _row(1, _t(0), _t(5), buh_used=1),                       # 5 h, BUH
        _row(2, _t(5) + 30, _t(6.5), mode="dhw"),                # split (30 s)
        _row(3, _t(6.5) + 30, _t(12), buh_used=1, defrost_used=1),  # split back
        _row(4, _t(12.2), _t(12.3)),                             # 6 min run, 12 min pause
        _row(5, _t(13), _t(13.5), is_reconstructed=1, dT_max=None, quality_score=None),
        _row(6, _t(14), _t(14.25), dT_max=None, buh_used=1),     # no day data share
    ]
    events = {D0: {"buh_min": 12.0, "defrost_events": 1}}
    scores = rescore_history(rows, {}, events)
    # BUH 12 min shared by length over cycles 1, 3, 6 (5 h / 5.5 h / 15 min)
    buh_rows = [rows[0], rows[2], rows[5]]
    total = sum(r["duration_s"] for r in buh_rows)
    share = {r["id"]: 720.0 * r["duration_s"] / total for r in buh_rows}
    assert scores[1] == score_cycle(dict(rows[0], buh_s=share[1]), {}, segment=True)
    assert scores[1] == 98                                        # 5.6 of 300 min
    assert scores[3] == score_cycle(
        dict(rows[2], buh_s=share[3], defrost_s=DEFROST_UNKNOWN_S), {}, segment=True)
    assert scores[2] == 100                                       # split segment
    s4 = score_breakdown(rows[3], {}, off_time_s=720, short_cycle_ratio=100 * 1 / 4)
    assert scores[4] == round(100 - sum(s4.values()))
    assert scores[5] is None                                      # rebuilt from samples
    assert scores[6] < 100


def test_rescore_history_defaults():
    rows = [_row(1, _t(0), _t(1), buh_used=1, defrost_used=1),
            _row(2, _t(0.5), _t(2))]                               # overlap: no pause
    scores = rescore_history(rows, None, None)
    pen = score_breakdown(dict(rows[0], buh_s=BUH_UNKNOWN_S, defrost_s=DEFROST_UNKNOWN_S))
    assert scores[1] == round(100 - sum(pen.values()))
    assert scores[2] == 100
    assert rescore_history([_row(1, _t(0), _t(1), buh_used=1)], {}, {D0: "bad"})[1] < 100


async def test_rescore_all_cycles_on_db(tmp_path):
    db = CycleDB(str(tmp_path / "q.db"))
    await db.async_open()
    await db.async_initialize()
    try:
        await db.async_insert_cycle({
            "start_ts": _t(0), "end_ts": _t(5), "duration_s": 18000,
            "mode": "heating", "dT_max": 6.0, "buh_used": 1, "buh_s": 120.0,
            "defrost_used": 1, "defrost_s": 360.0, "quality_score": 90,
        })
        await db.async_insert_cycle({
            "start_ts": _t(6), "end_ts": _t(7), "duration_s": 3600,
            "mode": "heating", "dT_max": 6.0, "quality_score": 100,
        })
        async with db._require().execute("SELECT buh_s, defrost_s FROM cycles ORDER BY start_ts") as cur:
            assert tuple(await cur.fetchone()) == (120.0, 360.0)
        stats = await db.async_rescore_all_cycles(lambda rows, ev: rescore_history(rows, {}, ev))
        assert stats["cycles"] == 2 and stats["changed"] == 1 and stats["completed"]
        async with db._require().execute("SELECT quality_score FROM cycles ORDER BY start_ts") as cur:
            assert [r[0] for r in await cur.fetchall()] == [99, 100]
        assert (await db.async_daily_summary(days=36500))
        assert await db.async_rescore_all_cycles(lambda r, e: {}) == {"skipped": 1}
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_old_db_gets_columns(tmp_path):
    db = CycleDB(str(tmp_path / "old.db"))
    await db.async_open()
    await db.async_initialize()
    try:
        conn = db._require()
        await conn.execute("ALTER TABLE cycles DROP COLUMN buh_s")
        await conn.execute("ALTER TABLE cycles DROP COLUMN defrost_s")
        await conn.commit()
        await db.async_initialize()
        async with conn.execute("PRAGMA table_info(cycles)") as cur:
            cols = {r[1] for r in await cur.fetchall()}
        assert {"buh_s", "defrost_s"} <= cols
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_coordinator_rescore_history():
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = None
    c.options = {}
    assert await c.async_rescore_history() is None
    c.db = SimpleNamespace(async_rescore_all_cycles=AsyncMock(return_value={"completed": True}))
    assert await c.async_rescore_history() == {"completed": True}
    c.db = SimpleNamespace(async_rescore_all_cycles=AsyncMock(side_effect=RuntimeError("x")))
    assert await c.async_rescore_history() is None
    seen: list[Any] = []

    async def _run(fn):
        seen.append(fn([_row(1, _t(0), _t(1))], {}))
        return {"completed": True}

    c.db = SimpleNamespace(async_rescore_all_cycles=_run)
    await c.async_rescore_history()
    assert seen == [{1: 100}]


def test_last_cycle_sensor_shows_breakdown():
    last = {"duration_s": 18000, "buh_s": 120.0, "defrost_s": None,
            "quality_penalties": {"buh": 0.7}}
    c = SimpleNamespace(store=SimpleNamespace(last_cycle=lambda: last),
                        cluster_label=lambda cid: None)
    attrs = _attrs_last_cycle(SimpleNamespace(cluster_id=None), c)  # type: ignore[arg-type]
    assert attrs["buh_min"] == 2.0 and attrs["defrost_min"] is None
    assert attrs["quality_penalties"] == {"buh": 0.7}
    last["quality_penalties"] = "x"
    assert _attrs_last_cycle(SimpleNamespace(cluster_id=None), c)["quality_penalties"] is None  # type: ignore[arg-type]


def test_penalty_caps():
    rec = {"duration_s": 60, "buh_used": True, "buh_s": 60.0,
           "defrost_used": True, "defrost_s": 60.0}
    pen = score_breakdown(rec)
    assert pen["buh"] == PENALTY_BUH and pen["defrost"] == PENALTY_DEFROST
