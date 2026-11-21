"""#466: ESPAltherma "today" counters that never reset at midnight.

Replay of a Tweakers report (ERGA08EAV3, ESPAltherma v2 with stats, no
clock on the ESP): at 14:24 the Daily summary card showed 110 starts,
531 h compressor run, 2 h 20 backup heater and 33 defrosts "today",
while the unit had started 2-3 times, the backup heater had not run and
there had been 1 defrost. ESPAltherma rolls these counters over at local
midnight only when the ESP has a clock (include/stats.h: day = -1 while
the clock is not set); without one they count since boot.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import sensor as S
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.engine import runtime_source as rs

MIDNIGHT = time.mktime((2026, 11, 21, 0, 0, 0, 0, 0, -1))
NOW = MIDNIGHT + 14 * 3600 + 24 * 60          # 14:24
REPORTED = {
    "Stats: Compressor starts today": "110",
    "Stats: Compressor run today (min)": "31860.00",   # 531 h
    "Stats: Backup heater today (min)": "140.00",      # 2 h 20
    "Stats: Defrosts today": "33",
}
RUN_START = NOW - 20 * 60                       # "draait 20 min, sinds 13:39"-like open run


def _coord(attrs: dict) -> MagicMock:
    c = MagicMock()
    c.store = MagicMock()
    c.store.cycles_today.return_value = [
        {"start_ts": MIDNIGHT + 3 * 3600, "end_ts": MIDNIGHT + 5 * 3600, "mode": "heating"},
    ]
    c.store.cycles_intersecting.return_value = [
        {"start_ts": MIDNIGHT + 3 * 3600, "end_ts": MIDNIGHT + 5 * 3600, "mode": "heating"},
    ]
    c.last_attrs = attrs
    c.runtime_snapshot = {
        "buh_step1_s": 0.0, "buh_step2_s": 0.0, "buh_total_s": 0.0,
        "defrost_count": 1.0, "defrost_duration_s": 240.0,
        "last_defrost_ts": NOW - 3600, "defrost_start_ts": None,
        "prev_defrost": False, "defrost_prior_s": None,
    }
    c.entry = None
    return c


def _snap(attrs: dict) -> DataSnapshot:
    s = DataSnapshot()
    s.state = "running"
    s.cycle_start_ts = RUN_START
    s.attrs = attrs
    return s


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(S, "_now", lambda: NOW)
    monkeypatch.setattr(S, "_local_midnight", lambda _: MIDNIGHT)


def test_reported_counters_are_not_used() -> None:
    c, s = _coord(dict(REPORTED)), _snap(dict(REPORTED))
    assert S._value_compressor_starts_today(s, c) == 1          # not 110
    assert S._value_runtime_compressor_today_s(s, c) == 2 * 3600 + 20 * 60  # not 531 h
    assert S._value_runtime_buh_today_s(s, c) == 0              # not 2 h 20
    assert S._value_defrost_count_today(s, c) == 1              # not 33


def test_attributes_say_why() -> None:
    c, s = _coord(dict(REPORTED)), _snap(dict(REPORTED))
    for fn in (S._attrs_runtime_compressor_today_s, S._attrs_runtime_buh_today_s,
               S._attrs_compressor_starts_today, S._attrs_defrost_count_today):
        a = fn(s, c)
        assert a["native_daily"] is False
        assert a["source"] == "computed"


def test_daily_counters_are_still_used() -> None:
    good = {
        "Stats: Compressor starts today": "3",
        "Stats: Compressor run today (min)": "500.0",
        "Stats: Backup heater today (min)": "0",
        "Stats: Defrosts today": "1",
    }
    c, s = _coord(dict(good)), _snap(dict(good))
    assert S._value_compressor_starts_today(s, c) == 3
    assert S._value_runtime_compressor_today_s(s, c) == 500 * 60
    assert S._attrs_compressor_starts_today(s, c)["native_daily"] is True
    assert S._attrs_compressor_starts_today(s, c)["source"] == "native"


def test_backup_heater_alone_can_prove_it() -> None:
    attrs = {"Stats: Backup heater today (min)": "2000", "Stats: Defrosts today": "40"}
    assert rs.native_today_is_daily(attrs, 864.0) is False
    assert "Stats: Defrosts today" not in rs.daily_attrs(attrs, 864.0)


@pytest.mark.parametrize(("minutes", "expected"), [(864.0, True), (850.0, True), (849.0, False)])
def test_slack_at_the_limit(minutes: float, expected: bool) -> None:
    assert rs.native_today_is_daily({"Stats: Compressor run today (min)": 855.0}, minutes) is expected


def test_non_dict_and_missing_values_pass_through() -> None:
    assert rs.daily_attrs([], 10.0) == []  # type: ignore[arg-type]
    assert rs.daily_attrs({}, 10.0) == {}
    assert rs.native_today_is_daily({"Stats: Compressor run today (min)": "unknown"}, 0.0) is True
