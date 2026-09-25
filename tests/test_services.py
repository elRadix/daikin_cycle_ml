"""Tests for services (Batch 6b-1)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError

from custom_components.daikin_cycle_ml.services import (
    ATTR_COUNTERS,
    ATTR_CYCLE_ID,
    ATTR_DAYS,
    ATTR_ENTRY_ID,
    ATTR_FORMAT,
    ATTR_LABEL,
    SCHEMA_BASELINE,
    SCHEMA_EXPORT,
    SCHEMA_LABEL,
    SCHEMA_RESET,
    SERVICE_EXPORT_CYCLES,
    SERVICE_LABEL_CYCLE,
    SERVICE_RECOMPUTE_BASELINE,
    SERVICE_RESET_COUNTERS,
    _do_export_cycles,
    _do_label_cycle,
    _do_recompute_baseline,
    _do_reset_counters,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _coord(store: CycleStore | None = None, db=None):
    c = MagicMock()
    c.store = store if store is not None else CycleStore()
    c.db = db
    return c


# ---------- constants ----------

def test_service_name_constants():
    assert SERVICE_RESET_COUNTERS == "reset_counters"
    assert SERVICE_EXPORT_CYCLES == "export_cycles"
    assert SERVICE_LABEL_CYCLE == "label_cycle"
    assert SERVICE_RECOMPUTE_BASELINE == "recompute_baseline"


# ---------- schema validation ----------

def test_schema_reset_minimal():
    out = SCHEMA_RESET({ATTR_ENTRY_ID: "e1"})
    assert out[ATTR_ENTRY_ID] == "e1"


def test_schema_reset_with_counters():
    out = SCHEMA_RESET({ATTR_ENTRY_ID: "e1", ATTR_COUNTERS: ["a", "b"]})
    assert out[ATTR_COUNTERS] == ["a", "b"]


def test_schema_reset_rejects_missing_entry_id():
    with pytest.raises(vol.Invalid):
        SCHEMA_RESET({})


def test_schema_export_defaults_applied():
    out = SCHEMA_EXPORT({ATTR_ENTRY_ID: "e1"})
    assert out[ATTR_DAYS] == 30
    assert out[ATTR_FORMAT] == "json"


def test_schema_export_csv():
    out = SCHEMA_EXPORT({ATTR_ENTRY_ID: "e1", ATTR_DAYS: 7, ATTR_FORMAT: "csv"})
    assert out[ATTR_FORMAT] == "csv"


def test_schema_export_rejects_bad_format():
    with pytest.raises(vol.Invalid):
        SCHEMA_EXPORT({ATTR_ENTRY_ID: "e1", ATTR_FORMAT: "xml"})


def test_schema_export_days_out_of_range():
    with pytest.raises(vol.Invalid):
        SCHEMA_EXPORT({ATTR_ENTRY_ID: "e1", ATTR_DAYS: 0})


def test_schema_label_requires_all_fields():
    with pytest.raises(vol.Invalid):
        SCHEMA_LABEL({ATTR_ENTRY_ID: "e1"})
    out = SCHEMA_LABEL({ATTR_ENTRY_ID: "e1", ATTR_CYCLE_ID: 5, ATTR_LABEL: "good"})
    assert out[ATTR_CYCLE_ID] == 5
    assert out[ATTR_LABEL] == "good"


def test_schema_baseline_default_days():
    assert SCHEMA_BASELINE({ATTR_ENTRY_ID: "e1"})[ATTR_DAYS] == 7


# ---------- _do_reset_counters ----------

def test_do_reset_counters_all():
    st = CycleStore()
    st.increment("a")
    st.increment("b")
    out = _do_reset_counters(_coord(st), None)
    assert out["reset"] is True
    assert out["counters"] == "all"
    assert st.get("a") == 0 and st.get("b") == 0


def test_do_reset_counters_subset():
    st = CycleStore()
    st.increment("a")
    st.increment("b")
    out = _do_reset_counters(_coord(st), ["a"])
    assert out["counters"] == ["a"]
    assert st.get("a") == 0
    assert st.get("b") == 1


# ---------- _do_export_cycles ----------

def test_do_export_json_with_data():
    st = CycleStore()
    st.add_cycle({"start_ts": time.time() - 60, "duration_s": 100, "mode": "Heating"})
    out = _do_export_cycles(_coord(st), 1, "json")
    assert out["format"] == "json"
    assert len(out["cycles"]) == 1
    assert out["cycles"][0]["mode"] == "Heating"


def test_do_export_json_filters_by_days():
    st = CycleStore()
    st.add_cycle({"start_ts": time.time() - 60, "duration_s": 100})
    st.add_cycle({"start_ts": time.time() - 40 * 86400, "duration_s": 100})
    out = _do_export_cycles(_coord(st), 1, "json")
    assert len(out["cycles"]) == 1


def test_do_export_csv_with_data():
    st = CycleStore()
    st.add_cycle({"start_ts": time.time() - 60, "duration_s": 100, "mode": "Heating"})
    out = _do_export_cycles(_coord(st), 1, "csv")
    assert out["format"] == "csv"
    assert "duration_s" in out["content"]
    assert "Heating" in out["content"]


def test_do_export_empty_json():
    out = _do_export_cycles(_coord(), 1, "json")
    assert out["cycles"] == []


def test_do_export_empty_csv_no_crash():
    out = _do_export_cycles(_coord(), 1, "csv")
    assert out["format"] == "csv"
    assert out["content"] == ""


# ---------- _do_recompute_baseline ----------

async def test_do_recompute_baseline_no_db():
    out = await _do_recompute_baseline(_coord(db=None), 7)
    assert out["computed"] is False
    assert out["reason"] == "no_db"
    assert out["days"] == 7


# ---------- _do_label_cycle ----------

async def test_do_label_cycle_without_db_raises():
    with pytest.raises(HomeAssistantError):
        await _do_label_cycle(_coord(db=None), 1, "x")


async def test_do_label_cycle_with_db():
    db = MagicMock()
    async def fake_label(cid, label):
        return True
    db.async_label_cycle = fake_label
    out = await _do_label_cycle(_coord(db=db), 42, "good")
    assert out["labeled"] is True
    assert out["cycle_id"] == 42
    assert out["label"] == "good"
