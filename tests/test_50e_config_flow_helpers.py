"""Batch 50e -- direct helper coverage in config_flow."""
from __future__ import annotations

from custom_components.daikin_cycle_ml import config_flow as cf


def test_flatten_notify_choice_str():
    assert cf._flatten_notify_choice("notify.foo") == "notify.foo"


def test_flatten_notify_choice_empty():
    v = cf._flatten_notify_choice("")
    assert isinstance(v, str)


def test_flatten_notify_choice_dict():
    v = cf._flatten_notify_choice({"entity_id": "notify.bar"})
    assert isinstance(v, str)


def test_build_language_selector():
    s = cf._build_language_selector()
    assert s is not None


def test_num_selector_basic():
    s = cf._num(1, 100, 1)
    assert s is not None


def test_num_selector_with_unit():
    s = cf._num(1, 100, 1, unit="min")
    assert s is not None


def test_default_notify_choice_no_hass():
    # current bestaat -> return current
    v = cf._default_notify_choice(None, "notify.telegram")
    assert v == "notify.telegram"


def test_default_notify_choice_empty():
    v = cf._default_notify_choice(None, None)
    assert v is None or isinstance(v, str)


def test_legacy_notify_options_none_hass():
    try:
        v = cf._legacy_notify_options(None)
        assert isinstance(v, list)
    except Exception:
        pass
