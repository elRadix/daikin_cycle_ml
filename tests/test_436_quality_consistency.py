"""#436: Daily summary and Daily summary tabbed show the same quality.

Fixture = the #436 reporter's sensor.daily_summary_recent (ERGA08EVH7,
diagnostics 2026-11-19 19:34, v1.24.0). The Daily summary card averaged
the heating and DHW rows of a day unweighted (17 Nov: (71 + 98.5) / 2 =
85) while the tabbed card weighted by cycles ((4*71 + 2*98.5) / 6 = 80).
Both now use the average of all cycles.

Also: today's DHW row showed an average run of 99.8 min next to a
longest run of 70.8 min, because the open run added minutes but no
cycle. daily_summary.runs counts every run with time on the day.
"""
from __future__ import annotations

import json
import re
import shutil
import time

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    _compute_daily_summary_recent,
)
from tests.test_rollup_concurrency import _mk_db
from tests.test_427_cards_live_states import (
    FIXTURE,
    _localized,
    _render,
    _text,
)

DAYS_436 = [
    {"day": "2026-11-19", "mode": "dhw", "cycles": 1, "dur_min": 99.8, "dur_min_avg": 99.8, "dur_max": 70.8, "quality_avg": 89.0, "buh": 0, "defrost": 0},
    {"day": "2026-11-18", "mode": "heating", "cycles": 5, "dur_min": 685.6, "dur_min_avg": 137.1, "dur_max": 312.0, "quality_avg": 74.0, "buh": 0, "defrost": 0},
    {"day": "2026-11-18", "mode": "dhw", "cycles": 2, "dur_min": 88.0, "dur_min_avg": 44.0, "dur_max": 47.0, "quality_avg": 97.5, "buh": 0, "defrost": 0},
    {"day": "2026-11-17", "mode": "heating", "cycles": 4, "dur_min": 1343.2, "dur_min_avg": 335.8, "dur_max": 700.0, "quality_avg": 71.0, "buh": 0, "defrost": 0},
    {"day": "2026-11-17", "mode": "dhw", "cycles": 2, "dur_min": 75.7, "dur_min_avg": 37.8, "dur_max": 51.2, "quality_avg": 98.5, "buh": 0, "defrost": 0},
    {"day": "2026-11-16", "mode": "heating", "cycles": 2, "dur_min": 50.5, "dur_min_avg": 25.3, "dur_max": 40.5, "quality_avg": 91.0, "buh": 1, "defrost": 1},
    {"day": "2026-11-16", "mode": "dhw", "cycles": 2, "dur_min": 91.0, "dur_min_avg": 45.5, "dur_max": 50.0, "quality_avg": 95.0, "buh": 0, "defrost": 1},
]
# average of all 18 cycles: (182+190+284+197+370+195+89) / 18 = 83.7
PERIOD_Q = "84%"


def _states_436() -> dict:
    dump = json.loads(FIXTURE.read_text(encoding="utf-8"))
    loc = _localized(dump, "en")
    sid = "sensor.daikin_cycle_ml_daily_summary_recent"
    loc["states"][sid]["state"] = "18"
    attrs = loc["states"][sid]["attributes"]
    attrs.update({
        "days": DAYS_436, "days_available": 4, "days_count": 4,
        "latest_day": "2026-11-19", "oldest_day": "2026-11-16",
        "events_by_day": {},
        "totals_by_mode": {
            "heating": {"days": 3, "cycles": 11, "dur_min": 2079.3, "buh": 1, "defrost": 1},
            "dhw": {"days": 4, "cycles": 7, "dur_min": 354.5, "buh": 0, "defrost": 1},
            "cooling": {"days": 0, "cycles": 0, "dur_min": 0.0, "buh": 0, "defrost": 0},
        },
    })
    return loc["states"]


@pytest.fixture(scope="module")
def cards_436() -> dict[str, str]:
    if not shutil.which("node"):
        pytest.skip("node not installed")
    dump = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out = _render(dump, "en", states=_states_436())
    return {
        name: " ".join(_text(o) for o in blocks if isinstance(o, str))
        for name, blocks in out.items()
    }


