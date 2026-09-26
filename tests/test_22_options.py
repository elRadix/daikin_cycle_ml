"""Batch 22 tests: i18n + alert groups + setpoint_osc options."""
from __future__ import annotations

import json
import os
import inspect

from custom_components.daikin_cycle_ml import config_flow as cf
from custom_components.daikin_cycle_ml import const


def test_const_language_keys():
    assert const.LANG_EN == "en"
    assert const.LANG_NL == "nl"
    assert const.DEFAULT_NOTIFICATION_LANGUAGE == "en"
    assert "en" in const.NOTIFICATION_LANGUAGES
    assert "nl" in const.NOTIFICATION_LANGUAGES


def test_const_alert_groups():
    assert set(const.ALERT_GROUPS) == {
        "pendulum", "short_cycle", "ml", "setpoint", "cop_stooklijn",
    }
    assert const.ALERT_GROUP_MAP["pendulum"] == "pendulum"
    assert const.ALERT_GROUP_MAP["short_run"] == "short_cycle"
    assert const.ALERT_GROUP_MAP["short_off"] == "short_cycle"
    assert const.ALERT_GROUP_MAP["ml_anomaly"] == "ml"
    assert const.ALERT_GROUP_MAP["setpoint_osc"] == "setpoint"
    assert const.ALERT_GROUP_MAP["cop_low"] == "cop_stooklijn"
    assert const.ALERT_GROUP_MAP["stooklijn_advies"] == "cop_stooklijn"


def test_language_selector_present():
    sel = cf._build_language_selector()
    cfg = sel.config
    assert cfg["mode"] == "dropdown"
    values = [o["value"] for o in cfg["options"]]
    assert "en" in values and "nl" in values


def test_options_flow_pendulum_has_setpoint_osc():
    src = inspect.getsource(cf.DaikinCycleMLOptionsFlow.async_step_pendulum)
    for key in (
        "setpoint_oscillation_threshold",
        "setpoint_osc_window_min",
        "setpoint_osc_min_delta",
    ):
        assert key in src, f"missing {key}"


def test_options_flow_notifications_has_language_and_groups():
    src = inspect.getsource(cf.DaikinCycleMLOptionsFlow.async_step_notifications)
    for key in (
        "notification_language",
        "alert_group_pendulum",
        "alert_group_short_cycle",
        "alert_group_ml",
        "alert_group_setpoint",
        "alert_group_cop_stooklijn",
    ):
        assert key in src, f"missing {key}"


def test_translations_pendulum_has_osc_keys():
    base = os.path.join(os.path.dirname(__file__), "..", "translations")
    for fn in ("en.json", "nl.json"):
        with open(os.path.join(base, fn), encoding="utf-8") as f:
            data = json.load(f)
        d = data["options"]["step"]["pendulum"]["data"]
        dd = data["options"]["step"]["pendulum"]["data_description"]
        for k in (
            "setpoint_oscillation_threshold",
            "setpoint_osc_window_min",
            "setpoint_osc_min_delta",
        ):
            assert k in d, f"{fn} data missing {k}"
            assert k in dd, f"{fn} data_description missing {k}"


def test_translations_notifications_has_language_and_groups():
    base = os.path.join(os.path.dirname(__file__), "..", "translations")
    for fn in ("en.json", "nl.json"):
        with open(os.path.join(base, fn), encoding="utf-8") as f:
            data = json.load(f)
        d = data["options"]["step"]["notifications"]["data"]
        dd = data["options"]["step"]["notifications"]["data_description"]
        for k in (
            "notification_language",
            "alert_group_pendulum",
            "alert_group_short_cycle",
            "alert_group_ml",
            "alert_group_setpoint",
            "alert_group_cop_stooklijn",
        ):
            assert k in d, f"{fn} data missing {k}"
            assert k in dd, f"{fn} data_description missing {k}"


def test_strings_json_mirrors_en():
    base = os.path.dirname(__file__)
    with open(os.path.join(base, "..", "strings.json"), encoding="utf-8") as f:
        s = json.load(f)
    with open(os.path.join(base, "..", "translations", "en.json"), encoding="utf-8") as f:
        e = json.load(f)
    sd = s["options"]["step"]["notifications"]["data"]
    ed = e["options"]["step"]["notifications"]["data"]
    assert sd.get("notification_language") == ed.get("notification_language")
    sp = s["options"]["step"]["pendulum"]["data"]
    ep = e["options"]["step"]["pendulum"]["data"]
    assert sp.get("setpoint_oscillation_threshold") == ep.get("setpoint_oscillation_threshold")
