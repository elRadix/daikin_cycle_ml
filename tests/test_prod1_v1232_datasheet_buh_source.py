"""prod-1 diagnostics 2026-11-18 22:05 (v1.23.2), three linked defects.

1. AUTO source switched monolithic -> individual on a 12/12 tie (Q1:
   v2 wins on tie). The individual set only carries the required
   attributes, so the native "Stats: ..." counters and the raw outdoor
   key disappeared (runtime/BUH/defrost/starts fell back to computed).
2. ``cop_normalized_a7w35`` / ``cop_vs_datasheet_pct`` stayed null:
   ``_resolve_outdoor_temp`` read only "R1T-Outdoor air temp." and
   ``last_record`` exists only on the closing tick.
3. ``buh_excessive`` fired with ratio 0.444 (cycles with any BUH /
   cycles) while BUH ran 9-10 min/day on ~20 h runs.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import ATTR_OUTDOOR_AIR_R1T
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    _buh_time_ratio,
)
from custom_components.daikin_cycle_ml.engine.model_datasheets import load_bundled
from custom_components.daikin_cycle_ml.engine.runtime_source import (
    read_native_compressor_minutes,
    read_native_defrost_count,
)
from tests.test_v2_coexistence import (
    _bare,
    _full_attrs,
    _set_mono_state,
    _set_read,
    _set_resolve,
)

# --- 1. AUTO tie keeps monolithic extras ---------------------------------------

MONO_EXTRA = {
    "Stats: Compressor run today (min)": 1309.02,
    "Stats: Defrosts today": 4,
    "Stats: Backup heater today (min)": 9.0,
    "Stats: Compressor starts today": 7,
    "R1T-Outdoor air temp.": 10,
}


def test_auto_tie_individual_supplemented_from_mono(monkeypatch):
    c = _bare()
    _set_mono_state(c, present=True)
    ind = _full_attrs()
    ind[ATTR_OUTDOOR_AIR_R1T] = 10.0
    mono = {**_full_attrs(), ATTR_OUTDOOR_AIR_R1T: 99.0, **MONO_EXTRA}
    _set_resolve(monkeypatch, attrs=ind)
    _set_read(monkeypatch, attrs=mono)
    choice = c._resolve_auto_source()
    assert choice.chosen == "individual"          # Q1 tie rule unchanged
    attrs = choice.ind_attrs
    assert read_native_compressor_minutes(attrs) == pytest.approx(1309.02)
    assert read_native_defrost_count(attrs) == 4
    assert attrs[ATTR_OUTDOOR_AIR_R1T] == 10.0      # individual wins on shared key
    assert c._source_resolution["supplemented_from_mono"] == len(MONO_EXTRA)


def test_auto_individual_without_mono_unchanged(monkeypatch):
    c = _bare()
    _set_mono_state(c, present=False)
    _set_resolve(monkeypatch)
    choice = c._resolve_auto_source()
    assert choice.chosen == "individual"
    assert choice.ind_attrs == _full_attrs()
    assert c._source_resolution["supplemented_from_mono"] == 0


def test_auto_monolithic_choice_not_supplemented(monkeypatch):
    c = _bare()
    _set_mono_state(c, present=True)
    _set_resolve(monkeypatch, attrs={}, missing=["x"] * 5, discovered=7)
    _set_read(monkeypatch, attrs={**_full_attrs(), **MONO_EXTRA})
    choice = c._resolve_auto_source()
    assert choice.chosen == "monolithic"
    assert c._source_resolution["supplemented_from_mono"] == 0


# --- 2. datasheet normalisation with the individual source ----------------------


def _ds_coord() -> DaikinCycleMLCoordinator:
    c = object.__new__(DaikinCycleMLCoordinator)
    c.entry = MagicMock()
    c.entry.data = {"model": "epra12eav3"}
    c._datasheet_user_loaded = True
    c._datasheet_defaults = None
    c._datasheet_cache = {}
    c._datasheet_user = {}
    c._datasheet_merged = load_bundled()
    c._stooklijn_cache = {"huidige_lwt": 30.9}
    return c


@pytest.mark.parametrize(
    "attrs",
    [
        {"Outdoor air temp.(R1T)": 10.0},          # individual (prod-1 now)
        {"R1T-Outdoor air temp.": 10},             # monolithic raw key
    ],
)
def test_outdoor_resolved_without_last_record(attrs):
    snap = SimpleNamespace(attrs=attrs, last_record=None)
    assert _ds_coord()._resolve_outdoor_temp(snap) == 10.0


async def test_prod1_normalized_a7w35_not_null():
    c = _ds_coord()
    snap = SimpleNamespace(
        cop=6.118, attrs={"Outdoor air temp.(R1T)": 10.0}, last_record=None,
    )
    await c._refresh_datasheet_state(
        time.time(),
        c._resolve_lwt_for_datasheet(snap),
        c._resolve_outdoor_temp(snap),
        c._resolve_cop_for_datasheet(snap),
    )
    norm = c._datasheet_cache["cop_normalized_a7w35"]
    pct = c._datasheet_cache["cop_vs_datasheet_pct"]
    assert norm is not None and pct is not None
    # LWT 30.9 / outdoor 10 is an easier point than A7/W35 -> lower normalised
    assert 3.0 < norm < 6.118


# --- 3. BUH ratio by time -------------------------------------------------------

def _rows(days: list[tuple[str, int, int, int]]) -> list[dict[str, Any]]:
    return [
        {"day": d, "mode": "heating", "total_duration_s": run, "cycles": cyc,
         "buh_count": buh}
        for d, run, cyc, buh in days
    ]


PROD1_WEEK = _rows([
    ("2026-11-12", 80543, 1, 1), ("2026-11-13", 80319, 1, 0),
    ("2026-11-14", 77808, 1, 1), ("2026-11-15", 56005, 2, 2),
    ("2026-11-16", 30897, 1, 0), ("2026-11-17", 80939, 2, 1),
    ("2026-11-18", 75099, 1, 1),
])
PROD1_BUH_MIN = {d: {"buh_min": m, "defrost_events": 0} for d, m in [
    ("2026-11-12", 12.0), ("2026-11-14", 20.0), ("2026-11-15", 30.0),
    ("2026-11-17", 15.0), ("2026-11-18", 10.0),
]}


def test_prod1_cycle_ratio_was_false_positive():
    buh = sum(r["buh_count"] for r in PROD1_WEEK)
    cyc = sum(r["cycles"] for r in PROD1_WEEK)
    assert buh / cyc > 0.15                       # old metric: 6/9 -> alert


def test_prod1_time_ratio_below_threshold():
    ratio = _buh_time_ratio(PROD1_WEEK, PROD1_BUH_MIN)
    assert ratio == pytest.approx(0.011, abs=0.001)  # 87 min / 134 h = 1.1 %
    assert ratio < 0.15                           # threshold: no alert


def test_time_ratio_flags_real_buh_use():
    rows = _rows([("2026-11-18", 36000, 3, 3)])
    assert _buh_time_ratio(rows, {"2026-11-18": {"buh_min": 180.0}}) == pytest.approx(0.3)


@pytest.mark.parametrize(
    "rows,events",
    [
        ([], {}),
        (_rows([("2026-11-18", 3600, 1, 1)]), {}),                       # no BUH minutes stored
        (_rows([("2026-11-18", 0, 0, 0)]), {"2026-11-18": {"buh_min": 5}}),  # no runtime
    ],
)
def test_time_ratio_none_falls_back(rows, events):
    assert _buh_time_ratio(rows, events) is None


def test_time_ratio_ignores_bad_buh_values():
    rows = _rows([("2026-11-17", 3600, 1, 1), ("2026-11-18", 3600, 1, 1)])
    ev = {"2026-11-17": {"buh_min": True}, "2026-11-18": {"buh_min": "x"}}
    assert _buh_time_ratio(rows, ev) == 0.0


class _DB:
    def __init__(self, rows, events, boom=False):
        self._rows, self._events, self._boom = rows, events, boom

    async def async_daily_summary(self, days=7):
        return self._rows

    async def async_defrost_duration_since(self, ts):
        return 0.0

    async def async_runtime_events_by_day(self):
        if self._boom:
            raise RuntimeError("x")
        return self._events


def _rollup_coord(db) -> DaikinCycleMLCoordinator:
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c._compute_db_retention_stale = AsyncMock(return_value={})
    c._compute_kmeans_stale = AsyncMock(return_value={})
    c._persist_energy_baseline = AsyncMock()
    c._compute_energy_daily_anomaly = AsyncMock(return_value={})
    c._compute_avg_duration_7d_min = AsyncMock(return_value=None)
    return c


async def test_refresh_7d_uses_time_ratio():
    c = _rollup_coord(_DB(PROD1_WEEK, PROD1_BUH_MIN))
    await c._refresh_7d_rollups()
    assert c._buh_7d_count == 6
    assert c._buh_7d_ratio == pytest.approx(0.011, abs=0.001)


@pytest.mark.parametrize("events,boom", [({}, False), ("bad", False), (None, True)])
async def test_refresh_7d_falls_back_to_cycle_ratio(events, boom):
    c = _rollup_coord(_DB(PROD1_WEEK, events, boom=boom))
    await c._refresh_7d_rollups()
    assert c._buh_7d_ratio == round(6 / 9, 3)
