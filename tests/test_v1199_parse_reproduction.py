"""v1.19.9 #635 R634: real-world reproduction tests for parse helpers.

Source: phase-2 probe 2026-11-05. Every failing case below was
OBSERVED in the probe output (see commit message). These are R635
"fix immediately" cases: parsing quirks that let bad data reach
the DB aggregates (NaN, inf) or lose precision silently (EU locale).

Categories:
- _parse_float: NaN, inf, EU decimals, scientific notation
- _parse_bool: string variants ('TRUE', 'yes', '1')
"""
from __future__ import annotations

import math

import pytest

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    _parse_bool,
    _parse_float,
    parse_global_cop_attrs,
)


# ============================================================
# _parse_float: NaN / inf rejection (data-integrity critical)
# ============================================================

def test_parse_float_nan_object_returns_none():
    """R634: NaN from numpy/float prop must not leak into COP."""
    assert _parse_float(float("nan")) is None


def test_parse_float_inf_object_returns_none():
    """R634: inf must not leak into COP aggregates."""
    assert _parse_float(float("inf")) is None


def test_parse_float_neg_inf_returns_none():
    assert _parse_float(float("-inf")) is None


def test_parse_float_nan_string_returns_none():
    """Already correct, guard against regression."""
    assert _parse_float("nan") is None


def test_parse_float_inf_string_returns_none():
    """Already correct, guard against regression."""
    assert _parse_float("inf") is None


# ============================================================
# _parse_float: EU decimal ("1,5" -> 1.5 not 1.0)
# ============================================================

def test_parse_float_eu_decimal_15():
    """R634: "1,5" must become 1.5, not 1.0 (33% error)."""
    assert _parse_float("1,5") == 1.5


def test_parse_float_eu_decimal_305():
    """R634: outdoor 30,5C must not become 30.0C."""
    assert _parse_float("30,5") == 30.5


def test_parse_float_eu_decimal_negative():
    """R634: -1,5C must become -1.5, not -1.0."""
    assert _parse_float("-1,5") == -1.5


def test_parse_float_eu_decimal_multiple_commas():
    """Ambiguous "1,5,0" -> None (reject)."""
    assert _parse_float("1,5,0") is None


def test_parse_float_eu_decimal_with_thousands():
    """Ambiguous "1,500" -> None (could be 1500 or 1.5)."""
    # Too ambiguous to auto-convert; safer to reject.
    assert _parse_float("1,500") is None


# ============================================================
# _parse_float: scientific notation ("5.0e2" -> 500.0)
# ============================================================

def test_parse_float_scientific_notation():
    """R634: "5.0e2" is 500.0, not 5.0 (100x error)."""
    assert _parse_float("5.0e2") == 500.0


def test_parse_float_scientific_negative_exp():
    """0.5 = 5e-1."""
    assert _parse_float("5e-1") == 0.5


def test_parse_float_scientific_upper_e():
    assert _parse_float("1E3") == 1000.0


# ============================================================
# _parse_float: string variants (regression guards)
# ============================================================

def test_parse_float_plain_string():
    assert _parse_float("5.0") == 5.0


def test_parse_float_whitespace_stripped():
    assert _parse_float(" 5.0 ") == 5.0


def test_parse_float_int_input():
    assert _parse_float(5) == 5.0


def test_parse_float_negative():
    assert _parse_float("-1") == -1.0


def test_parse_float_none_returns_none():
    assert _parse_float(None) is None


def test_parse_float_bool_returns_none():
    """R634: bool must not coerce to 1.0/0.0 (would create phantom COP)."""
    assert _parse_float(True) is None
    assert _parse_float(False) is None


def test_parse_float_empty_string():
    assert _parse_float("") is None


def test_parse_float_garbage_string():
    assert _parse_float("abc") is None


# ============================================================
# _parse_bool: string variants ('TRUE', 'yes', '1' -> True)
# ============================================================

@pytest.mark.parametrize("value", ["ON", "on", "On", "TRUE", "True",
                                    "true", "YES", "yes", "1", "ON "])
def test_parse_bool_true_variants(value):
    """R634: all truthy string variants must return True."""
    assert _parse_bool(value) is True


@pytest.mark.parametrize("value", ["OFF", "off", "OFF ", "FALSE", "False",
                                    "false", "NO", "no", "0", ""])
def test_parse_bool_false_variants(value):
    """R634: all falsy string variants must return False."""
    assert _parse_bool(value) is False


@pytest.mark.parametrize("value", [True, 1, 2, -1])
def test_parse_bool_true_numeric_or_bool(value):
    assert _parse_bool(value) is True


@pytest.mark.parametrize("value", [False, 0, None])
def test_parse_bool_false_numeric_or_none(value):
    assert _parse_bool(value) is False


# ============================================================
# parse_global_cop_attrs integration
# ============================================================

def test_parse_sample_rejects_nan_cop():
    """R634: NaN COP must be rejected at parse level."""
    s = parse_global_cop_attrs({"state": float("nan")})
    assert s is None


def test_parse_sample_rejects_inf_cop():
    s = parse_global_cop_attrs({"state": float("inf")})
    assert s is None


def test_parse_sample_defrost_true_variants():
    """R634: R635 defrost fix regression guard."""
    for raw in ["ON", "on", True, 1]:
        s = parse_global_cop_attrs({"state": "5.0",
                                     "defrost_operation": raw})
        assert s is not None
        assert s.defrost is True, f"defrost_operation={raw!r}"


def test_parse_sample_defrost_false_variants():
    for raw in ["OFF", "off", False, 0, None, ""]:
        s = parse_global_cop_attrs({"state": "5.0",
                                     "defrost_operation": raw})
        assert s is not None
        assert s.defrost is False, f"defrost_operation={raw!r}"


def test_parse_sample_eu_decimal_outdoor():
    """R634: outdoor "10,5" must parse to 10.5, not 10.0."""
    s = parse_global_cop_attrs({
        "state": "5.0",
        "outdoor_temperature": "10,5",
    })
    assert s is not None
    assert s.outdoor == 10.5
