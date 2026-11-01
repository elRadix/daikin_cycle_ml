"""v1.19.0 (#241) — model-SKU in notification subtitle."""
import pytest

from custom_components.daikin_cycle_ml.engine.status_report import (
    _subtitle_line,
    build_cop_low_report,
    build_rich_alert,
    build_status_report,
    build_stooklijn_report,
)


@pytest.mark.parametrize("model,emoji,expected", [
    ("EPRA12EAV3", True,  "\U0001F3E0 EPRA12EAV3 \u00B7 \U0001F550 TS"),
    ("EPRA12EAV3", False, "EPRA12EAV3 \u00B7 TS"),
    ("",           True,  "\U0001F550 TS"),
    ("",           False, "TS"),
])
def test_subtitle_line(model, emoji, expected):
    assert _subtitle_line("TS", model, emoji) == expected

def test_rich_alert_with_model():
    out = build_rich_alert("energy_daily_anomaly", "info", {}, full_model="EPRA12EAV3")
    assert "\U0001F3E0 EPRA12EAV3" in out

def test_status_report_with_model():
    out = build_status_report({}, full_model="EPRA12EAV3")
    assert "\U0001F3E0 EPRA12EAV3" in out

def test_stooklijn_with_model():
    out = build_stooklijn_report({}, full_model="EPRA12EAV3")
    assert "\U0001F3E0 EPRA12EAV3" in out

def test_cop_low_with_model():
    out = build_cop_low_report(2.5, 10, full_model="EPRA12EAV3")
    assert "\U0001F3E0 EPRA12EAV3" in out

def test_rich_alert_backward_compat():
    out = build_rich_alert("energy_daily_anomaly", "info", {})
    assert "\U0001F3E0" not in out
    assert "\U0001F550" in out
