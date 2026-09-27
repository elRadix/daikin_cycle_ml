"""Batch 52e-1: coverage-fill for small pure-Python modules.

Targets:
  - engine/attribute_reader.py: lines 47, 75, 97-99
  - engine/action_engine.py:   lines 105, 107, 120-122
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.daikin_cycle_ml.engine.action_engine import (
    _mode_context,
    generate_advice,
)
from custom_components.daikin_cycle_ml.engine.attribute_reader import (
    _normalize,
    _to_float,
    read,
)


# ---------- attribute_reader._to_float (line 47) ----------

def test_to_float_bool_returns_none() -> None:
    assert _to_float(True) is None
    assert _to_float(False) is None


def test_to_float_numeric_string_ok() -> None:
    assert _to_float("3.14") == pytest.approx(3.14)
    assert _to_float(42) == 42.0


# ---------- attribute_reader._normalize (line 75) ----------

def test_normalize_numeric_string_returns_float() -> None:
    assert _normalize("42.5") == 42.5
    assert _normalize("1.5") == 1.5


def test_normalize_bool_string_returns_bool() -> None:
    assert _normalize("on") is True
    assert _normalize("off") is False


# ---------- attribute_reader.read custom_map (lines 97-99) ----------

def test_read_custom_map_renames_actual_key() -> None:
    state = SimpleNamespace(attributes={"Outside temp": 5.5, "Other": 1.0})
    out = read(state, custom_map={"outdoor_temp": "Outside temp"})
    assert out["outdoor_temp"] == 5.5
    assert "Outside temp" not in out
    assert out["Other"] == 1.0


def test_read_custom_map_skips_missing_actual() -> None:
    state = SimpleNamespace(attributes={"Other": 1.0})
    out = read(state, custom_map={"outdoor_temp": "Nonexistent"})
    assert "outdoor_temp" not in out
    assert out["Other"] == 1.0


def test_read_custom_map_skips_same_name() -> None:
    state = SimpleNamespace(attributes={"outdoor_temp": 7.0})
    out = read(state, custom_map={"outdoor_temp": "outdoor_temp"})
    assert out["outdoor_temp"] == 7.0


# ---------- action_engine._mode_context (lines 105, 107) ----------

def test_mode_context_heating() -> None:
    assert _mode_context("Heating") == " (space heating)"


def test_mode_context_cooling() -> None:
    assert _mode_context("Cooling") == " (space cooling)"


def test_mode_context_dhw_unknown_none() -> None:
    assert _mode_context("DHW") == " (DHW tank)"
    assert _mode_context(None) == ""
    assert _mode_context("Other") == ""


# ---------- action_engine.generate_advice exception (lines 120-122) ----------

def test_generate_advice_swallows_exception() -> None:
    with patch(
        "custom_components.daikin_cycle_ml.engine.action_engine._generate",
        side_effect=RuntimeError("boom"),
    ):
        result = generate_advice(anomaly=None, record={}, mode="Heating", options={})
    assert result == []
