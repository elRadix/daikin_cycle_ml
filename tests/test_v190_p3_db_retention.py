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
    assert counts[0] == 9, f"expected 9 toggles, got {counts[0]}"
