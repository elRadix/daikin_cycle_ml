"""Batch 37 -- rich sectioned status report."""
from __future__ import annotations

import datetime as _dt

import pytest

from custom_components.daikin_cycle_ml.engine.status_report import (
    DIV,
    LABELS,
    build_cop_low_report,
    build_status_report,
    build_stooklijn_report,
    hour_bucket,
)


def _full_snapshot():
    return {
        "state": "idle", "mode": "heating",
        "last_cycle_ago_min": 14, "quality_last": 82,
        "lwt": 32.4, "indoor": 21.3, "outdoor": 14.7,
        "flow_lmin": 8.2, "thermal_kw": 1.85,
        "cycles_today": 4, "target_cpd": 8, "target_cph": 4,
        "short_runs_today": 1, "good_cycles_today": 3,
        "cycles_per_hour": 2,
        "baseline_samples": 47, "baseline_modes": ["heating"],
        "anomaly_severity": "normal",
        "cop_today": 3.42, "cop_today_samples": 12,
        "db_total": 128, "db_7d": 32, "db_30d": 128,
        "db_avg_duration_min": 42.0,
    }


def test_hour_buckets():
    assert hour_bucket(3) == "night"
    assert hour_bucket(8) == "morning"
    assert hour_bucket(14) == "afternoon"
    assert hour_bucket(20) == "evening"


def test_status_has_header_and_timestamp():
    out = build_status_report(_full_snapshot(), language='nl')
    assert 'Daikin Cycle ML' in out
    assert 'RAPPORT' in out
    assert _dt.datetime.now().strftime('%Y-%m-%d') in out


def test_status_has_section_dividers():
    out = build_status_report(_full_snapshot(), language='en')
    assert out.count(DIV) >= 4


def test_status_includes_all_key_sections():
    out = build_status_report(_full_snapshot(), language='en')
    for k in ('Status', 'Mode', 'LWT', 'Indoor', 'Outdoor',
              'Flow', 'Thermal', 'Cycles today', 'Baseline',
              'Anomaly', 'COP today', 'Statistics'):
        assert k in out, k


def test_status_nl_labels():
    out = build_status_report(_full_snapshot(), language='nl')
    for k in ('Modus', 'Binnen', 'Buiten', 'Cycli vandaag',
              'Anomalie', 'Statistieken'):
        assert k in out, k


def test_status_signoff_present():
    out_nl = build_status_report(_full_snapshot(), language='nl')
    out_en = build_status_report(_full_snapshot(), language='en')
    assert 'fijne dag' in out_nl or 'zet' in out_nl or 'slaap' in out_nl or 'Rustige' in out_nl
    assert 'Good' in out_en or 'Quiet' in out_en


def test_status_emoji_toggle():
    out = build_status_report(_full_snapshot(), emoji_enabled=False)
    assert '\U0001F305' not in out
    assert 'Daikin Cycle ML' in out


def test_status_handles_missing_fields():
    out = build_status_report({}, language='en')
    assert 'Daikin Cycle ML' in out
    assert DIV in out


def test_stooklijn_bilingual():
    cache = {'state': 'ok', 'besparing_cop_pct': 12.0, 'comfort_impact': -0.3,
             'betrouwbaarheid': 0.75, 'samples': 42}
    en = build_stooklijn_report(cache, language='en')
    nl = build_stooklijn_report(cache, language='nl')
    assert 'Stooklijn advice' in en
    assert 'Stooklijn advies' in nl
    assert '+12%' in en and '+12%' in nl


def test_cop_low_bilingual():
    en = build_cop_low_report(2.1, 8, language='en')
    nl = build_cop_low_report(2.1, 8, language='nl')
    assert 'Day COP low' in en
    assert 'Dag-COP laag' in nl
    assert '2.10' in en and '2.10' in nl


def test_labels_have_parity():
    en = set(LABELS['en'].keys())
    nl = set(LABELS['nl'].keys())
    assert en == nl
