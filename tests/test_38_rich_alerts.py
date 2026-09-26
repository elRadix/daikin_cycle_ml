"""Batch 38 -- rich format for all binary alert types."""
from __future__ import annotations

import datetime as _dt

import pytest

from custom_components.daikin_cycle_ml.engine.status_report import (
    ALERT_EMOJI,
    ALERT_LABELS,
    ALERT_SCHEMA,
    ALERT_TITLES,
    DIV,
    build_rich_alert,
)


ALL_TYPES = (
    "pendulum_hourly", "pendulum_daily", "short_run",
    "short_off", "ml_anomaly", "setpoint_osc",
)


@pytest.mark.parametrize("alert_type", ALL_TYPES)
def test_rich_alert_has_header(alert_type):
    ctx = {'cph': 6, 'target_cph': 4, 'cycles_today': 12, 'target_cpd': 40,
           'duration_min': 8, 'threshold_min': 20,
           'off_min': 3, 'mode': 'heating', 'z_max': 3.4,
           'top_dim': 'duration_s', 'osc_count': 8,
           'window_min': 30, 'threshold': 6,
           'advice': '\u2022 Test advice'}
    out = build_rich_alert(alert_type, 'warning', ctx, language='en')
    assert 'Daikin Cycle ML' in out
    assert DIV in out
    assert _dt.datetime.now().strftime('%Y-%m-%d') in out


@pytest.mark.parametrize("alert_type", ALL_TYPES)
def test_rich_alert_nl_title(alert_type):
    out = build_rich_alert(alert_type, 'warning', {}, language='nl')
    assert ALERT_TITLES['nl'][alert_type] in out


@pytest.mark.parametrize("alert_type", ALL_TYPES)
def test_rich_alert_has_advice_when_present(alert_type):
    out = build_rich_alert(alert_type, 'warning', {'advice': '\u2022 Advice'}, language='en')
    assert 'Advice' in out


@pytest.mark.parametrize("alert_type", ALL_TYPES)
def test_rich_alert_emoji_toggle(alert_type):
    out = build_rich_alert(alert_type, 'warning', {}, emoji_enabled=False)
    assert ALERT_EMOJI.get(alert_type, '\U0001F514') not in out


@pytest.mark.parametrize("alert_type", ALL_TYPES)
def test_rich_alert_schema_parity_en_nl(alert_type):
    for label_key in ALERT_LABELS['en']:
        assert label_key in ALERT_LABELS['nl']


def test_rich_alert_has_types_in_schema():
    for t in ALL_TYPES:
        assert t in ALERT_SCHEMA


def test_rich_alert_all_types_have_emoji():
    for t in ALL_TYPES:
        assert t in ALERT_EMOJI
