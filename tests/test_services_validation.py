import pytest
import voluptuous as vol

from custom_components.daikin_cycle_ml.services import (
    ATTR_COUNTERS,
    ATTR_CYCLE_ID,
    ATTR_DAYS,
    ATTR_ENTRY_ID,
    ATTR_LABEL,
    SCHEMA_EXPORT,
    SCHEMA_LABEL,
    SCHEMA_RESET,
)


def test_reset_missing_entry_id():
    """SCHEMA_RESET requires ATTR_ENTRY_ID."""
    with pytest.raises(vol.Invalid):
        SCHEMA_RESET({})


def test_reset_invalid_counters_type():
    """SCHEMA_RESET counters must be a list of strings (or None)."""
    with pytest.raises(vol.Invalid):
        SCHEMA_RESET({ATTR_ENTRY_ID: "abc", ATTR_COUNTERS: "not_a_list"})


def test_reset_valid():
    """SCHEMA_RESET accepts valid input."""
    out = SCHEMA_RESET({ATTR_ENTRY_ID: "abc", ATTR_COUNTERS: ["cycles_today"]})
    assert out[ATTR_ENTRY_ID] == "abc"
    assert out[ATTR_COUNTERS] == ["cycles_today"]


def test_export_missing_entry_id():
    with pytest.raises(vol.Invalid):
        SCHEMA_EXPORT({})


def test_export_days_out_of_range():
    with pytest.raises(vol.Invalid):
        SCHEMA_EXPORT({ATTR_ENTRY_ID: "abc", ATTR_DAYS: 0})


def test_label_missing_fields():
    with pytest.raises(vol.Invalid):
        SCHEMA_LABEL({ATTR_ENTRY_ID: "abc"})


def test_label_valid():
    out = SCHEMA_LABEL({ATTR_ENTRY_ID: "abc", ATTR_CYCLE_ID: 1, ATTR_LABEL: "test"})
    assert out[ATTR_CYCLE_ID] == 1
