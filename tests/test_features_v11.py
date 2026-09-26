"""Tests voor 11-dim feature-vector (batch 14c-1)."""

from __future__ import annotations

from custom_components.daikin_cycle_ml.ml import features as F


CYCLE_BASE = {
    "duration_s": 600,
    "dT_max": 5.0,
    "dT_avg": 3.0,
    "rps_max": 40,
    "rps_avg": 30.0,
    "outdoor_temp": 7.0,
    "buh_used": 0,
    "defrost_used": 0,
}


def test_vector_len_is_12():
    assert F.VECTOR_LEN == 12


def test_vector_len_legacy_is_8():
    assert F.VECTOR_LEN_LEGACY == 8


def test_feature_names_contains_new_dims():
    assert "cop_avg" in F.FEATURE_NAMES
    assert "lwt_avg" in F.FEATURE_NAMES
    assert "indoor_temp_avg" in F.FEATURE_NAMES


def test_extract_legacy_call_zero_fills():
    v = F.extract_feature_vector(dict(CYCLE_BASE))
    assert len(v) == 12
    assert v[8] == 0.0
    assert v[9] == 0.0
    assert v[10] == 0.0


def test_extract_with_cop():
    v = F.extract_feature_vector(dict(CYCLE_BASE), cop_avg=3.2)
    assert v[8] == 3.2
    assert v[9] == 0.0
    assert v[10] == 0.0


def test_extract_with_all_extra():
    v = F.extract_feature_vector(
        dict(CYCLE_BASE),
        cop_avg=3.2,
        lwt_avg=35.0,
        indoor_temp_avg=21.0,
    )
    assert v[8] == 3.2
    assert v[9] == 35.0
    assert v[10] == 21.0


def test_extract_first_8_dims_unchanged():
    v = F.extract_feature_vector(
        dict(CYCLE_BASE), cop_avg=3.2, lwt_avg=35.0, indoor_temp_avg=21.0
    )
    assert v[0] == 600
    assert v[1] == 5.0
    assert v[2] == 3.0
    assert v[3] == 40
    assert v[4] == 30.0
    assert v[5] == 7.0
    assert v[6] == 0
    assert v[7] == 0


def test_is_valid_record_legacy_ok():
    assert F.is_valid_record(dict(CYCLE_BASE)) is True


def test_is_valid_record_missing_required():
    bad = dict(CYCLE_BASE)
    del bad["duration_s"]
    assert F.is_valid_record(bad) is False


def test_extract_many_length():
    rows = [dict(CYCLE_BASE), dict(CYCLE_BASE)]
    out = F.extract_many(rows)
    assert len(out) == 2
    assert len(out[0]) == 12
