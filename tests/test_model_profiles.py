"""Tests for engine.model_profiles."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.const import (
    DEFAULT_PENDULUM_CPD,
    MODEL_BASISPROFIEL,
    MODEL_CHOICES,
    MODEL_EPRA12EAV3,
    REQUIRED_ATTRIBUTES,
)
from custom_components.daikin_cycle_ml.engine.model_profiles import (
    MODEL_PROFILES,
    defaults_for,
    expected_attributes,
    get_profile,
)


def test_all_model_choices_present():
    for m in MODEL_CHOICES:
        assert m in MODEL_PROFILES


def test_epra12_has_model_specific_cpd():
    assert get_profile(MODEL_EPRA12EAV3)["pendulum_cycles_per_day"] == 35


def test_unknown_model_falls_back_to_basis():
    p = get_profile("nonexistent")
    assert p["pendulum_cycles_per_day"] == DEFAULT_PENDULUM_CPD


def test_get_profile_returns_copy():
    p1 = get_profile(MODEL_EPRA12EAV3)
    p1["pendulum_cycles_per_day"] = 999
    p2 = get_profile(MODEL_EPRA12EAV3)
    assert p2["pendulum_cycles_per_day"] == 35


def test_no_model_expects_brine():
    for m in MODEL_CHOICES:
        assert get_profile(m)["expects_brine"] is False


def test_expected_attributes_returns_core():
    from custom_components.daikin_cycle_ml.const import CORE_ATTRIBUTES
    attrs = expected_attributes(MODEL_EPRA12EAV3)
    assert set(attrs) == set(CORE_ATTRIBUTES)

def test_defaults_for_excludes_expects_brine():
    d = defaults_for(MODEL_EPRA12EAV3)
    assert "expects_brine" not in d
    assert d["pendulum_cycles_per_day"] == 35


def test_basisprofiel_is_default_baseline():
    p = get_profile(MODEL_BASISPROFIEL)
    assert p["pendulum_cycles_per_day"] == DEFAULT_PENDULUM_CPD


def test_all_profiles_have_same_keys():
    keysets = {frozenset(p.keys()) for p in MODEL_PROFILES.values()}
    assert len(keysets) == 1
