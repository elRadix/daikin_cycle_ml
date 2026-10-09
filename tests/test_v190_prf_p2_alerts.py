"""v1.9.0 PR F — 3 new P2 alerts: dhw_pendulum, high_cycle_rate, cop_vs_datasheet_low.

Covers: const registrations, BINARY_ALERT_MAP/NOTIF_ID_BY_TYPE, group mapping,
dedup defaults, schema render (real + collapse), i18n parity, config_flow toggles.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.const import (
    ALERT_DEDUP_DEFAULTS,
    ALERT_GROUP_COP_STOOKLIJN,
    ALERT_GROUP_MAP,
    ALERT_GROUP_PENDULUM,
    ALERT_GROUP_SHORT_CYCLE,
    ALERT_TYPE_EMOJI,
    COP_VS_DATASHEET_LOW_PCT,
    DEFAULT_DHW_PENDULUM_CPH,
    HIGH_CYCLE_RATE_MULTIPLIER,
    NOTIF_ID_COP_VS_DATASHEET_LOW,
    NOTIF_ID_DHW_PENDULUM,
    NOTIF_ID_HIGH_CYCLE_RATE,
)
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
    NOTIF_ID_BY_TYPE,
    SEV_INFO,
    SEV_WARNING,
)
from custom_components.daikin_cycle_ml.engine.status_report import (
    ALERT_ADVICE,
    ALERT_EMOJI,
    ALERT_LABELS,
    ALERT_SCHEMA,
    ALERT_TITLES,
    SEVERITY_LABELS,
    build_rich_alert,
)

ROOT = Path(__file__).resolve().parents[1]
PRF_ALERTS = ("dhw_pendulum", "high_cycle_rate", "cop_vs_datasheet_low")


# --- const.py registrations ---

def test_notif_ids_registered():
    assert NOTIF_ID_DHW_PENDULUM.endswith("dhw_pendulum")
    assert NOTIF_ID_HIGH_CYCLE_RATE.endswith("high_cycle_rate")
    assert NOTIF_ID_COP_VS_DATASHEET_LOW.endswith("cop_vs_datasheet_low")


def test_thresholds_defined():
    assert COP_VS_DATASHEET_LOW_PCT == -10.0
    assert HIGH_CYCLE_RATE_MULTIPLIER == 1.5
    assert DEFAULT_DHW_PENDULUM_CPH == 3


def test_alert_type_emoji_has_prf():
    for at in PRF_ALERTS:
        assert at in ALERT_TYPE_EMOJI


def test_alert_group_map_groups():
    assert ALERT_GROUP_MAP["dhw_pendulum"] == ALERT_GROUP_PENDULUM
    assert ALERT_GROUP_MAP["high_cycle_rate"] == ALERT_GROUP_SHORT_CYCLE
    assert ALERT_GROUP_MAP["cop_vs_datasheet_low"] == ALERT_GROUP_COP_STOOKLIJN


def test_alert_dedup_defaults():
    assert ALERT_DEDUP_DEFAULTS["dhw_pendulum"] == 60
    assert ALERT_DEDUP_DEFAULTS["high_cycle_rate"] == 60
    assert ALERT_DEDUP_DEFAULTS["cop_vs_datasheet_low"] == 1440


# --- notification_engine.py registrations ---

def test_binary_alert_map_entries():
    assert BINARY_ALERT_MAP["dhw_pendulum"][1] == SEV_WARNING
    assert BINARY_ALERT_MAP["high_cycle_rate"][1] == SEV_WARNING
    assert BINARY_ALERT_MAP["cop_vs_datasheet_low"][1] == SEV_INFO


def test_notif_id_by_type_entries():
    assert NOTIF_ID_BY_TYPE["dhw_pendulum"] == NOTIF_ID_DHW_PENDULUM
    assert NOTIF_ID_BY_TYPE["high_cycle_rate"] == NOTIF_ID_HIGH_CYCLE_RATE
    assert NOTIF_ID_BY_TYPE["cop_vs_datasheet_low"] == NOTIF_ID_COP_VS_DATASHEET_LOW


def test_sev_info_constant():
    assert SEV_INFO == "info"


# --- status_report.py registrations ---

def test_alert_schema_entries():
    for at in PRF_ALERTS:
        assert at in ALERT_SCHEMA
        assert isinstance(ALERT_SCHEMA[at], list)
        assert len(ALERT_SCHEMA[at]) >= 4


def test_alert_titles_en_nl():
    for at in PRF_ALERTS:
        assert at in ALERT_TITLES["en"]
        assert at in ALERT_TITLES["nl"]


def test_alert_emoji_entries():
    for at in PRF_ALERTS:
        assert at in ALERT_EMOJI


def test_alert_advice_en_nl():
    for at in PRF_ALERTS:
        assert at in ALERT_ADVICE["en"]
        assert at in ALERT_ADVICE["nl"]


def test_severity_labels_have_info():
    assert SEVERITY_LABELS["en"]["info"] == "info"
    assert SEVERITY_LABELS["nl"]["info"] == "informatie"


# --- schema render ---

def test_render_dhw_pendulum_real_values():
    ctx = {
        "dhw_cph": 5, "target_cph": 3,
        "mode": "dhw", "outdoor": "8.0", "advice": "",
    }
    out = build_rich_alert("dhw_pendulum", "warning", ctx, language="en")
    assert "DHW pendulum detected" in out
    assert "5" in out
    assert "—" not in out.split("━")[2]  # rows block has no dash


def test_render_high_cycle_rate_real_values():
    ctx = {
        "cph": 8, "target_cph": 4, "multiplier": 1.5,
        "mode": "heating", "outdoor": "5.0", "advice": "",
    }
    out = build_rich_alert("high_cycle_rate", "warning", ctx, language="en")
    assert "High cycle rate" in out
    assert "8" in out
    assert "1.5" in out


def test_render_cop_vs_datasheet_low_real_values():
    ctx = {
        "pct_diff": "-12.5", "cop_expected": "3.2",
        "mode": "heating", "outdoor": "3.0", "advice": "",
    }
    out = build_rich_alert("cop_vs_datasheet_low", "info", ctx, language="en")
    assert "COP below datasheet" in out
    assert "-12.5" in out
    assert "3.2" in out


def test_render_cop_vs_datasheet_uses_type_emoji():
    ctx = {
        "pct_diff": "-12.5", "cop_expected": "3.2",
        "mode": "heating", "outdoor": "3.0", "advice": "",
    }
    out = build_rich_alert("cop_vs_datasheet_low", "info", ctx, language="en")
    # alert-type emoji must be used in the header, not severity fallback
    assert "\U0001F4CA" in out  # \U0001F4CA = bar chart


@pytest.mark.parametrize("at", [
    "dhw_pendulum",
    "high_cycle_rate",
    "cop_vs_datasheet_low",
])
def test_render_collapses_when_missing(at):
    ctx: dict = {}
    out = build_rich_alert(at, "warning", ctx, language="en")
    # rows collapse to em-dash when the backing fields are absent
    assert "\u2014" in out


# --- i18n parity across the 3 translation files ---

@pytest.mark.parametrize("fname", ["strings.json", "translations/en.json", "translations/nl.json"])
def test_translation_files_have_prf_keys(fname):
    path = ROOT / "custom_components" / "daikin_cycle_ml" / fname
    data = json.loads(path.read_text(encoding="utf-8"))
    st = data["options"]["step"]
    ne = st["notifications_enabled"]
    nd = st["notifications_dedup"]
    for k in ("alert_enabled_dhw_pendulum",
              "alert_enabled_high_cycle_rate",
              "alert_enabled_cop_vs_datasheet_low"):
        assert k in ne["data"], f"{fname} missing data.{k}"
        assert k in ne["data_description"], f"{fname} missing desc.{k}"
    for k in ("alert_agg_dhw_pendulum_min",
              "alert_agg_high_cycle_rate_min",
              "alert_agg_cop_vs_datasheet_low_min"):
        assert k in nd["data"], f"{fname} missing data.{k}"
        assert k in nd["data_description"], f"{fname} missing desc.{k}"


@pytest.mark.parametrize("fname", ["strings.json", "translations/en.json", "translations/nl.json"])
def test_translation_keys_parity(fname):
    """Both PR E and PR F keys exist in all 3 files at identical counts."""
    path = ROOT / "custom_components" / "daikin_cycle_ml" / fname
    data = json.loads(path.read_text(encoding="utf-8"))
    st = data["options"]["step"]
    assert len(st["notifications_enabled"]["data"]) == 8
    assert len(st["notifications_enabled"]["data_description"]) == 8
    assert len(st["notifications_dedup"]["data"]) == 16
    assert len(st["notifications_dedup"]["data_description"]) == 16


# --- labels present in both languages ---

@pytest.mark.parametrize("lang", ["en", "nl"])
def test_new_label_keys_present(lang):
    labels = ALERT_LABELS[lang]
    for k in ("dhw_cph", "target_cph", "multiplier", "pct_diff", "cop_expected"):
        assert k in labels, f"ALERT_LABELS[{lang}] missing {k}"


# --- invariants: totals expected after PR F ---

def test_schema_total():
    assert len(ALERT_SCHEMA) == 14


def test_binary_alert_map_total():
    assert len(BINARY_ALERT_MAP) == 14


def test_notif_id_by_type_total():
    assert len(NOTIF_ID_BY_TYPE) == 14


def test_alert_titles_totals():
    assert len(ALERT_TITLES["en"]) == 16
    assert len(ALERT_TITLES["nl"]) == 16


def test_alert_advice_totals():
    assert len(ALERT_ADVICE["en"]) == 14
    assert len(ALERT_ADVICE["nl"]) == 14
