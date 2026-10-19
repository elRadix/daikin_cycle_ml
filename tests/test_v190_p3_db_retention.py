"""I1 - db_retention_warning plumbing.

Tests const registration, BINARY_ALERT_MAP entry, NOTIF_ID_BY_TYPE
entry, config_flow toggle presence, i18n parity.

Trigger / schema / dispatch live in C3/C4.
"""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.daikin_cycle_ml.const import (
    ALERT_DEDUP_DEFAULTS,
    ALERT_TYPE_EMOJI,
    NOTIF_ID_DB_RETENTION_WARNING,
)
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
    NOTIF_ID_BY_TYPE,
)


PKG = Path("custom_components/daikin_cycle_ml")


def test_notif_id_defined():
    assert NOTIF_ID_DB_RETENTION_WARNING.endswith("_db_retention_warning")
    assert "daikin_cycle_ml" in NOTIF_ID_DB_RETENTION_WARNING


def test_alert_type_emoji_present():
    assert "db_retention_warning" in ALERT_TYPE_EMOJI
    assert ALERT_TYPE_EMOJI["db_retention_warning"]


def test_dedup_default_present():
    assert ALERT_DEDUP_DEFAULTS["db_retention_warning"] == 1440


def test_binary_alert_map_entry():
    assert "db_retention_warning" in BINARY_ALERT_MAP
    spec = BINARY_ALERT_MAP["db_retention_warning"]
    assert isinstance(spec, tuple)
    assert len(spec) == 3
    assert spec[0] == "db_retention_warning"
    assert "Database retention" in spec[2]


def test_notif_id_by_type_entry():
    assert NOTIF_ID_BY_TYPE["db_retention_warning"] == NOTIF_ID_DB_RETENTION_WARNING


def test_config_flow_toggle_present():
    src = (PKG / "config_flow.py").read_text()
    assert "alert_enabled_db_retention_warning" in src


def test_i18n_parity():
    for f in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = json.loads((PKG / f).read_text())
        blk = d["options"]["step"]["notifications_enabled"]["data"]
        assert "alert_enabled_db_retention_warning" in blk, f"missing in {f}"


def test_i18n_key_counts_equal():
    counts = []
    for f in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = json.loads((PKG / f).read_text())
        blk = d["options"]["step"]["notifications_enabled"]["data"]
        counts.append(len(blk))
    assert len(set(counts)) == 1, f"i18n parity mismatch: {counts}"
    assert counts[0] == 11, f"expected 11 toggles, got {counts[0]}"

# ---------- C3: schema / titles / advice ----------


def test_alert_schema_entry():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_SCHEMA
    assert "db_retention_warning" in ALERT_SCHEMA
    fields = ALERT_SCHEMA["db_retention_warning"]
    assert isinstance(fields, list)
    assert len(fields) == 5
    keys = [f[1] for f in fields]
    assert "stale_alerts" in keys
    assert "stale_cycles" in keys
    assert "alert_retention_days" in keys
    assert "cycle_retention_days" in keys
    assert "mode" in keys


def test_alert_titles_en():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_TITLES
    assert ALERT_TITLES["en"]["db_retention_warning"] == "Database retention warning"


def test_alert_titles_nl():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_TITLES
    assert ALERT_TITLES["nl"]["db_retention_warning"] == "Database-retentie waarschuwing"


def test_alert_advice_en():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_ADVICE
    advice = ALERT_ADVICE["en"]["db_retention_warning"]
    assert "Database" in advice
    assert "maintenance" in advice


def test_alert_advice_nl():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_ADVICE
    advice = ALERT_ADVICE["nl"]["db_retention_warning"]
    assert "Database" in advice
    assert "onderhoud" in advice

# ---------- C4: dispatch wiring ----------

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_compute_db_retention_stale_no_db():
    """No db -> returns empty dict, cache unchanged."""
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
    from custom_components.daikin_cycle_ml import coordinator as coord_mod

    # Build minimal coordinator-like object via __new__
    cls = coord_mod.DaikinCycleMLCoordinator
    obj = cls.__new__(cls)
    obj.db = None
    obj.options = {}
    result = await obj._compute_db_retention_stale()
    assert result == {}


