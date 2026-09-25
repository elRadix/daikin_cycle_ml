"""Tests for ml.features (Batch 7a)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.ml.features import (
    FEATURE_NAMES,
    REQUIRED_FOR_VALID,
    VECTOR_LEN,
    extract_feature_vector,
    extract_many,
    is_valid_record,
)


def _good():
    return {
        "duration_s": 3600,
        "dT_max": 7.5,
        "dT_avg": 5.2,
        "rps_max": 60,
        "rps_avg": 42.5,
        "outdoor_temp": 8.0,
        "buh_used": 0,
        "defrost_used": 0,
    }


def test_feature_names_length_matches_vector_len():
    assert len(FEATURE_NAMES) == VECTOR_LEN


def test_vector_length_fixed():
    assert len(extract_feature_vector(_good())) == VECTOR_LEN


def test_vector_values_in_order():
    v = extract_feature_vector(_good())
    assert v[0] == 3600.0
    assert v[1] == 7.5
    assert v[2] == 5.2
    assert v[3] == 60.0
    assert v[4] == 42.5
    assert v[5] == 8.0
    assert v[6] == 0.0
    assert v[7] == 0.0


def test_missing_fields_become_zero():
    v = extract_feature_vector({"duration_s": 100})
    assert v[0] == 100.0
    assert all(x == 0.0 for x in v[1:])


def test_empty_record_yields_zeros():
    v = extract_feature_vector({})
    assert v == [0.0] * VECTOR_LEN


def test_bool_true_maps_to_one():
    v = extract_feature_vector({"buh_used": True, "defrost_used": True})
    assert v[6] == 1.0
    assert v[7] == 1.0


def test_bool_false_maps_to_zero():
    v = extract_feature_vector({"buh_used": False})
    assert v[6] == 0.0


def test_string_values_become_zero():
    v = extract_feature_vector({"duration_s": "3600"})
    assert v[0] == 0.0


def test_none_values_become_zero():
    v = extract_feature_vector({"duration_s": None, "dT_max": 5.0})
    assert v[0] == 0.0
    assert v[1] == 5.0


def test_is_valid_good_record():
    assert is_valid_record(_good()) is True


def test_is_valid_missing_duration():
    r = _good()
    del r["duration_s"]
    assert is_valid_record(r) is False


def test_is_valid_missing_dt_max():
    r = _good()
    del r["dT_max"]
    assert is_valid_record(r) is False


def test_is_valid_string_field_rejected():
    r = _good()
    r["duration_s"] = "3600"
    assert is_valid_record(r) is False


def test_is_valid_empty_record():
    assert is_valid_record({}) is False


def test_required_for_valid_subset_of_names():
    assert set(REQUIRED_FOR_VALID).issubset(set(FEATURE_NAMES))


def test_extract_many_skips_invalid():
    recs = [_good(), {"duration_s": 100}, _good()]
    out = extract_many(recs)
    assert len(out) == 2


def test_extract_many_all_invalid_returns_empty():
    assert extract_many([{}, {"foo": 1}]) == []
