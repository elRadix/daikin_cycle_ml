"""Tests for model-family and alias resolution (v1.13.2)."""

from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.const import (
    MODEL_ALIASES,
    MODEL_BASISPROFIEL,
    MODEL_CHOICES,
    MODEL_CUSTOM,
    MODEL_ERGA04EAV3,
    MODEL_ERGA06EAV3,
    MODEL_ERGA08EAV3,
    MODEL_ERGA08EVH7,
    MODEL_FAMILIES,
    MODEL_LABELS,
    family_for_model,
    models_in_family,
    resolve_model_key,
)
from custom_components.daikin_cycle_ml.engine.model_profiles import (
    MODEL_PROFILES,
    get_profile,
)


def test_model_families_shape() -> None:
    assert isinstance(MODEL_FAMILIES, dict)
    assert len(MODEL_FAMILIES) == 11
    for key, label in MODEL_FAMILIES.items():
        assert isinstance(key, str) and key
        assert isinstance(label, str) and label


def test_model_aliases_shape() -> None:
    """Validates that all aliases map to valid model profiles."""
    assert isinstance(MODEL_ALIASES, dict)
    assert len(MODEL_ALIASES) >= 1
    for alias, target in MODEL_ALIASES.items():
        assert target in MODEL_PROFILES, f"Alias {alias} maps to invalid target {target}"
        assert resolve_model_key(alias) == target


def test_resolve_model_key_alias() -> None:
    assert resolve_model_key(MODEL_ERGA08EVH7) == MODEL_ERGA08EAV3


def test_resolve_model_key_identity() -> None:
    assert resolve_model_key(MODEL_ERGA08EAV3) == MODEL_ERGA08EAV3


def test_resolve_model_key_empty() -> None:
    assert resolve_model_key("") == ""


def test_family_for_model_basisprofiel() -> None:
    assert family_for_model(MODEL_BASISPROFIEL) == MODEL_BASISPROFIEL


def test_family_for_model_custom() -> None:
    assert family_for_model(MODEL_CUSTOM) == MODEL_CUSTOM


def test_family_for_model_real() -> None:
    assert family_for_model(MODEL_ERGA04EAV3) == "erga"


def test_family_for_model_alias() -> None:
    assert family_for_model(MODEL_ERGA08EVH7) == "erga"


def test_family_for_model_empty() -> None:
    assert family_for_model("") == MODEL_BASISPROFIEL


def test_family_for_model_none() -> None:
    assert family_for_model(None) == MODEL_BASISPROFIEL


def test_family_for_model_unknown() -> None:
    assert family_for_model("zzz999") == MODEL_BASISPROFIEL


def test_models_in_family_basisprofiel() -> None:
    assert models_in_family(MODEL_BASISPROFIEL) == [MODEL_BASISPROFIEL]


def test_models_in_family_custom() -> None:
    assert models_in_family(MODEL_CUSTOM) == [MODEL_CUSTOM]


def test_models_in_family_erga() -> None:
    result = models_in_family("erga")
    assert MODEL_ERGA04EAV3 in result
    assert MODEL_ERGA08EAV3 in result
    assert MODEL_ERGA08EVH7 in result
    assert len(result) == 4


def test_models_in_family_unknown() -> None:
    assert models_in_family("zzz") == []


def test_every_choice_has_known_family() -> None:
    for m in MODEL_CHOICES:
        fam = family_for_model(m)
        assert fam in (MODEL_BASISPROFIEL, MODEL_CUSTOM) or fam in MODEL_FAMILIES, (
            f"{m} -> {fam}"
        )


def test_erga08evh7_present() -> None:
    assert MODEL_ERGA08EVH7 in MODEL_CHOICES
    assert MODEL_ERGA08EVH7 in MODEL_LABELS
    assert "ERGA08EVH7" in MODEL_LABELS[MODEL_ERGA08EVH7]


def test_alias_target_in_profiles() -> None:
    assert MODEL_ALIASES[MODEL_ERGA08EVH7] in MODEL_PROFILES


def test_get_profile_empty_string() -> None:
    p = get_profile("")
    assert p == get_profile(MODEL_BASISPROFIEL)


def test_get_profile_alias_equivalent() -> None:
    assert get_profile(MODEL_ERGA08EVH7) == get_profile(MODEL_ERGA08EAV3)


@pytest.mark.parametrize("variant, expected", [
    ("erg04eav3", MODEL_ERGA04EAV3),
    ("erg06eav3", MODEL_ERGA06EAV3),
    ("erg08eav3", MODEL_ERGA08EAV3),
])
def test_erg_aliases(variant: str, expected: str) -> None:
    """Test ESPAltherma ERG (missing A) aliases."""
    assert resolve_model_key(variant) == expected