@pytest.mark.asyncio
async def test_compute_db_retention_stale_under_threshold():
    """Both counts under 100 -> fired=False."""
    from custom_components.daikin_cycle_ml import coordinator as coord_mod
    cls = coord_mod.DaikinCycleMLCoordinator
    obj = cls.__new__(cls)
    obj.db = MagicMock()
    obj.db.async_count_alerts_before = AsyncMock(return_value=42)
    obj.db.async_count_cycles_before = AsyncMock(return_value=7)
    obj.options = {}
    result = await obj._compute_db_retention_stale()
    assert result["fired"] is False
    assert result["stale_alerts"] == 42
    assert result["stale_cycles"] == 7


@pytest.mark.asyncio
async def test_compute_db_retention_stale_alerts_fired():
    """stale_alerts > 100 -> fired=True regardless of cycles."""
    from custom_components.daikin_cycle_ml import coordinator as coord_mod
    cls = coord_mod.DaikinCycleMLCoordinator
    obj = cls.__new__(cls)
    obj.db = MagicMock()
    obj.db.async_count_alerts_before = AsyncMock(return_value=500)
    obj.db.async_count_cycles_before = AsyncMock(return_value=0)
    obj.options = {}
    result = await obj._compute_db_retention_stale()
    assert result["fired"] is True


@pytest.mark.asyncio
async def test_compute_db_retention_stale_cycles_fired():
    """stale_cycles > 100 -> fired=True regardless of alerts."""
    from custom_components.daikin_cycle_ml import coordinator as coord_mod
    cls = coord_mod.DaikinCycleMLCoordinator
    obj = cls.__new__(cls)
    obj.db = MagicMock()
    obj.db.async_count_alerts_before = AsyncMock(return_value=0)
    obj.db.async_count_cycles_before = AsyncMock(return_value=150)
    obj.options = {}
    result = await obj._compute_db_retention_stale()
    assert result["fired"] is True


@pytest.mark.asyncio
async def test_compute_db_retention_stale_boundary_exactly_100():
    """Exactly 100 does NOT fire (strict >)."""
    from custom_components.daikin_cycle_ml import coordinator as coord_mod
    cls = coord_mod.DaikinCycleMLCoordinator
    obj = cls.__new__(cls)
    obj.db = MagicMock()
    obj.db.async_count_alerts_before = AsyncMock(return_value=100)
    obj.db.async_count_cycles_before = AsyncMock(return_value=100)
    obj.options = {}
    result = await obj._compute_db_retention_stale()
    assert result["fired"] is False


@pytest.mark.asyncio
async def test_compute_db_retention_stale_db_error_returns_empty():
    """DB exception -> returns {} so cache is preserved."""
    from custom_components.daikin_cycle_ml import coordinator as coord_mod
    cls = coord_mod.DaikinCycleMLCoordinator
    obj = cls.__new__(cls)
    obj.db = MagicMock()
    obj.db.async_count_alerts_before = AsyncMock(
        side_effect=RuntimeError("db fail")
    )
    obj.db.async_count_cycles_before = AsyncMock(return_value=0)
    obj.options = {}
    result = await obj._compute_db_retention_stale()
    assert result == {}

# ---------- C4b: ALERT_LABELS field labels ----------


def test_alert_labels_en_present():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_LABELS
    labels = ALERT_LABELS["en"]
    assert labels["stale_alerts"] == "Stale alerts"
    assert labels["stale_cycles"] == "Stale cycles"
    assert labels["alert_retention_days"] == "Alert retention"
    assert labels["cycle_retention_days"] == "Cycle retention"


def test_alert_labels_nl_present():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_LABELS
    labels = ALERT_LABELS["nl"]
    assert labels["stale_alerts"] == "Verouderde meldingen"
    assert labels["stale_cycles"] == "Verouderde cycli"
    assert labels["alert_retention_days"] == "Melding-retentie"
    assert labels["cycle_retention_days"] == "Cyclus-retentie"


def test_alert_renders_labels_not_raw_keys():
    """Regression: build_rich_alert must render labels, not fallback to key."""
    from custom_components.daikin_cycle_ml.engine.status_report import build_rich_alert
    ctx = {
        "stale_alerts": 42,
        "stale_cycles": 7,
        "alert_retention_days": 90,
        "cycle_retention_days": 365,
        "mode": "heating",
    }
    msg = build_rich_alert("db_retention_warning", "info", ctx, language="en")
    # Labels render with spaces:
    assert "Stale alerts" in msg
    assert "Stale cycles" in msg
    assert "Alert retention" in msg
    assert "Cycle retention" in msg
    # Raw keys do NOT appear collapsed:
    assert "stalealerts" not in msg
    assert "stalecycles" not in msg

