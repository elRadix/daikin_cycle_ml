"""v1.22.8: runtime_compressor_today native-first + cross-midnight fix."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.sensor import (
    _attrs_runtime_compressor_today_s,
    _local_midnight,
    _value_runtime_compressor_today_s,
)


def _mk_coord(intersecting=None, native_attrs=None):
    c = MagicMock()
    c.store = MagicMock()
    c.store.cycles_intersecting.return_value = intersecting or []
    c.last_attrs = native_attrs or {}
    c.runtime_snapshot = {
        "buh_step1_s": 0.0, "buh_step2_s": 0.0, "buh_total_s": 0.0,
        "defrost_count": 0.0, "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0, "defrost_start_ts": None,
        "prev_defrost": False, "defrost_prior_s": None,
    }
    return c


def _mk_snap(**over):
    s = DataSnapshot()
    s.state = over.get("state", "idle")
    s.cycle_start_ts = over.get("cycle_start_ts", 0.0)
    s.attrs = over.get("attrs", {})
    return s


# ─── native-first ───

def test_native_wins_when_stats_present():
    c = _mk_coord(native_attrs={"Stats: Compressor run today (min)": 631.35})
    s = _mk_snap()
    v = _value_runtime_compressor_today_s(s, c)
    assert v == round(631.35 * 60) == 37881


def test_native_overrides_computed_when_both_available():
    now = time.time()
    c = _mk_coord(
        native_attrs={"Stats: Compressor run today (min)": 100.0},
        intersecting=[
            {"start_ts": now - 3600, "end_ts": now - 3500, "mode": "heating",
             "is_transient": 0},
        ],
    )
    s = _mk_snap()
    assert _value_runtime_compressor_today_s(s, c) == 6000  # 100 min


def test_native_invalid_string_falls_back():
    for bad in ("", "unknown", "unavailable", "---", "null"):
        c = _mk_coord(native_attrs={"Stats: Compressor run today (min)": bad})
        s = _mk_snap()
        assert _value_runtime_compressor_today_s(s, c) == 0


def test_native_negative_rejected():
    c = _mk_coord(native_attrs={"Stats: Compressor run today (min)": -5})
    s = _mk_snap()
    assert _value_runtime_compressor_today_s(s, c) == 0


def test_native_magicmock_attrs_rejected():
    c = _mk_coord()
    s = _mk_snap()
    s.attrs = MagicMock()  # NOT a dict — _read_float guards
    assert _value_runtime_compressor_today_s(s, c) == 0


# ─── computed fallback: cross-midnight ───

def test_cross_midnight_cycle_tail_counted():
    """Cycle started yesterday, ended 2h after midnight → today = 2h only."""
    now = time.time()
    midnight = _local_midnight(now)
    two_h_after = midnight + 7200
    c = _mk_coord(
        intersecting=[
            {"start_ts": midnight - 3600, "end_ts": two_h_after,
             "mode": "heating", "is_transient": 0},
        ],
    )
    s = _mk_snap()
    v = _value_runtime_compressor_today_s(s, c)
    # Overlap = min(two_h_after, now) - max(start, midnight)
    expected = min(two_h_after, now) - midnight
    assert v == int(expected)


def test_transient_cycles_excluded_by_intersecting():
    """cycles_intersecting(exclude_transient=True) is the store's contract;
    sensor trusts it. Verify a transient-flagged cycle in the returned list
    is filtered by store, not sensor."""
    now = time.time()
    midnight = _local_midnight(now)
    c = _mk_coord(
        intersecting=[],  # store already filtered
    )
    s = _mk_snap()
    assert _value_runtime_compressor_today_s(s, c) == 0


def test_open_cycle_portion_only_today():
    """Open cycle started yesterday: only today-portion counted."""
    now = time.time()
    midnight = _local_midnight(now)
    c = _mk_coord()
    s = _mk_snap(state="running", cycle_start_ts=midnight - 7200)
    v = _value_runtime_compressor_today_s(s, c)
    # open-portion from midnight to now
    assert v == int(now - midnight)


def test_open_cycle_started_today_full_count():
    now = time.time()
    midnight = _local_midnight(now)
    c = _mk_coord()
    s = _mk_snap(state="running", cycle_start_ts=midnight + 600)
    v = _value_runtime_compressor_today_s(s, c)
    assert v == int(now - (midnight + 600))


def test_attrs_has_source_and_native_min():
    c = _mk_coord(native_attrs={"Stats: Compressor run today (min)": 30.0})
    s = _mk_snap()
    a = _attrs_runtime_compressor_today_s(s, c)
    assert a["source"] == "native"
    assert a["native_min"] == 30.0


def test_attrs_computed_source_when_native_absent():
    c = _mk_coord()
    s = _mk_snap()
    a = _attrs_runtime_compressor_today_s(s, c)
    assert a["source"] == "computed"
    assert a["native_min"] is None


# ─── BUH leak regression guard ───

def test_attrs_no_buh_leak():
    """v1.22.8: BUH fields must NOT appear on compressor sensor attrs."""
    c = _mk_coord()
    s = _mk_snap()
    a = _attrs_runtime_compressor_today_s(s, c)
    assert "buh_step1_s" not in a
    assert "buh_step2_s" not in a
    assert "buh_total_s" not in a
    assert "buh_energy_kwh_est" not in a


def test_attrs_cycle_count_start_ts_rule():
    """cycle_count counts only cycles whose START is today (rollup rule)."""
    now = time.time()
    midnight = _local_midnight(now)
    c = _mk_coord(
        intersecting=[
            {"start_ts": midnight - 3600, "end_ts": midnight + 600,
             "mode": "heating", "is_transient": 0},  # started yesterday
            {"start_ts": midnight + 1200, "end_ts": midnight + 1800,
             "mode": "dhw", "is_transient": 0},      # started today
        ],
    )
    s = _mk_snap()
    a = _attrs_runtime_compressor_today_s(s, c)
    assert a["cycle_count"] == 1  # only today-started cycle
