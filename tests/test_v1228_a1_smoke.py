"""v1.22.8 A1 smoke: end-to-end counter entity sanity."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import sensor as S
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot

COUNTER_KEYS = {
    "runtime_buh_today", "runtime_compressor_today",
    "compressor_starts_today", "defrost_count_today",
    "defrost_duration_today", "duty_cycle_today",
    "cycles_today", "quality_today",
}
NATIVE_AWARE_KEYS = {
    "runtime_buh_today", "runtime_compressor_today",
    "compressor_starts_today", "defrost_count_today",
    "defrost_duration_today",
}


def _mk_coord(attrs=None, intersecting=None, cycles_today=None):
    c = MagicMock()
    c.store = MagicMock()
    c.store.cycles_today.return_value = cycles_today or []
    c.store.cycles_intersecting.return_value = intersecting or []
    c.last_attrs = attrs or {}
    c.runtime_snapshot = {
        "buh_step1_s": 0.0, "buh_step2_s": 0.0, "buh_total_s": 0.0,
        "defrost_count": 0.0, "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0, "defrost_start_ts": None,
        "prev_defrost": False, "defrost_prior_s": None,
    }
    c.entry = MagicMock()
    c.entry.data = {"model": "EPRA12"}
    c.energy_snapshot = {}
    return c


def _mk_snap(**over):
    s = DataSnapshot()
    s.state = over.get("state", "idle")
    s.cycle_start_ts = over.get("cycle_start_ts", 0.0)
    s.attrs = over.get("attrs", {})
    return s


def test_all_counter_value_fns_execute_on_empty_state():
    c = _mk_coord()
    s = _mk_snap()
    for d in S.SENSOR_DEFS:
        if d["key"] not in COUNTER_KEYS:
            continue
        vf = d.get("value_fn")
        if vf is None:
            continue
        v = vf(s, c)
        assert v is None or isinstance(v, (int, float))


def test_all_counter_attr_fns_execute_on_empty_state():
    c = _mk_coord()
    s = _mk_snap()
    for d in S.SENSOR_DEFS:
        if d["key"] not in COUNTER_KEYS:
            continue
        af = d.get("attr_fn")
        if af is None:
            continue
        assert isinstance(af(s, c), dict)


def test_native_aware_counters_all_expose_source():
    c = _mk_coord()
    s = _mk_snap()
    missing = []
    for d in S.SENSOR_DEFS:
        if d["key"] not in NATIVE_AWARE_KEYS:
            continue
        af = d.get("attr_fn")
        if af is None:
            missing.append(f"{d['key']}: no attr_fn")
            continue
        a = af(s, c)
        if "source" not in a:
            missing.append(f"{d['key']}: no source")
    assert not missing, f"Missing: {missing}"


def test_native_aware_counters_report_computed_when_no_attrs():
    c = _mk_coord()
    s = _mk_snap()
    for d in S.SENSOR_DEFS:
        if d["key"] not in NATIVE_AWARE_KEYS:
            continue
        af = d.get("attr_fn")
        if af is None:
            continue
        assert af(s, c)["source"] == "computed"


def test_native_aware_counters_report_native_when_attrs_present():
    attrs = {
        "Stats: Backup heater today (min)": 30.0,
        "Stats: Compressor run today (min)": 60.0,
        "Stats: Compressor starts today": 5,
        "Stats: Defrosts today": 2,
    }
    c = _mk_coord(attrs=attrs)
    s = _mk_snap()
    expected = {
        "runtime_buh_today": "native",
        "runtime_compressor_today": "native",
        "compressor_starts_today": "native",
        "defrost_count_today": "native",
        "defrost_duration_today": "computed",
    }
    for d in S.SENSOR_DEFS:
        if d["key"] not in expected:
            continue
        a = d["attr_fn"](s, c)
        assert a["source"] == expected[d["key"]], (
            f"{d['key']}: expected {expected[d['key']]}, got {a['source']}"
        )


def test_native_entity_values_match_firmware():
    attrs = {
        "Stats: Backup heater today (min)": 30.0,
        "Stats: Compressor run today (min)": 60.0,
        "Stats: Compressor starts today": 5,
        "Stats: Defrosts today": 2,
    }
    c = _mk_coord(attrs=attrs)
    s = _mk_snap()
    expected = {
        "runtime_buh_today": 1800,
        "runtime_compressor_today": 3600,
        "compressor_starts_today": 5,
        "defrost_count_today": 2,
    }
    for d in S.SENSOR_DEFS:
        if d["key"] not in expected:
            continue
        v = d["value_fn"](s, c)
        assert v == expected[d["key"]], (
            f"{d['key']}: expected {expected[d['key']]}, got {v}"
        )


def test_full_tick_no_exceptions():
    from custom_components.daikin_cycle_ml.storage.store import CycleStore
    store = CycleStore(maxlen=100)
    now = time.time()
    store.add_cycle({
        "start_ts": now - 5000, "end_ts": now - 2000,
        "duration_s": 3000, "mode": "heating", "is_transient": 0,
    })
    c = _mk_coord(attrs={
        "Stats: Compressor run today (min)": 100.0,
        "Stats: Backup heater today (min)": 20.0,
        "Stats: Defrosts today": 1,
        "Stats: Compressor starts today": 3,
    })
    c.store = store
    s = _mk_snap(state="running", cycle_start_ts=now - 1000)
    for d in S.SENSOR_DEFS:
        if d["key"] not in COUNTER_KEYS:
            continue
        vf = d.get("value_fn")
        if vf is None:
            continue
        v = vf(s, c)
        assert v is None or isinstance(v, (int, float))


def test_no_counter_attrs_missing_source_attribute():
    c = _mk_coord(attrs={})
    s = _mk_snap()
    valid = {"native", "computed"}
    for d in S.SENSOR_DEFS:
        if d["key"] not in NATIVE_AWARE_KEYS:
            continue
        af = d.get("attr_fn")
        if af is None:
            continue
        assert af(s, c)["source"] in valid