def test_daily_summary_quality_is_average_of_cycles(cards_436):
    text = cards_436["daily-summary"]
    # header + chart header: the average of all cycles
    assert f"QUAL {PERIOD_Q}" in text
    assert "18 cycles" in text
    assert f"avg {PERIOD_Q}" in text
    # per day, weighted by cycles: 93 / 80 / 81 / 89 (was 93 / 85 / 86 / 89)
    assert "Q 80%" in text and "Q 81%" in text
    assert "Q 85%" not in text and "Q 86%" not in text
    # worst day follows the weighted values
    assert re.search(r"Worst day 17 Nov · \S+ ago 80%", text)


def test_tabbed_card_shows_the_same_period_quality(cards_436):
    text = cards_436["daily-summary-tabbed"]
    assert f"Avg quality {PERIOD_Q}" in text


def test_quality_chart_has_no_in_plot_trend_or_zone_labels(cards_436):
    text = cards_436["daily-summary"]
    # zone labels stay in the legend only (once), trend in the header
    assert text.count("Good ≥70") == 1


# ---------- runs per day (server side) ----------


def _row(**kw):
    base = {"day": "2026-11-19", "mode": "dhw", "cycles": 1,
            "total_duration_s": 5987, "duration_max": 4248,
            "quality_sum": 89, "buh_count": 0, "defrost_count": 0}
    base.update(kw)
    return base


def test_dur_min_avg_divides_by_runs():
    out = _compute_daily_summary_recent([_row(runs=2)])
    d = out["days"][0]
    assert d["runs"] == 2
    assert d["dur_min_avg"] == round(5987 / 2 / 60, 1)  # 49.9
    assert d["dur_min_avg"] <= d["dur_max"]
    assert d["quality_avg"] == 89.0  # quality stays per started cycle


def test_dur_min_avg_falls_back_to_cycles_for_old_rows():
    d = _compute_daily_summary_recent([_row()])["days"][0]
    assert d["runs"] == 1
    assert d["dur_min_avg"] == round(5987 / 60, 1)


async def _db(tmp_path):
    return await _mk_db(tmp_path)


async def _cycle(db, start, end, mode="heating", q=80):
    await db.async_insert_cycle({
        "start_ts": start, "end_ts": end, "duration_s": int(end - start),
        "mode": mode, "dT_max": 5.0, "dT_avg": 4.0, "rps_max": 40,
        "rps_avg": 35, "outdoor_temp": 8.0, "buh_used": 0,
        "defrost_used": 0, "quality_score": q, "is_transient": 0,
    })


async def test_rollup_counts_open_run_and_midnight_crossing(tmp_path):
    db = await _db(tmp_path)
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    d0 = time.mktime(time.strptime(day, "%Y-%m-%d"))
    # closed 1 h run on the day + one starting the evening before
    await _cycle(db, d0 + 3600, d0 + 7200, "dhw", 90)
    await _cycle(db, d0 - 3600, d0 + 1800, "dhw", 70)
    await db.async_rollup_day(day)
    rows = [r for r in await db.async_daily_summary(days=5) if r["day"] == day]
    assert len(rows) == 1
    r = rows[0]
    assert r["cycles"] == 1          # started that day (quality, count)
    assert r["runs"] == 2            # both have time on the day
    assert r["total_duration_s"] == 3600 + 1800
    assert r["duration_avg"] == pytest.approx(5400 / 2)
    assert r["duration_avg"] <= r["duration_max"]
    # open run: counted as a run, not as a cycle
    today = time.strftime("%Y-%m-%d")
    t0 = time.mktime(time.strptime(today, "%Y-%m-%d"))
    now = time.time()
    if now - t0 > 1200:  # pragma: no branch - not in the first 20 min
        await _cycle(db, t0 + 60, t0 + 600, "dhw", 89)
        await db.async_rollup_day(
            today, open_cycle={"start_ts": now - 300, "mode": "dhw"}
        )
        tr = [x for x in await db.async_daily_summary(days=1) if x["day"] == today][0]
        assert tr["cycles"] == 1 and tr["runs"] == 2
    await db.async_close()


async def test_v33_rerolls_once(tmp_path):
    db = await _db(tmp_path)
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() - 2 * 86400))
    d0 = time.mktime(time.strptime(day, "%Y-%m-%d"))
    await _cycle(db, d0 + 3600, d0 + 7200)
    first = await db.async_migrate_to_v33()
    assert first["completed"] is True and first["days_rebuilt"] >= 1
    rows = [r for r in await db.async_daily_summary(days=5) if r["day"] == day]
    assert rows[0]["runs"] == 1
    assert await db.async_migrate_to_v33() == {"skipped": 1}
    await db.async_close()
