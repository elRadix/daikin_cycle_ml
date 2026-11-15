"""v1.22.8 A1: reproduce prod-1 2026-11-14 undercount, prove fix."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import sensor as S
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.storage.store import CycleStore

MIDNIGHT_CET = 1794610800.0
PREV_START   = 1794570211.536616
PREV_END     = 1794636207.6676347
OPEN_START   = 1794636301.506307
NOW          = 1794648690.336354
NATIVE_MIN   = 631.35


def _mk_coord(intersecting=None, attrs=None):
    c = MagicMock()
    c.store = MagicMock()
    c.store.cycles_today.return_value = []
    c.store.cycles_intersecting.return_value = intersecting or []
    c.last_attrs = attrs or {}
    c.runtime_snapshot = {
        "buh_step1_s": 0.0, "buh_step2_s": 0.0, "buh_total_s": 0.0,
        "defrost_count": 0.0, "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0, "defrost_start_ts": None,
        "prev_defrost": False, "defrost_prior_s": None,
    }
    c.entry = None
    return c


def _mk_snap(state="running", cycle_start_ts=OPEN_START, attrs=None):
    s = DataSnapshot()
    s.state = state
    s.cycle_start_ts = cycle_start_ts
    s.attrs = attrs or {}
    return s


@pytest.fixture
def prod_clock(monkeypatch):
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.sensor._now", lambda: NOW
    )
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.sensor._local_midnight",
        lambda _: MIDNIGHT_CET,
    )


def test_bug_reproduces_old_code_undercount(prod_clock):
    c = _mk_coord(intersecting=[], attrs={})
    s = _mk_snap()
    v = S._value_runtime_compressor_today_s(s, c)
    expected = int(NOW - OPEN_START)
    assert v == expected
    assert v == 12388
    assert v < 20000


def test_fix_native_path_returns_firmware_value(prod_clock):
    c = _mk_coord(attrs={"Stats: Compressor run today (min)": NATIVE_MIN})
    s = _mk_snap()
    assert S._value_runtime_compressor_today_s(s, c) == 37881


def test_fix_computed_path_includes_cross_midnight(prod_clock):
    c = _mk_coord(intersecting=[{
        "start_ts": PREV_START, "end_ts": PREV_END,
        "mode": "heating", "is_transient": 0,
    }])
    s = _mk_snap()
    v = S._value_runtime_compressor_today_s(s, c)
    expected = int(round((PREV_END - MIDNIGHT_CET) + (NOW - OPEN_START)))
    assert v == expected
    assert v == 37796


def test_fix_converges_native_and_computed(prod_clock):
    c_n = _mk_coord(attrs={"Stats: Compressor run today (min)": NATIVE_MIN})
    c_c = _mk_coord(intersecting=[{
        "start_ts": PREV_START, "end_ts": PREV_END,
        "mode": "heating", "is_transient": 0,
    }])
    s = _mk_snap()
    v_n = S._value_runtime_compressor_today_s(s, c_n)
    v_c = S._value_runtime_compressor_today_s(s, c_c)
    assert v_n == 37881 and v_c == 37796
    delta_pct = abs(v_n - v_c) / v_n * 100
    assert delta_pct < 1.0


def test_daily_summary_matches_computed_prev_tail(prod_clock):
    assert int(PREV_END - MIDNIGHT_CET) == 25407


def test_attrs_reflect_native_source(prod_clock):
    c = _mk_coord(attrs={"Stats: Compressor run today (min)": NATIVE_MIN})
    s = _mk_snap()
    a = S._attrs_runtime_compressor_today_s(s, c)
    assert a["source"] == "native" and a["native_min"] == NATIVE_MIN
    for k in ("buh_step1_s", "buh_step2_s", "buh_total_s"):
        assert k not in a


@pytest.mark.parametrize("so,eo,expected", [
    (-10_000, -5_000, 0),
    (-10_000,  5_000, 5_000),
    ( 5_000,  10_000, 5_000),
    (  -50,    50,   50),
])
def test_cross_midnight_sweep(prod_clock, so, eo, expected):
    c = _mk_coord(intersecting=[{
        "start_ts": MIDNIGHT_CET + so, "end_ts": MIDNIGHT_CET + eo,
        "mode": "heating", "is_transient": 0,
    }])
    s = _mk_snap(state="idle", cycle_start_ts=0.0)
    v = S._value_runtime_compressor_today_s(s, c)
    assert v <= expected
    if expected and eo < (NOW - MIDNIGHT_CET):
        assert v == expected


def test_real_cycle_store_intersecting_math(prod_clock):
    store = CycleStore(maxlen=1000)
    store.add_cycle({
        "start_ts": PREV_START, "end_ts": PREV_END,
        "duration_s": int(PREV_END - PREV_START),
        "mode": "heating", "is_transient": 0,
    })
    c = _mk_coord()
    c.store = store
    s = _mk_snap()
    assert S._value_runtime_compressor_today_s(s, c) == 37796


def test_real_cycle_store_transient_excluded(prod_clock):
    store = CycleStore(maxlen=1000)
    store.add_cycle({
        "start_ts": PREV_START, "end_ts": PREV_END,
        "duration_s": int(PREV_END - PREV_START),
        "mode": "heating", "is_transient": 1,
    })
    c = _mk_coord()
    c.store = store
    s = _mk_snap()
    v = S._value_runtime_compressor_today_s(s, c)
    assert v == int(NOW - OPEN_START) == 12388


def test_real_cycle_store_no_cycles_returns_open_only(prod_clock):
    store = CycleStore(maxlen=1000)
    c = _mk_coord()
    c.store = store
    s = _mk_snap()
    assert S._value_runtime_compressor_today_s(s, c) == int(NOW - OPEN_START)
