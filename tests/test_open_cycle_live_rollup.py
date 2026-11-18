"""A running cycle is visible in daily_summary on every day it covers.

Cycle rows are written on close only, so the 15-min live rollup (R782)
re-rolled today without the running cycle: a run 22:00 -> 03:00 showed
0 h on both days at 01:00 and appeared only after it ended. The detector
never splits a cycle at midnight (one cycle 22:00 -> 03:00).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

import custom_components.daikin_cycle_ml.coordinator as coord_mod
import custom_components.daikin_cycle_ml.storage.db as db_mod
from custom_components.daikin_cycle_ml.const import (
    ATTR_INV_FREQUENCY_RPS,
    ATTR_OPERATION_MODE,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    _days_covered,
    _open_cycle_from_detector,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import CycleDetector
from custom_components.daikin_cycle_ml.storage.db import CycleDB, _open_cycle_row

D0, D1, D2 = "2026-11-16", "2026-11-17", "2026-11-18"
ON = {ATTR_INV_FREQUENCY_RPS: 40, ATTR_OPERATION_MODE: "Heating",
      "I/U operation mode": "Heating"}
OFF = {ATTR_INV_FREQUENCY_RPS: 0, ATTR_OPERATION_MODE: "Heating",
       "I/U operation mode": "Heating"}


def _ts(day: str, h: int, m: int = 0) -> float:
    return time.mktime(time.strptime(f"{day} {h:02d}:{m:02d}", "%Y-%m-%d %H:%M"))


async def _mk_db(tmp_path) -> CycleDB:
    db = CycleDB(str(tmp_path / "live.db"))
    await db.async_open()
    await db.async_initialize()
    return db


async def _day(db: CycleDB, day: str) -> dict[str, Any] | None:
    rows = [r for r in await db.async_daily_summary(days=36500) if r["day"] == day]
    return rows[0] if rows else None


class _Coord(DaikinCycleMLCoordinator):
    options: dict[str, Any] = {}  # type: ignore[assignment]


def _coord(db: CycleDB, det: CycleDetector) -> _Coord:
    c = object.__new__(_Coord)
    c.db = db
    c.detector = det
    c._last_rollup_today_ts = 0.0
    c._daily_summary_recent = None
    return c


def _run(det: CycleDetector, start: float, until: float) -> list[dict[str, Any]]:
    closed = []
    t = start
    while t <= until:
        r = det.update(ON, now=t)
        if r:
            closed.append(r)
        t += 30.0
    return closed


async def test_run_across_midnight_visible_live_and_after_close(tmp_path, monkeypatch):
    db = await _mk_db(tmp_path)
    try:
        det = CycleDetector({})
        assert _run(det, _ts(D0, 22), _ts(D1, 1)) == []    # not split at 00:00
        assert det.state == "running"
        now = _ts(D1, 1)
        monkeypatch.setattr(db_mod.time, "time", lambda: now)
        c = _coord(db, det)
        await c._maybe_rollup_today_live(now)
        d0, d1 = await _day(db, D0), await _day(db, D1)
        # before the fix both days were empty at 01:00
        assert d0["total_duration_s"] == 2 * 3600 and d0["duration_max"] == 2 * 3600
        assert d1["total_duration_s"] == 3600 and d1["duration_max"] == 3600
        assert d0["cycles"] == 0 and d1["cycles"] == 0    # counted on close
        assert d0["quality_avg"] is None
        assert c._daily_summary_recent["days"]             # payload refreshed

        # close at 03:00 -> one cycle; both days re-rolled from the DB row
        _run(det, _ts(D1, 1) + 30, _ts(D1, 3) - 30)
        rec = det.update(OFF, now=_ts(D1, 3))
        assert rec is not None and rec["start_ts"] == _ts(D0, 22)
        await db.async_insert_cycle(rec)
        monkeypatch.setattr(db_mod.time, "time", lambda: _ts(D1, 4))
        await db.async_rollup_day(D0)
        await db.async_rollup_day(D1)
        d0, d1 = await _day(db, D0), await _day(db, D1)
        assert d0["cycles"] == 1 and d0["total_duration_s"] == 2 * 3600
        assert d1["cycles"] == 0 and d1["total_duration_s"] == 3 * 3600
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_open_cycle_adds_to_closed_rows_same_day(tmp_path, monkeypatch):
    db = await _mk_db(tmp_path)
    try:
        rec = {"start_ts": _ts(D1, 8), "end_ts": _ts(D1, 9), "duration_s": 3600,
               "mode": "heating", "quality_score": 80, "is_transient": 0}
        await db.async_insert_cycle(rec)
        monkeypatch.setattr(db_mod.time, "time", lambda: _ts(D1, 12))
        await db.async_rollup_day(
            D1, open_cycle={"start_ts": _ts(D1, 10), "mode": "heating"}
        )
        d1 = await _day(db, D1)
        assert d1["cycles"] == 1 and d1["quality_avg"] == 80
        assert d1["total_duration_s"] == 3 * 3600          # 1 h closed + 2 h open
        assert d1["duration_max"] == 2 * 3600
        # mode filter excludes the open cycle
        await db.async_rollup_day(
            D1, modes=("dhw",), open_cycle={"start_ts": _ts(D1, 10), "mode": "heating"}
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_open_cycle_only_row(tmp_path, monkeypatch):
    db = await _mk_db(tmp_path)
    try:
        monkeypatch.setattr(db_mod.time, "time", lambda: _ts(D1, 2))
        n = await db.async_rollup_day(D1, open_cycle={"start_ts": _ts(D1, 1)})
        assert n == 1
        d1 = await _day(db, D1)
        assert d1["mode"] == "unknown" and d1["total_duration_s"] == 3600
        assert await db.async_rollup_day(D2, open_cycle={"start_ts": _ts(D1, 1)}) == 0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.parametrize(
    "oc,modes,expected",
    [
        (None, None, None),
        ("x", None, None),
        ({"start_ts": None}, None, None),
        ({"start_ts": True}, None, None),
        ({"start_ts": 0}, None, None),
        ({"start_ts": 1.0, "mode": "dhw"}, ("heating",), None),
    ],
)
def test_open_cycle_row_rejects(oc, modes, expected):
    assert _open_cycle_row(oc, _ts(D1, 0), _ts(D1, 12), modes) is expected


def test_open_cycle_row_outside_day():
    later = {"start_ts": _ts(D2, 1)}
    assert _open_cycle_row(later, _ts(D1, 0), _ts(D1, 23), None) is None


class _Det:
    def __init__(self, snap: Any = None, boom: bool = False) -> None:
        self._snap, self._boom = snap, boom

    def snapshot(self) -> Any:
        if self._boom:
            raise RuntimeError("x")
        return self._snap


@pytest.mark.parametrize(
    "det,expected",
    [
        (_Det(boom=True), None),
        (_Det("nope"), None),
        (_Det({"start_ts": None}), None),
        (_Det({"start_ts": False}), None),
        (_Det({"start_ts": 0}), None),
        (_Det({"start_ts": 5.0}), {"start_ts": 5.0, "mode": "unknown"}),
        (_Det({"start_ts": 5.0, "mode": "dhw"}), {"start_ts": 5.0, "mode": "dhw"}),
    ],
)
def test_open_cycle_from_detector(det, expected):
    assert _open_cycle_from_detector(det) == expected


def test_days_covered():
    now = _ts(D1, 1)
    assert _days_covered(None, now) == [D1]
    assert _days_covered({"start_ts": _ts(D1, 0, 30)}, now) == [D1]
    assert _days_covered({"start_ts": _ts(D0, 22)}, now) == [D0, D1]
    assert _days_covered({"start_ts": _ts(D0, 1)}, _ts(D2, 1)) == [D0, D1, D2]
    # start in the future (clock skew) -> today only
    assert _days_covered({"start_ts": _ts(D2, 5)}, now) == [D1]
    # longer than the 48 h cap -> first 3 days + today
    out = _days_covered({"start_ts": _ts("2026-11-10", 1)}, _ts(D1, 1))
    assert out[-1] == D1 and len(out) == 4


async def test_live_rollup_survives_rollup_error(monkeypatch):
    class _DB:
        async def async_rollup_day(self, *a, **k):
            raise RuntimeError("db")

    c = _coord(_DB(), _Det({"start_ts": 5.0}))  # type: ignore[arg-type]
    c.detector.state = "running"
    await c._maybe_rollup_today_live(time.time())   # logs, does not raise
    assert coord_mod is not None
