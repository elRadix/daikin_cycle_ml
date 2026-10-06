"""Batch 50g -- coordinator helper coverage."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.const import DOMAIN


def test_const_domain():
    assert DOMAIN == "daikin_cycle_ml"


def test_const_version_semver():
    from custom_components.daikin_cycle_ml import const
    import re
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", const.VERSION), const.VERSION


def test_const_core_attributes_count():
    from custom_components.daikin_cycle_ml import const
    assert len(const.CORE_ATTRIBUTES) >= 13


def test_const_alert_templates_have_en_nl():
    from custom_components.daikin_cycle_ml.engine import notification_engine as ne
    assert hasattr(ne, "ALERT_TEMPLATES_EN")
    assert hasattr(ne, "ALERT_TEMPLATES_NL")
    assert isinstance(ne.ALERT_TEMPLATES_EN, dict)


def test_status_report_labels_complete():
    from custom_components.daikin_cycle_ml.engine import status_report as sr
    assert "en" in sr.LABELS
    assert "nl" in sr.LABELS
    # Belangrijke sleutels moeten in beide talen staan
    for lang in ("en", "nl"):
        for key in ("status", "mode", "quality", "cycles_today"):
            assert key in sr.LABELS[lang], f"missing {key} in {lang}"
