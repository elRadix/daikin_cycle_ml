"""Batch 41 -- rich pendulum path + all-alerts test option."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
JSON_FILES = [
    "strings.json",
    "translations/en.json",
    "translations/nl.json",
]


def test_ne_uses_bkey_for_schema_lookup():
    src = (ROOT / "engine/notification_engine.py").read_text()
    assert "if bkey in ALERT_SCHEMA:" in src
    assert "if alert_type in ALERT_SCHEMA:" not in src


def test_pendulum_rich_output():
    from custom_components.daikin_cycle_ml.engine.status_report import (
        ALERT_SCHEMA, DIV, build_rich_alert,
    )
    ctx = {"cph": 6, "target_cph": 4, "cycles_today": 12, "target_cpd": 40,
           "advice": "\u2022 advice"}
    for bkey in ("pendulum_hourly", "pendulum_daily"):
        assert bkey in ALERT_SCHEMA
        out = build_rich_alert(bkey, "warning", ctx, language="en")
        assert "Daikin Cycle ML" in out
        assert DIV in out
        assert "0 cycli" not in out
        assert "0 cycles" not in out


def test_coordinator_has_emit_all():
    src = (ROOT / "coordinator.py").read_text()
    assert "async def _emit_all_test_alerts(" in src
    assert 'alert_kind == "all_alerts"' in src


def test_config_flow_dropdown_has_all_alerts():
    src = (ROOT / "config_flow.py").read_text()
    assert "\"all_alerts\"" in src


@pytest.mark.parametrize("rel", JSON_FILES)
def test_json_selector_has_all_alerts(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    assert "all_alerts" in d["selector"]["alert_kind"]["options"]


@pytest.mark.parametrize("rel", JSON_FILES)
def test_json_step_labels_updated(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    step = d["options"]["step"]["test_notification"]
    data = step.get("data") or {}
    dd = step.get("data_description") or {}
    assert data.get("alert_kind")
    assert data.get("ignore_group_filters")
    assert "Force" in data["ignore_group_filters"] or "Forceer" in data["ignore_group_filters"]
    assert len(dd["ignore_group_filters"]) > 30
