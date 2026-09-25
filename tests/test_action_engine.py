"""Tests for engine.action_engine (Batch 7c)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.action_engine import (
    CAT_ANOMALY,
    CAT_EFFICIENCY,
    CAT_PATTERN,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MED,
    ActionAdvice,
    generate_advice,
)
from custom_components.daikin_cycle_ml.engine.anomaly_engine import (
    AnomalyResult,
    SEV_CRITICAL,
    SEV_NORMAL,
    SEV_WARN,
)


def _anom(sev=SEV_WARN, is_a=True, top=0, z=3.0):
    return AnomalyResult(
        is_anomaly=is_a, severity=sev, max_abs_z=z,
        top_dim=top, top_dim_value=0.0, message="test",
    )


# ---------- basic shape ----------

def test_generate_advice_returns_list():
    assert isinstance(generate_advice(None, {}), list)


def test_generate_advice_empty_input():
    assert generate_advice(None, {}, None, {}) == []


def test_generate_advice_never_raises_on_bad_input():
    # bad anomaly object (no attrs) still returns list
    assert generate_advice(object(), None, None, None) == []


def test_advice_to_dict_roundtrip():
    a = ActionAdvice(
        priority=1, category="x", code="y",
        title="t", description="d",
    )
    d = a.to_dict()
    assert d["priority"] == 1
    assert d["code"] == "y"


# ---------- anomaly-driven ----------

def test_anomaly_duration_creates_advice():
    out = generate_advice(_anom(top=0), {})
    codes = {a.code for a in out}
    assert "anomaly_duration" in codes


def test_anomaly_rps_max_creates_advice():
    # rps_max is index 3 in FEATURE_NAMES
    out = generate_advice(_anom(top=3), {})
    codes = {a.code for a in out}
    assert "anomaly_rps" in codes


def test_anomaly_dt_creates_advice():
    # dT_max is index 1
    out = generate_advice(_anom(top=1), {})
    codes = {a.code for a in out}
    assert "anomaly_dt" in codes


def test_anomaly_no_flag_no_advice():
    out = generate_advice(_anom(is_a=False, sev=SEV_NORMAL), {})
    codes = {a.code for a in out}
    assert not any(c.startswith("anomaly_") for c in codes)


def test_anomaly_top_dim_none_no_advice():
    out = generate_advice(_anom(top=None), {})
    codes = {a.code for a in out}
    assert not any(c.startswith("anomaly_") for c in codes)


def test_critical_anomaly_priority_high():
    out = generate_advice(_anom(sev=SEV_CRITICAL, top=0), {})
    a = next(x for x in out if x.code == "anomaly_duration")
    assert a.priority == PRIORITY_HIGH
    assert "Critical" in a.title


def test_outdoor_temp_anomaly_priority_low():
    # outdoor_temp is index 5
    out = generate_advice(_anom(top=5), {})
    a = next(x for x in out if x.code == "anomaly_outdoor")
    assert a.priority == PRIORITY_LOW


# ---------- record-driven ----------

def test_buh_used_creates_advice():
    out = generate_advice(None, {"buh_used": 1})
    codes = {a.code for a in out}
    assert "buh_used" in codes


def test_defrost_used_creates_advice():
    out = generate_advice(None, {"defrost_used": 1})
    assert any(a.code == "defrost_used" for a in out)


def test_short_cycle_pattern():
    out = generate_advice(None, {"duration_s": 300},
                          options={"short_run_threshold_min": 20})
    assert any(a.code == "short_cycle_pattern" for a in out)


def test_low_dt_pattern():
    out = generate_advice(None, {"dT_max": 2.0},
                          options={"good_dt_threshold_k": 5.0})
    assert any(a.code == "low_dt" for a in out)


# ---------- mode context ----------

def test_mode_suffix_in_title():
    out = generate_advice(None, {"buh_used": 1}, mode="DHW")
    a = next(x for x in out if x.code == "buh_used")
    assert "DHW" in a.title


def test_no_mode_suffix_when_unknown():
    out = generate_advice(None, {"buh_used": 1}, mode="UnknownMode")
    a = next(x for x in out if x.code == "buh_used")
    assert "DHW" not in a.title


# ---------- ordering + dedupe ----------

def test_advice_sorted_by_priority():
    # duration anomaly = HIGH, defrost = LOW
    out = generate_advice(
        _anom(sev=SEV_CRITICAL, top=0),
        {"defrost_used": 1},
    )
    priorities = [a.priority for a in out]
    assert priorities == sorted(priorities)


def test_advice_no_duplicates_by_code():
    out = generate_advice(
        _anom(sev=SEV_CRITICAL, top=0),
        {"buh_used": 1, "duration_s": 100},
    )
    codes = [a.code for a in out]
    assert len(codes) == len(set(codes))


def test_categories_assigned():
    out = generate_advice(
        _anom(sev=SEV_WARN, top=0),
        {"buh_used": 1, "duration_s": 100},
    )
    cats = {a.category for a in out}
    assert CAT_ANOMALY in cats
    assert CAT_EFFICIENCY in cats
    assert CAT_PATTERN in cats
