"""#400: cross-midnight runs in the daily summary.

Reported scenario (Tweakers, 2026-11-17): a run crossing 00:00 made the
morning show quality 0 %, "longest 5h" with "total 4h" on the start day,
and per-day BUH/defrost counts of 0 while the Today block showed 29 min
BUH and 6 defrosts.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    _compute_daily_summary_recent,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB

D0 = "2026-11-16"
D1 = "2026-11-17"


def _ts(day: str, h: int, mi: int = 0) -> float:
    return time.mktime(time.strptime(f"{day} {h:02d}:{mi:02d}", "%Y-%m-%d %H:%M"))


async def _mk_db(tmp_path) -> CycleDB:
    db = CycleDB(str(tmp_path / "t400.db"))
    await db.async_open()
    await db.async_initialize()
    return db


async def _ins(db: CycleDB, start: float, end: float, **kw) -> int:
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, "
        "is_transient, quality_score, dT_max, rps_avg, buh_used, "
        "defrost_used) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (start, end, int(end - start), kw.get("mode", "heating"), 0,
         kw.get("quality_score", 80), kw.get("dT_max", 4.0), 25.0,
         kw.get("buh_used", 0), kw.get("defrost_used", 0)),
    )
    await conn.commit()
    return int(cur.lastrowid)


async def _summary(db: CycleDB) -> dict[str, dict]:
    rows = await db.async_daily_summary(days=36500)
    return {r["day"]: r for r in rows if r["mode"] == "heating"}


async def _close(db: CycleDB) -> None:
    await db.async_close()
    await asyncio.sleep(0.05)


# --- longest <= total ---------------------------------------------------------


async def test_cross_midnight_longest_never_exceeds_total(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        # 5h run 23:00 -> 04:00 next day, plus a 2h afternoon run on D1.
        await _ins(db, _ts(D0, 23), _ts(D1, 4), quality_score=85)
        await _ins(db, _ts(D1, 14), _ts(D1, 16), quality_score=75)
        await db.async_rollup_day(D0)
        await db.async_rollup_day(D1)
        s = await _summary(db)
        for day in (D0, D1):
            assert s[day]["duration_max"] <= s[day]["total_duration_s"], day
        assert s[D0]["total_duration_s"] == 3600
        assert s[D0]["duration_max"] == 3600          # was 18000 (5h)
        assert s[D1]["total_duration_s"] == 6 * 3600   # 4h tail + 2h run
        assert s[D1]["duration_max"] == 4 * 3600       # tail is longest
        # cycle count + quality stay on the start day (R709)
        assert s[D0]["cycles"] == 1 and s[D0]["quality_avg"] == 85
        assert s[D1]["cycles"] == 1 and s[D1]["quality_avg"] == 75
    finally:
        await _close(db)


async def test_tail_only_day_has_no_quality(tmp_path):
    """Morning after: only the overnight tail -> no quality, not 0 %."""
    db = await _mk_db(tmp_path)
    try:
        await _ins(db, _ts(D0, 23), _ts(D1, 4), quality_score=85)
        await db.async_rollup_day(D1)
        rows = await db.async_daily_summary(days=36500)
        out = _compute_daily_summary_recent(rows)
        d1 = [d for d in out["days"] if d["day"] == D1]
        assert len(d1) == 1
        assert d1[0]["cycles"] == 0
        assert d1[0]["dur_min"] == 240.0
        assert d1[0]["quality_avg"] is None
    finally:
        await _close(db)


# --- forward merge keeps flags ------------------------------------------------


async def test_merge_carries_buh_defrost_and_peak_dt(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        keeper = await _ins(db, _ts(D1, 10), _ts(D1, 11), dT_max=3.0)
        new = await _ins(
            db, _ts(D1, 11) + 60, _ts(D1, 12),
            dT_max=5.5, buh_used=1, defrost_used=1,
        )
        assert await db.async_merge_cycle_forward(new) == 1
        async with db._require().execute(
            "SELECT buh_used, defrost_used, dT_max, end_ts FROM cycles "
            "WHERE id = ?", (keeper,)
        ) as cur:
            row = await cur.fetchone()
        assert (row[0], row[1], row[2]) == (1, 1, 5.5)
        assert row[3] == _ts(D1, 12)
    finally:
        await _close(db)


async def test_merge_without_flags_stays_clean(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        keeper = await _ins(db, _ts(D1, 10), _ts(D1, 11), dT_max=4.0)
        new = await _ins(db, _ts(D1, 11) + 30, _ts(D1, 12), dT_max=3.0)
        assert await db.async_merge_cycle_forward(new) == 1
        async with db._require().execute(
            "SELECT buh_used, defrost_used, dT_max FROM cycles WHERE id = ?",
            (keeper,),
        ) as cur:
            row = await cur.fetchone()
        assert (row[0], row[1], row[2]) == (0, 0, 4.0)
    finally:
        await _close(db)


# --- real per-day events ------------------------------------------------------


async def test_runtime_events_by_day(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        await db.async_set_model_state(
            f"runtime_acc.{D1}",
            {"day": D1, "buh_total_s": 29 * 60, "defrost_count": 6},
        )
        # pre-v1.22.7 payload without buh_total_s
        await db.async_set_model_state(
            f"runtime_acc.{D0}",
            {"day": D0, "buh_step1_s": 600.0, "buh_step2_s": 300.0},
        )
        conn = db._require()
        await conn.execute(
            "INSERT INTO model_state (key, value_json, updated_ts) "
            "VALUES ('runtime_acc.bad', 'not json', 0)"
        )
        await conn.execute(
            "INSERT INTO model_state (key, value_json, updated_ts) "
            "VALUES ('runtime_acc.list', '[1]', 0)"
        )
        await conn.commit()
        ev = await db.async_runtime_events_by_day()
        assert ev[D1] == {"buh_min": 29.0, "defrost_events": 6}
        assert ev[D0] == {"buh_min": 10.0, "defrost_events": 0}
        assert "bad" not in ev and "list" not in ev
    finally:
        await _close(db)


async def test_runtime_events_no_buh_keys(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        await db.async_set_model_state(f"runtime_acc.{D1}", {"day": D1})
        ev = await db.async_runtime_events_by_day()
        assert ev[D1] == {"buh_min": 0.0, "defrost_events": 0}
    finally:
        await _close(db)


def test_events_by_day_in_payload():
    ev = {D1: {"buh_min": 29.0, "defrost_events": 6}}
    assert _compute_daily_summary_recent([], ev)["events_by_day"] == ev
    row = {"day": D1, "mode": "heating", "cycles": 1, "total_duration_s": 60,
           "duration_max": 60, "quality_sum": 80, "buh_count": 0,
           "defrost_count": 0}
    out = _compute_daily_summary_recent([row], ev)
    assert out["events_by_day"][D1]["defrost_events"] == 6
    assert _compute_daily_summary_recent([row])["events_by_day"] == {}


@pytest.mark.parametrize("bad", [None, "x", 42])
async def test_refresh_ignores_non_dict_events(bad):
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_daily_summary = AsyncMock(return_value=[])
    c.db.async_runtime_events_by_day = AsyncMock(return_value=bad)
    await c._refresh_daily_summary_recent()
    assert c._daily_summary_recent["events_by_day"] == {}


async def test_refresh_survives_events_error():
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_daily_summary = AsyncMock(return_value=[])
    c.db.async_runtime_events_by_day = AsyncMock(side_effect=RuntimeError)
    await c._refresh_daily_summary_recent()
    assert c._daily_summary_recent["events_by_day"] == {}


# --- Pattern Analysis card uses real per-day events -----------------------------

_NODE = r"""
const vm = require('vm');
const D = JSON.parse(require('fs').readFileSync(0, 'utf8'));
function render(body, states) {
  const hass = { language: 'en', states, entities: {}, user: { name: 'u', is_admin: true },
                 themes: { darkMode: false } };
  const FD = class extends Date { constructor(...a) { if (a.length) super(...a); else super('2026-11-17T12:00:00Z'); }
                                  static now() { return Date.parse('2026-11-17T12:00:00Z'); } };
  let seed = 1; const M = Object.create(Math);
  M.random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const ctx = vm.createContext({ Date: FD, Math: M, JSON, Object, Array, String, Number, parseFloat,
    parseInt, isNaN, isFinite, encodeURIComponent, decodeURIComponent, RegExp, Error,
    setTimeout: () => 0, clearTimeout: () => 0, requestAnimationFrame: () => 0,
    console: { log() {}, warn() {}, error() {} }, window: {} });
  const fn = vm.runInContext('(function(hass,states,entity,user,variables,html,helpers){' + body + '\n})', ctx);
  try { const o = fn.call({ _config: {}, __paState: { tab: D.tab, win: 7 } }, hass, states, undefined, hass.user, { lang_override: '' }, (s) => s.join(''), {});
        return typeof o === 'string' ? o : String(JSON.stringify(o)); }
  catch (e) { return 'THROW: ' + e.message; }
}
process.stdout.write(JSON.stringify(D.cases.map((st) => render(D.body, st))));
"""


def _pa_states(events: dict | None) -> dict:
    eid = "sensor.daikin_cycle_ml_daily_summary_recent"
    days = [
        {"day": d, "mode": "heating", "cycles": 4, "dur_min": 300.0,
         "dur_min_avg": 75.0, "dur_max": 120.0, "quality_avg": 80.0,
         "buh": 0, "defrost": 0}
        for d in ("2026-11-15", "2026-11-16", "2026-11-17")
    ]
    attrs: dict = {"days": days, "days_available": 3, "totals_by_mode": {}}
    if events is not None:
        attrs["events_by_day"] = events
    cs = "sensor.daikin_cycle_ml_cycle_state"
    return {
        eid: {"entity_id": eid, "state": "12", "attributes": attrs},
        cs: {"entity_id": cs, "state": "idle", "attributes": {}},
    }


@pytest.mark.skipif(
    __import__("shutil").which("node") is None, reason="node not installed"
)
@pytest.mark.parametrize(
    "card,tab,must_change",
    [("daily-summary-tabbed", "events", True), ("pattern-analysis", "dist", False)],
)
def test_cards_use_events_by_day(card, tab, must_change):
    import json
    import subprocess
    from pathlib import Path

    from tests.test_347_dashboard_entity_resolution import _js_blocks

    path = (Path(__file__).resolve().parent.parent
            / f"dashboard/cards/{card}/{card}.yaml")
    body = next(b for b in _js_blocks(path) if "EVENTS_BY_DAY" in b)
    ev = {"2026-11-17": {"buh_min": 29.0, "defrost_events": 6}}
    cases = [_pa_states(None), _pa_states({}), _pa_states(ev)]
    proc = subprocess.run(
        ["node", "-e", _NODE],
        input=json.dumps({"body": body, "cases": cases, "tab": tab}),
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    old, empty, new = json.loads(proc.stdout)
    for out in (old, empty, new):
        assert not out.startswith("THROW"), out[:200]
    assert old == empty          # older backend without events: unchanged
    if must_change:
        assert new != old        # real events reach the Events tab
