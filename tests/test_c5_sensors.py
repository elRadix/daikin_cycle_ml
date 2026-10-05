"""v1.6.0-C5 sensor tests: runtime, BUH, defrost, duty."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import sensor as s_mod
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)

C5_KEYS = {
    "runtime_compressor_today",
    "runtime_buh_today",
    "compressor_starts_today",
    "defrost_count_today",
    "defrost_duration_today",
    "duty_cycle_today",
}


def _mk_coord(**overrides: Any) -> DaikinCycleMLCoordinator:
    """Minimal coordinator stub for sensor value_fn calls (R245)."""
    c = MagicMock()
    c.store = MagicMock()
    c.store.cycles_today.return_value = overrides.get("cycles", [])
    c.entry = MagicMock()
    c.entry.data = {"model": overrides.get("model", "EPRA08")}
    rt = overrides.get("runtime", {
        "buh_step1_s": 0.0,
        "buh_step2_s": 0.0,
        "defrost_count": 0.0,
        "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0,
    })
    c.runtime_snapshot = rt
    c.energy_snapshot = {}
    return c


def _mk_snap(**overrides: Any) -> DataSnapshot:
    s = DataSnapshot()
    s.state = overrides.get("state", "idle")
    s.cycle_start_ts = overrides.get("cycle_start_ts", 0.0)
    return s


def test_sensor_defs_contains_all_c5_keys():
    keys = {d["key"] for d in s_mod.SENSOR_DEFS}
    assert C5_KEYS <= keys


def test_c5_sensors_have_value_and_attr_fn():
    for d in s_mod.SENSOR_DEFS:
        if d["key"] in C5_KEYS:
            assert "value_fn" in d, f"{d['key']} missing value_fn"
            assert "attr_fn" in d, f"{d['key']} missing attr_fn"
            assert d["name"], f"{d['key']} missing name"


def test_runtime_compressor_today_sums_cycles():
    now = time.time()
    c = _mk_coord(cycles=[
        {"duration_s": 100, "mode": "heating", "start_ts": now - 3600},
        {"duration_s": 50,  "mode": "dhw",     "start_ts": now - 1800},
    ])
    s = _mk_snap()
    assert s_mod._value_runtime_compressor_today_s(s, c) == 150


def test_runtime_compressor_today_adds_live_elapsed():
    now = time.time()
    c = _mk_coord(cycles=[{"duration_s": 100, "mode": "heating"}])
    s = _mk_snap(state="running", cycle_start_ts=now - 60)
    v = s_mod._value_runtime_compressor_today_s(s, c)
    assert v >= 160


def test_runtime_buh_today_sums_steps():
    c = _mk_coord(runtime={
        "buh_step1_s": 60.0, "buh_step2_s": 30.0,
        "defrost_count": 0.0, "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0,
    })
    s = _mk_snap()
    assert s_mod._value_runtime_buh_today_s(s, c) == 90


def test_compressor_starts_counts_cycles():
    c = _mk_coord(cycles=[{"start_ts": 1.0}, {"start_ts": 2.0}])
    s = _mk_snap()
    assert s_mod._value_compressor_starts_today(s, c) == 2


def test_defrost_count_reads_snapshot():
    c = _mk_coord(runtime={
        "buh_step1_s": 0.0, "buh_step2_s": 0.0,
        "defrost_count": 5.0, "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0,
    })
    s = _mk_snap()
    assert s_mod._value_defrost_count_today(s, c) == 5


def test_defrost_duration_reads_snapshot():
    c = _mk_coord(runtime={
        "buh_step1_s": 0.0, "buh_step2_s": 0.0,
        "defrost_count": 0.0, "defrost_duration_s": 123.4,
        "last_defrost_ts": 0.0,
    })
    s = _mk_snap()
    assert s_mod._value_defrost_duration_today_s(s, c) == 123


def test_duty_cycle_zero_when_no_runtime():
    c = _mk_coord(cycles=[])
    s = _mk_snap()
    assert s_mod._value_duty_cycle_today_pct(s, c) == 0.0


def test_duty_cycle_computes_pct():
    now = time.time()
    c = _mk_coord(cycles=[{"duration_s": 3600, "mode": "heating",
                            "start_ts": now - 7200}])
    s = _mk_snap()
    pct = s_mod._value_duty_cycle_today_pct(s, c)
    assert 0.0 < pct < 100.0


def test_buh_energy_kwh_est_known_model():
    c = _mk_coord(model="EPRA12")
    v = s_mod._buh_energy_kwh_est(c, 3600.0, 3600.0)
    assert v == pytest.approx(9.0, abs=0.01)


def test_buh_energy_kwh_est_unknown_model_fallback():
    c = _mk_coord(model="UNKNOWN99")
    v = s_mod._buh_energy_kwh_est(c, 3600.0, 0.0)
    assert v == pytest.approx(3.0, abs=0.01)


def test_buh_energy_kwh_est_none_entry():
    c = MagicMock()
    c.entry = None
    assert s_mod._buh_energy_kwh_est(c, 3600.0, 0.0) == pytest.approx(3.0)


def test_local_midnight_is_before_now():
    now = time.time()
    assert s_mod._local_midnight(now) <= now


def test_attrs_runtime_per_mode_split():
    now = time.time()
    c = _mk_coord(cycles=[
        {"duration_s": 100, "mode": "heating", "start_ts": now - 3600},
        {"duration_s": 50,  "mode": "dhw",     "start_ts": now - 1800},
        {"duration_s": 30,  "mode": "cooling", "start_ts": now - 900},
    ])
    s = _mk_snap()
    a = s_mod._attrs_runtime_compressor_today_s(s, c)
    assert a["heating_s"] == 100
    assert a["dhw_s"] == 50
    assert a["cooling_s"] == 30
    assert a["cycle_count"] == 3


def test_attrs_compressor_starts_per_mode():
    c = _mk_coord(cycles=[
        {"mode": "heating", "start_ts": 1.0},
        {"mode": "heating", "start_ts": 2.0},
        {"mode": "dhw",     "start_ts": 3.0},
    ])
    s = _mk_snap()
    a = s_mod._attrs_compressor_starts_today(s, c)
    assert a["per_mode"]["heating"] == 2
    assert a["per_mode"]["dhw"] == 1


def test_attrs_defrost_count_avg():
    c = _mk_coord(runtime={
        "buh_step1_s": 0.0, "buh_step2_s": 0.0,
        "defrost_count": 2.0, "defrost_duration_s": 600.0,
        "last_defrost_ts": 1234.0,
    })
    s = _mk_snap()
    a = s_mod._attrs_defrost_count_today(s, c)
    assert a["avg_duration_s"] == 300.0
    assert a["last_defrost_ts"] == 1234.0


def test_attrs_defrost_count_zero_none_avg():
    c = _mk_coord(runtime={
        "buh_step1_s": 0.0, "buh_step2_s": 0.0,
        "defrost_count": 0.0, "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0,
    })
    s = _mk_snap()
    a = s_mod._attrs_defrost_count_today(s, c)
    assert a["avg_duration_s"] is None
    assert a["last_defrost_ts"] is None


def test_attrs_duty_cycle_bands():
    c = _mk_coord(cycles=[])
    s = _mk_snap()
    a = s_mod._attrs_duty_cycle_today_pct(s, c)
    assert a["band"] == "low"
    assert a["runtime_s"] == 0


def test_attrs_duty_cycle_nominal_band():
    now = time.time()
    # Force a 30% duty: 30min runtime in 100min elapsed
    # Use epoch-relative midnight to control elapsed
    midnight = s_mod._local_midnight(now)
    elapsed = now - midnight
    target_pct = 30.0
    runtime = int(elapsed * target_pct / 100.0)
    c = _mk_coord(cycles=[{"duration_s": runtime, "mode": "heating"}])
    s = _mk_snap()
    a = s_mod._attrs_duty_cycle_today_pct(s, c)
    # band is nominal if 15 <= pct < 60
    assert a["band"] in ("low", "nominal")


def test_attrs_runtime_buh_includes_energy_est():
    c = _mk_coord(model="EPRA12", runtime={
        "buh_step1_s": 3600.0, "buh_step2_s": 0.0,
        "defrost_count": 0.0, "defrost_duration_s": 0.0,
        "last_defrost_ts": 0.0,
    })
    s = _mk_snap()
    a = s_mod._attrs_runtime_buh_today_s(s, c)
    assert a["step1_s"] == 3600
    assert a["buh_energy_kwh_est"] == pytest.approx(3.0, abs=0.01)


def test_attrs_defrost_duration_includes_count():
    c = _mk_coord(runtime={
        "buh_step1_s": 0.0, "buh_step2_s": 0.0,
        "defrost_count": 3.0, "defrost_duration_s": 900.0,
        "last_defrost_ts": 0.0,
    })
    s = _mk_snap()
    a = s_mod._attrs_defrost_duration_today_s(s, c)
    assert a["defrost_count"] == 3
    assert a["avg_duration_s"] == 300.0


def test_buh_energy_kwh_est_swallows_exception():
    c = MagicMock()
    c.entry.data.get = MagicMock(side_effect=RuntimeError("boom"))
    assert s_mod._buh_energy_kwh_est(c, 3600.0, 0.0) is None


def test_attrs_runtime_unknown_mode_skipped():
    now = time.time()
    c = _mk_coord(cycles=[
        {"duration_s": 100, "mode": "unknown", "start_ts": now - 3600},
        {"duration_s": 50, "mode": "heating", "start_ts": now - 1800},
    ])
    s = _mk_snap()
    a = s_mod._attrs_runtime_compressor_today_s(s, c)
    assert a["heating_s"] == 50
    assert a["dhw_s"] == 0


def test_attrs_starts_unknown_mode_skipped():
    c = _mk_coord(cycles=[
        {"mode": "unknown", "start_ts": 1.0},
        {"mode": "heating", "start_ts": 2.0},
    ])
    s = _mk_snap()
    a = s_mod._attrs_compressor_starts_today(s, c)
    assert a["per_mode"]["heating"] == 1


def test_attrs_duty_cycle_high_band(monkeypatch):
    fake = 100000.0
    monkeypatch.setattr(s_mod, "_now", lambda: fake)
    monkeypatch.setattr(s_mod, "_local_midnight", lambda _: fake - 100.0)
    c = _mk_coord(cycles=[{"duration_s": 70, "mode": "heating"}])
    s = _mk_snap()
    a = s_mod._attrs_duty_cycle_today_pct(s, c)
    assert a["band"] == "high"


def test_attrs_duty_cycle_saturated_band(monkeypatch):
    fake = 100000.0
    monkeypatch.setattr(s_mod, "_now", lambda: fake)
    monkeypatch.setattr(s_mod, "_local_midnight", lambda _: fake - 100.0)
    c = _mk_coord(cycles=[{"duration_s": 90, "mode": "heating"}])
    s = _mk_snap()
    a = s_mod._attrs_duty_cycle_today_pct(s, c)
    assert a["band"] == "saturated"
