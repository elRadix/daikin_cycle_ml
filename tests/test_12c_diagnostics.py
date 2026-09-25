"""Tests for 12c diagnostics extension."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.diagnostics import (
    ATTRS_SAMPLE_CAP,
    DB_TABLES,
)


def test_db_tables_includes_daily_summary():
    assert "daily_summary" in DB_TABLES


def test_db_tables_all_five_present():
    for t in ("cycles", "features", "model_state", "alerts", "daily_summary"):
        assert t in DB_TABLES


def test_attrs_sample_cap_positive():
    assert ATTRS_SAMPLE_CAP > 0

