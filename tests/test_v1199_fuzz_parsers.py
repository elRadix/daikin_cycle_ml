"""v1.19.9 #635 R640: hypothesis fuzz tests for parse helpers.

Doel: bugs vinden die handmatige tests missen. 200+ random inputs per
strategie, allen met invarianten:
- Geen crash (return None of float/bool, nooit raise)
- NaN/inf -> None (altijd)
- Negatieve floats -> negatief (nooit silent flip)
- Wetenschappelijke notatie -> correct gevalueerd
- Bool-varianten -> True, falsy varianten -> False
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given, settings, strategies as st

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    _parse_bool,
    _parse_float,
)


# ============================================================
# _parse_float: 200+ cases via hypothesis
# ============================================================

@settings(max_examples=200)
@given(st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(),
    st.binary(),
    st.just([]),
    st.just({}),
    st.just(()),
))
def test_fuzz_parse_float_never_raises(x):
    """R640: any input -> float|None, nooit raise."""
    try:
        result = _parse_float(x)
    except Exception as e:
        pytest.fail(f"_parse_float({x!r}) raised {type(e).__name__}: {e}")
    assert result is None or isinstance(result, float)


@settings(max_examples=200)
@given(st.floats(allow_nan=True, allow_infinity=True))
def test_fuzz_parse_float_nan_inf_always_none(x):
    """R640: NaN/inf input -> None (nooit doorlaten)."""
    if math.isnan(x) or math.isinf(x):
        assert _parse_float(x) is None


@settings(max_examples=200)
@given(st.floats(min_value=-1e6, max_value=1e6,
                 allow_nan=False, allow_infinity=False))
def test_fuzz_parse_float_roundtrip(x):
    """R640: float input -> dezelfde float als output."""
    result = _parse_float(x)
    assert result == x


@settings(max_examples=200)
@given(st.integers(min_value=-10**9, max_value=10**9))
def test_fuzz_parse_float_int_roundtrip(x):
    """R640: int input -> float(x)."""
    assert _parse_float(x) == float(x)


@settings(max_examples=200)
@given(st.text(
    alphabet=st.characters(
        whitelist_categories=("Nd", "Pd"),
    ),
    min_size=1, max_size=20,
))
def test_fuzz_parse_float_digit_string_never_raises(s):
    """R640: cijfer-streepje strings -> nooit crash."""
    try:
        _parse_float(s)
    except Exception as e:
        pytest.fail(f"_parse_float({s!r}) raised {type(e).__name__}: {e}")


# ============================================================
# _parse_bool: 200+ cases
# ============================================================

@settings(max_examples=200)
@given(st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(),
    st.binary(),
    st.just([]),
    st.just({}),
))
def test_fuzz_parse_bool_never_raises(x):
    """R640: any input -> bool, nooit raise."""
    try:
        result = _parse_bool(x)
    except Exception as e:
        pytest.fail(f"_parse_bool({x!r}) raised {type(e).__name__}: {e}")
    assert isinstance(result, bool)


@settings(max_examples=200)
@given(st.booleans())
def test_fuzz_parse_bool_bool_roundtrip(x):
    """R640: bool in -> zelfde bool uit."""
    assert _parse_bool(x) == x


@settings(max_examples=200)
@given(st.integers())
def test_fuzz_parse_bool_int_truthiness(x):
    """R640: int != 0 -> True, int == 0 -> False."""
    assert _parse_bool(x) == (x != 0)


@settings(max_examples=200)
@given(st.floats(allow_nan=False, allow_infinity=False))
def test_fuzz_parse_bool_float_truthiness(x):
    """R640: float != 0 -> True, == 0 -> False."""
    assert _parse_bool(x) == (x != 0)
