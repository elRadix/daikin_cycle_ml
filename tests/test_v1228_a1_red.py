"""v1.22.8 A1 red-team: negative/edge paths for compressor runtime."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import sensor as S
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.engine.runtime_source import _read_float


def _mk_coord(attrs=None, cycles=None):
    c = MagicMock()
    c.store = MagicMock()
    c.store.cycles_today.return_value = []
    c.store.cycles_intersecting.return_value = cycles or []
    c.last_attrs = attrs or {}
    c.runtime_snapshot = {
        "buh_step1_s": 0.0, "buh_step2_s": 0.0, "buh_total_s": 0.0,
        "defrost_count": 0.0, "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0, "defrost_start_ts": None,
        "prev_defrost": False, "defrost_prior_s": None,
    }
    c.entry = None
    return c


def _mk_snap(**over):
    s = DataSnapshot()
    s.state = over.get("state", "idle")
    s.cycle_start_ts = over.get("cycle_start_ts", 0.0)
    s.attrs = over.get("attrs", {})
    return s


@pytest.mark.parametrize("raw", [True, False])
def test_read_float_rejects_bool(raw):
    assert _read_float({"k": raw}, "k") is None


@pytest.mark.parametrize("raw", [
    None, "", "   ", "unknown", "unavailable", "---", "null", "none",
    "N/A", "NaN", "inf", "-inf", -1, -0.5, -1e6,
])
def test_read_float_rejects_invalid(raw):
    assert _read_float({"k": raw}, "k") is None


@pytest.mark.parametrize("raw", [0, 0.0, 1, 1.5, "1.5", "0"])
def test_read_float_accepts_valid(raw):
    v = _read_float({"k": raw}, "k")
    assert v is not None and v >= 0.0


def test_read_float_rejects_non_dict():
    for x in (None, "string", [], MagicMock()):
        assert _read_float(x, "k") is None


def test_value_survives_store_exception():
    c = _mk_coord()
    c.store.cycles_intersecting.side_effect = Exception("DB down")
    s = _mk_snap()
    v = S._value_runtime_compressor_today_s(s, c)
    assert isinstance(v, int) and v == 0


def test_attrs_survives_store_exception():
    c = _mk_coord()
    c.store.cycles_intersecting.side_effect = Exception("DB down")
    s = _mk_snap()
    a = S._attrs_runtime_compressor_today_s(s, c)
    assert a["source"] == "computed" and a["heating_s"] == 0


def test_value_survives_store_returning_none():
    c = _mk_coord()
    c.store.cycles_intersecting.return_value = None
    s = _mk_snap()
    try:
        v = S._value_runtime_compressor_today_s(s, c)
        assert v == 0
    except TypeError:
        pytest.fail("sensor crashed on store returning None")


@pytest.mark.parametrize("bad_record", [
    {"start_ts": "not-a-number", "end_ts": 100.0},
    {"start_ts": 100.0, "end_ts": "not-a-number"},
    {"start_ts": None, "end_ts": 100.0},
    {"start_ts": 100.0, "end_ts": None},
    {"start_ts": [1, 2], "end_ts": {}},
    {"mode": "heating"},
    {},
])
def test_value_skips_malformed_cycle(bad_record):
    now = time.time()
    c = _mk_coord(cycles=[bad_record, {
        "start_ts": now - 100, "end_ts": now - 50,
        "mode": "heating", "is_transient": 0,
    }])
    s = _mk_snap()
    assert isinstance(S._value_runtime_compressor_today_s(s, c), int)


def test_attrs_skip_malformed_cycle():
    c = _mk_coord(cycles=[{"start_ts": "bad", "end_ts": 100.0}])
    s = _mk_snap()
    a = S._attrs_runtime_compressor_today_s(s, c)
    assert a["source"] == "computed" and a["cycle_count"] == 0


@pytest.mark.parametrize("bad_attrs", [None, [], "string", 42, True])
def test_value_survives_bad_attrs_type(bad_attrs):
    c = _mk_coord()
    c.last_attrs = bad_attrs
    s = _mk_snap()
    assert isinstance(S._value_runtime_compressor_today_s(s, c), int)


def test_attrs_survives_both_sides_magicmock():
    c = _mk_coord()
    c.last_attrs = MagicMock()
    s = _mk_snap()
    s.attrs = MagicMock()
    a = S._attrs_runtime_compressor_today_s(s, c)
    assert a["source"] == "computed" and a["native_min"] is None


def test_open_cycle_start_in_future_ignored():
    now = time.time()
    c = _mk_coord()
    s = _mk_snap(state="running", cycle_start_ts=now + 1000)
    assert S._value_runtime_compressor_today_s(s, c) == 0


def test_open_cycle_start_zero_ignored():
    c = _mk_coord()
    s = _mk_snap(state="running", cycle_start_ts=0.0)
    assert S._value_runtime_compressor_today_s(s, c) == 0


def test_open_cycle_negative_start_ignored():
    c = _mk_coord()
    s = _mk_snap(state="running", cycle_start_ts=-1000.0)
    assert S._value_runtime_compressor_today_s(s, c) == 0


@pytest.mark.parametrize("garbage", [
    "", "  ", "unknown", "unavailable", "---", "null", "none",
    "N/A", "NaN", "inf", "-inf", -100, -0.001,
    True, False, None,
])
def test_native_garbage_falls_back(garbage):
    c = _mk_coord(attrs={"Stats: Compressor run today (min)": garbage})
    s = _mk_snap()
    v = S._value_runtime_compressor_today_s(s, c)
    a = S._attrs_runtime_compressor_today_s(s, c)
    assert v == 0 and a["source"] == "computed" and a["native_min"] is None


def test_huge_native_does_not_crash():
    c = _mk_coord(attrs={"Stats: Compressor run today (min)": 1e10})
    s = _mk_snap()
    assert S._value_runtime_compressor_today_s(s, c) == int(round(1e10 * 60))


def test_massive_cycle_overlap_bounded():
    now = time.time()
    c = _mk_coord(cycles=[{
        "start_ts": now - 10 * 365 * 86400,
        "end_ts": now + 1000,
        "mode": "heating", "is_transient": 0,
    }])
    s = _mk_snap()
    v = S._value_runtime_compressor_today_s(s, c)
    assert v <= int(now)


def test_loop_skips_cycle_with_negative_overlap():
    """Covers sensor.py:962->966 branch (ov <= 0 within loop body).

    cycles_intersecting filter accepts cycles where end > start_window AND
    start < end_window. A malformed cycle with end < start still passes
    those checks, but ov = min(end,now)-max(start,midnight) becomes negative.
    Verifies the attrs fn continues to line 966 without adding to by_mode.
    """
    now = time.time()
    c = _mk_coord(cycles=[{
        "start_ts": now - 50, "end_ts": now - 100,
        "mode": "heating", "is_transient": 0,
    }])
    s = _mk_snap()
    a = S._attrs_runtime_compressor_today_s(s, c)
    assert a["heating_s"] == 0
    assert a["source"] == "computed"
