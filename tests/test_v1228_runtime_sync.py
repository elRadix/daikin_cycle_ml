"""v1.22.8: BUH/defrost/starts counters — source-honest attrs sync with entity."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import sensor as S
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot


def _mk_coord(attrs=None, snap_over=None, cycles=None):
    c = MagicMock()
    c.store = MagicMock()
    c.store.cycles_today.return_value = cycles or []
    c.store.cycles_intersecting.return_value = []
    c.last_attrs = attrs or {}
    snap = {
        "buh_step1_s": 0.0, "buh_step2_s": 0.0, "buh_total_s": 0.0,
        "defrost_count": 0.0, "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0, "defrost_start_ts": None,
        "prev_defrost": False, "defrost_prior_s": None,
    }
    if snap_over:
        snap.update(snap_over)
    c.runtime_snapshot = snap
    c.entry = None
    return c


def _mk_snap(**over):
    s = DataSnapshot()
    s.state = over.get("state", "idle")
    s.cycle_start_ts = over.get("cycle_start_ts", 0.0)
    s.attrs = over.get("attrs", {})
    return s


# ─── BUH attrs ───

def test_buh_attrs_native_total_s_matches_entity():
    c = _mk_coord(
        attrs={"Stats: Backup heater today (min)": 50.0},
        snap_over={"buh_step1_s": 1000.0, "buh_step2_s": 500.0,
                   "buh_total_s": 1000.0},
    )
    s = _mk_snap()
    a = S._attrs_runtime_buh_today_s(s, c)
    v = S._value_runtime_buh_today_s(s, c)
    assert a["source"] == "native"
    assert a["total_s"] == v == 3000
    assert a["computed_total_s"] == 1000
    assert a["step_split_source"] == "computed"


def test_buh_attrs_computed_total_s_matches_entity():
    c = _mk_coord(
        snap_over={"buh_step1_s": 600.0, "buh_step2_s": 200.0,
                   "buh_total_s": 600.0},
    )
    s = _mk_snap()
    a = S._attrs_runtime_buh_today_s(s, c)
    v = S._value_runtime_buh_today_s(s, c)
    assert a["source"] == "computed"
    assert a["total_s"] == v == 600
    assert a["computed_total_s"] == 600
    assert a["native_min"] is None


def test_buh_attrs_energy_source_is_computed():
    c = _mk_coord(
        attrs={"Stats: Backup heater today (min)": 50.0},
        snap_over={"buh_step1_s": 1000.0, "buh_step2_s": 500.0,
                   "buh_total_s": 1000.0},
    )
    s = _mk_snap()
    a = S._attrs_runtime_buh_today_s(s, c)
    assert a["buh_energy_source"] == "computed"


# ─── Starts attrs ───

def test_starts_attrs_native_source():
    c = _mk_coord(
        attrs={"Stats: Compressor starts today": 12},
        cycles=[{"mode": "heating"}, {"mode": "heating"}, {"mode": "dhw"}],
    )
    s = _mk_snap()
    a = S._attrs_compressor_starts_today(s, c)
    assert a["source"] == "native"
    assert a["native_count"] == 12
    assert a["computed_count"] == 3
    assert a["per_mode_source"] == "computed"


def test_starts_attrs_computed_source():
    c = _mk_coord(cycles=[{"mode": "heating"}, {"mode": "dhw"}])
    s = _mk_snap()
    a = S._attrs_compressor_starts_today(s, c)
    assert a["source"] == "computed"
    assert a["native_count"] is None
    assert a["computed_count"] == 2


def test_starts_attrs_native_entity_matches_value_fn():
    c = _mk_coord(
        attrs={"Stats: Compressor starts today": 7},
        cycles=[{"mode": "heating"}] * 3,
    )
    s = _mk_snap()
    v = S._value_compressor_starts_today(s, c)
    a = S._attrs_compressor_starts_today(s, c)
    assert v == 7
    assert a["source"] == "native"
    assert a["native_count"] == 7


def test_starts_attrs_empty_cycles_no_exception():
    c = _mk_coord()
    s = _mk_snap()
    a = S._attrs_compressor_starts_today(s, c)
    assert a["source"] == "computed"
    assert a["computed_count"] == 0
    assert a["per_mode"] == {"heating": 0, "dhw": 0, "cooling": 0}


# ─── Defrost count attrs ───

def test_defrost_count_attrs_native():
    c = _mk_coord(
        attrs={"Stats: Defrosts today": 6},
        snap_over={"defrost_count": 4.0, "defrost_duration_s": 1800.0},
    )
    s = _mk_snap()
    a = S._attrs_defrost_count_today(s, c)
    assert a["source"] == "native"
    assert a["native_count"] == 6
    assert a["computed_count"] == 4
    assert a["avg_duration_source"] == "computed"


def test_defrost_count_attrs_computed():
    c = _mk_coord(snap_over={"defrost_count": 2.0, "defrost_duration_s": 600.0})
    s = _mk_snap()
    a = S._attrs_defrost_count_today(s, c)
    assert a["source"] == "computed"
    assert a["native_count"] is None
    assert a["computed_count"] == 2
    assert a["avg_duration_s"] == 300.0


def test_defrost_count_zero_no_division_error():
    c = _mk_coord()
    s = _mk_snap()
    a = S._attrs_defrost_count_today(s, c)
    assert a["avg_duration_s"] is None
    assert a["computed_count"] == 0


# ─── Defrost duration attrs ───

def test_defrost_duration_attrs_computed_only():
    c = _mk_coord(
        attrs={"Stats: Defrosts today": 6},
        snap_over={"defrost_count": 4.0, "defrost_duration_s": 1800.0},
    )
    s = _mk_snap()
    a = S._attrs_defrost_duration_today_s(s, c)
    assert a["source"] == "computed"
    assert a["native_available"] is False
    assert a["computed_count"] == 4
    assert a["native_count"] == 6


# ─── MagicMock guards ───

def test_all_counters_reject_magicmock_attrs():
    c = _mk_coord()
    s = _mk_snap()
    s.attrs = MagicMock()
    for fn in (
        S._value_runtime_buh_today_s,
        S._value_compressor_starts_today,
        S._value_defrost_count_today,
    ):
        v = fn(s, c)
        assert isinstance(v, int)
    for afn in (
        S._attrs_runtime_buh_today_s,
        S._attrs_compressor_starts_today,
        S._attrs_defrost_count_today,
        S._attrs_defrost_duration_today_s,
    ):
        a = afn(s, c)
        assert "source" in a


# ─── Empty-attrs + populated-last_attrs (the _resolve_attrs guarantee) ───

def test_resolve_attrs_picks_populated_side():
    c = _mk_coord(
        attrs={
            "Stats: Backup heater today (min)": 10.0,
            "Stats: Compressor starts today": 3,
            "Stats: Defrosts today": 2,
        },
    )
    s = _mk_snap()
    assert S._value_runtime_buh_today_s(s, c) == 600
    assert S._value_compressor_starts_today(s, c) == 3
    assert S._value_defrost_count_today(s, c) == 2


def test_starts_attrs_survives_store_exception():
    """Covers sensor.py:1020-1021 except-branch: store.cycles_today raises."""
    c = _mk_coord()
    c.store.cycles_today.side_effect = Exception("DB down")
    s = _mk_snap()
    a = S._attrs_compressor_starts_today(s, c)
    assert a["computed_count"] == 0
    assert a["per_mode"] == {"heating": 0, "dhw": 0, "cooling": 0}
    assert a["source"] == "computed"
