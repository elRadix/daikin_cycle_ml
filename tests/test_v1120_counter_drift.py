"""v1.12.0: counter drift regression tests (issue #101 sub-items).

- add_cycle must increment cycles_today (before: never incremented → drift)
- hydrate_from_rows must restore cycles_total + per-mode (before: reset to 0)
"""
from __future__ import annotations

import datetime as _dt

from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _today_noon_ts() -> float:
    return _dt.datetime.combine(_dt.date.today(), _dt.time(12, 0)).timestamp()


def _make_row(
    *, start_ts: float, mode: str = "heating",
    quality_score: int | None = None,
) -> dict:
    return {
        "start_ts": start_ts, "end_ts": start_ts + 60,
        "duration_s": 60, "mode": mode,
        "dT_max": 5.0, "dT_avg": 3.0,
        "rps_max": 30, "rps_avg": 20.0,
        "outdoor_temp": 10.0,
        "buh_used": 0, "defrost_used": 0,
        "quality_score": quality_score,
        "label": None, "cluster_id": None,
        "cop_avg": None, "cop_sample_count": None,
        "cop_sample_stdev": None, "cop_confidence": None,
    }


def test_add_cycle_increments_cycles_today():
    s = CycleStore()
    s.add_cycle(_make_row(start_ts=100.0))
    s.add_cycle(_make_row(start_ts=200.0))
    assert s.get("cycles_today") == 2
    assert s.get("cycles_total") == 2


def test_good_bad_match_cycles_today_after_runtime():
    s = CycleStore()
    for i, qs in enumerate([80, 80, 80, 30, 30]):
        rec = _make_row(start_ts=100.0 + i * 100, quality_score=qs)
        s.add_cycle(rec)
        key = "good_cycles_today" if qs >= 70 else "bad_cycles_today"
        s.increment(key)
    assert s.get("cycles_today") == 5
    assert s.get("good_cycles_today") + s.get("bad_cycles_today") == 5


def test_hydrate_restores_cycles_total():
    noon = _today_noon_ts()
    rows = [_make_row(start_ts=noon - i * 100) for i in range(5)]
    s = CycleStore()
    s.hydrate_from_rows(rows)
    assert s.get("cycles_total") == 5
    assert s.count() == 5


def test_hydrate_restores_per_mode_counters():
    noon = _today_noon_ts()
    rows = (
        [_make_row(start_ts=noon - i * 100, mode="heating") for i in range(3)]
        + [_make_row(start_ts=noon - 1000 - i * 100, mode="dhw") for i in range(2)]
    )
    s = CycleStore()
    s.hydrate_from_rows(rows)
    assert s.get("cycles_heating") == 3
    assert s.get("cycles_dhw") == 2
    assert s.get("cycles_cooling") == 0


def test_prod_shape_never_occurs():
    """Exact v88 prod failure: hydrate(3 good) + 3 runtime bad."""
    noon = _today_noon_ts()
    rows = [_make_row(start_ts=noon - i * 100, quality_score=80) for i in range(3)]
    s = CycleStore()
    s.hydrate_from_rows(rows)
    assert s.get("cycles_today") == 3
    assert s.get("good_cycles_today") == 3
    assert s.get("bad_cycles_today") == 0

    for i in range(3):
        rec = _make_row(start_ts=noon + 1000 + i * 100, quality_score=30)
        s.add_cycle(rec)
        s.increment("bad_cycles_today")

    assert s.get("cycles_today") == 6
    assert s.get("good_cycles_today") + s.get("bad_cycles_today") == 6
