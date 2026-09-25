"""Tests for engine.attribute_reader."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.const import REQUIRED_ATTRIBUTES
from custom_components.daikin_cycle_ml.engine.attribute_reader import (
    _coerce_bool,
    _normalize,
    missing_required,
    read,
)


class _FakeState:
    def __init__(self, attributes):
        self.attributes = attributes


def test_read_none_state():
    assert read(None) == {}


def test_read_no_attributes():
    assert read(_FakeState(None)) == {}


def test_read_normalizes_mixed_types():
    st = _FakeState({"INV frequency (rps)": 0, "BUH Step1": "OFF"})
    out = read(st)
    assert out["INV frequency (rps)"] == 0.0
    assert out["BUH Step1"] is False


def test_read_filters_template_garbage():
    st = _FakeState({"O/U EEPROM": "{0:X}{1:X}"})
    assert read(st)["O/U EEPROM"] is None


def test_read_filters_placeholder():
    st = _FakeState({"X": "Conv 995 not avail."})
    assert read(st)["X"] is None


def test_read_filters_null_strings():
    st = _FakeState({"a": "---", "b": "unavailable", "c": ""})
    out = read(st)
    assert out["a"] is None
    assert out["b"] is None
    assert out["c"] is None


def test_read_trims_whitespace():
    st = _FakeState({"Error Code": " 0 "})
    assert read(st)["Error Code"] == 0.0


def test_read_keeps_floats():
    st = _FakeState({"Outdoor air temp.(R1T)": 27.7})
    assert read(st)["Outdoor air temp.(R1T)"] == 27.7


def test_coerce_bool_variants():
    assert _coerce_bool("ON") is True
    assert _coerce_bool("on") is True
    assert _coerce_bool("true") is True
    assert _coerce_bool("OFF") is False
    assert _coerce_bool("false") is False
    assert _coerce_bool("garbage") is None
    assert _coerce_bool(True) is True
    assert _coerce_bool(3.14) is None


def test_normalize_passthrough_numbers():
    assert _normalize(27.7) == 27.7
    assert _normalize(5) == 5.0
    assert _normalize(True) is True
    assert _normalize(None) is None


def test_normalize_rejects_unknown_types():
    assert _normalize([1, 2]) is None
    assert _normalize({"x": 1}) is None


def test_missing_required_reports_all_missing():
    assert len(missing_required({})) == len(REQUIRED_ATTRIBUTES)


def test_missing_required_empty_when_complete():
    attrs = {k: 0.0 for k in REQUIRED_ATTRIBUTES}
    assert missing_required(attrs) == []

def test_read_preserves_string_mode():
    st = _FakeState({"I/U operation mode": "Heating"})
    assert read(st)["I/U operation mode"] == "Heating"


def test_read_preserves_dhw_string():
    st = _FakeState({"Operation Mode": "DHW"})
    assert read(st)["Operation Mode"] == "DHW"


def test_normalize_returns_clean_string_for_unknown():
    assert _normalize("Heating") == "Heating"
    assert _normalize("DHW") == "DHW"
    assert _normalize("Cooling") == "Cooling"
