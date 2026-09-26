"""Batch 47 -- status_report edge cases."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.status_report import (
    ALERT_ADVICE,
    ALERT_LABELS,
    ALERT_SCHEMA,
    DIV,
    MODE_LABELS,
    SEVERITY_LABELS,
    build_cop_low_report,
    build_rich_alert,
    build_status_report,
    build_stooklijn_report,
    hour_bucket,
)


def test_hour_bucket_midnight():
    assert hour_bucket(0) == 'night'
    assert hour_bucket(4) == 'night'
    assert hour_bucket(5) == 'morning'
    assert hour_bucket(11) == 'morning'
    assert hour_bucket(12) == 'afternoon'
    assert hour_bucket(17) == 'afternoon'
    assert hour_bucket(18) == 'evening'
    assert hour_bucket(22) == 'evening'
    assert hour_bucket(23) == 'night'


def test_status_report_empty_snapshot():
    out = build_status_report({})
    assert 'Daikin Cycle ML' in out
    assert DIV in out


def test_status_report_no_emoji():
    out = build_status_report({'mode': 'heating', 'state': 'idle'}, emoji_enabled=False)
    assert 'Daikin Cycle ML' in out
    assert 'Mode' in out


def test_status_report_nl():
    out = build_status_report(
        {'state': 'idle', 'mode': 'dhw', 'cycles_today': 3},
        language='nl',
    )
    assert 'SWW' in out or 'dhw' in out
    assert 'Status' in out


def test_status_report_unknown_language():
    out = build_status_report({'mode': 'heating'}, language='xx')
    assert 'Daikin Cycle ML' in out


def test_status_report_anomaly_severity():
    for sev in ('normal', 'watch', 'warn', 'critical'):
        out = build_status_report({'anomaly_severity': sev})
        assert isinstance(out, str)


def test_stooklijn_empty():
    out = build_stooklijn_report({})
    assert 'Stooklijn' in out
    assert 'Samples' in out


def test_stooklijn_not_mapping():
    out = build_stooklijn_report(None)
    assert 'Stooklijn' in out


def test_stooklijn_string_values():
    out = build_stooklijn_report({
        'state': 'behoud',
        'besparing_cop_pct': 'bad',
        'comfort_impact': None,
        'betrouwbaarheid': 'also_bad',
        'samples': 'nope',
    })
    assert 'Stooklijn' in out
    assert 'Keep current LWT' in out or 'Behoud' in out


def test_stooklijn_nl():
    out = build_stooklijn_report({'state': 'verlaag_lwt_2c'}, language='nl')
    assert 'Verlaag LWT' in out


def test_stooklijn_en():
    out = build_stooklijn_report({'state': 'verlaag_lwt_2c'}, language='en')
    assert 'Lower LWT' in out


def test_stooklijn_emoji_off():
    out = build_stooklijn_report({'state': 'behoud'}, emoji_enabled=False)
    assert 'Stooklijn' in out
    assert 'Daikin Cycle ML' in out


def test_cop_low_basic():
    out = build_cop_low_report(2.1, 8)
    assert '2.10' in out
    assert '2.50' in out
    assert '8' in out


def test_cop_low_nl():
    out = build_cop_low_report(1.5, 3, language='nl')
    assert 'Dag-COP' in out


def test_cop_low_en():
    out = build_cop_low_report(1.5, 3, language='en')
    assert 'Day COP low' in out


def test_cop_low_no_emoji():
    out = build_cop_low_report(2.0, 5, emoji_enabled=False)
    assert '2.00' in out
    assert 'Daikin Cycle ML' in out


def test_rich_alert_unknown_type():
    out = build_rich_alert('unknown_type_xyz', 'warning', {})
    assert 'Daikin Cycle ML' in out
    assert 'unknown_type_xyz' in out


def test_rich_alert_no_emoji():
    out = build_rich_alert('short_run', 'warning', {}, emoji_enabled=False)
    assert 'Daikin Cycle ML' in out


def test_rich_alert_nl_mode_translated():
    ctx = {'mode': 'heating', 'cph': 5, 'target_cph': 4}
    out = build_rich_alert('pendulum_hourly', 'warning', ctx, language='nl')
    assert 'verwarmen' in out


def test_rich_alert_en_mode():
    ctx = {'mode': 'heating', 'cph': 5, 'target_cph': 4}
    out = build_rich_alert('pendulum_hourly', 'warning', ctx, language='en')
    assert 'heating' in out


def test_rich_alert_critical_severity():
    ctx = {'mode': 'heating', 'z_max': 5.5, 'top_dim': 'x'}
    out = build_rich_alert('ml_anomaly', 'critical', ctx, language='nl')
    assert 'kritiek' in out


def test_rich_alert_warning_severity():
    ctx = {'mode': 'heating', 'z_max': 3.2, 'top_dim': 'x'}
    out = build_rich_alert('ml_anomaly', 'warning', ctx, language='nl')
    assert 'waarschuwing' in out


def test_rich_alert_ctx_advice_wins():
    ctx = {'advice': '\u2022 Custom advice'}
    out = build_rich_alert('short_run', 'warning', ctx)
    assert 'Custom advice' in out


def test_labels_have_all_keys_en_nl():
    assert set(ALERT_LABELS['en'].keys()) == set(ALERT_LABELS['nl'].keys())


def test_modes_have_parity():
    assert set(MODE_LABELS['en'].keys()) == set(MODE_LABELS['nl'].keys())


def test_severities_have_parity():
    assert set(SEVERITY_LABELS['en'].keys()) == set(SEVERITY_LABELS['nl'].keys())


def test_advice_has_all_types_nl_en():
    assert set(ALERT_ADVICE['en'].keys()) == set(ALERT_ADVICE['nl'].keys())


def test_schema_has_all_binary_alerts():
    for k in ('pendulum_hourly', 'pendulum_daily', 'short_run',
              'short_off', 'ml_anomaly', 'setpoint_osc'):
        assert k in ALERT_SCHEMA


def test_rich_alert_all_schemas_render():
    ctx = {
        'cph': 6, 'target_cph': 4, 'cycles_today': 12, 'target_cpd': 40,
        'duration_min': 8, 'threshold_min': 20, 'off_min': 3,
        'mode': 'heating', 'z_max': 4.7, 'top_dim': 'thermal_kw_avg',
        'osc_count': 8, 'window_min': 30, 'threshold': 6,
        'lwt_setpoint': '32.0', 'lwt_target': '34.0', 'delta_max': '2.5',
        'lwt_actual': '35.2', 'indoor': '21.3', 'flow': '8.2',
        'outdoor': '12.4', 'avg_duration_min': 22,
    }
    for bkey in ALERT_SCHEMA:
        for lang in ('en', 'nl'):
            out = build_rich_alert(bkey, 'warning', ctx, language=lang)
            assert 'Daikin Cycle ML' in out
            assert DIV in out
