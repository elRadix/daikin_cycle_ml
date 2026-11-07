"""Tests for const.py invariant validators (v1.20.0 #281).

R643: no # pragma: no cover. The validators exist to fail loud on drift;
each invariant gets its own negative test that monkeypatches the module
constant and asserts RuntimeError with a specific message fragment.
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml import const as C


def test_attribute_sets_valid_passes() -> None:
    """Baseline: shipped constants satisfy the invariant."""
    C._validate_attribute_sets()  # no raise


def test_attribute_sets_duplicate_raises(monkeypatch) -> None:
    """Duplicate in CONSUMED_ATTRIBUTES is a fatal drift."""
    monkeypatch.setattr(C, "CONSUMED_ATTRIBUTES", ["A", "B", "A"])
    with pytest.raises(RuntimeError, match="duplicates"):
        C._validate_attribute_sets()


def test_attribute_sets_required_not_subset_raises(monkeypatch) -> None:
    """If REQUIRED has a label not in CONSUMED, that's a fatal drift."""
    monkeypatch.setattr(C, "CONSUMED_ATTRIBUTES", ["A", "B"])
    monkeypatch.setattr(C, "REQUIRED_ATTRIBUTES", ["A", "C"])  # C not in consumed
    with pytest.raises(RuntimeError, match="must be a subset"):
        C._validate_attribute_sets()


def test_features_mapping_valid_passes() -> None:
    """Baseline: shipped features map satisfies the invariant."""
    C._validate_features_mapping()  # no raise


def test_features_mapping_missing_label_raises(monkeypatch) -> None:
    """Missing feature entry for a consumed label is a fatal drift."""
    monkeypatch.setattr(C, "CONSUMED_ATTRIBUTES", ["A", "B"])
    monkeypatch.setattr(C, "CONSUMED_ATTRIBUTE_FEATURES", {"A": "feat_a"})
    with pytest.raises(RuntimeError, match="must map every"):
        C._validate_features_mapping()


def test_features_mapping_extra_label_raises(monkeypatch) -> None:
    """Extra feature for a non-consumed label is also fatal drift."""
    monkeypatch.setattr(C, "CONSUMED_ATTRIBUTES", ["A"])
    monkeypatch.setattr(
        C, "CONSUMED_ATTRIBUTE_FEATURES", {"A": "fa", "B": "fb"},
    )
    with pytest.raises(RuntimeError, match="must map every"):
        C._validate_features_mapping()


# ---------- const.py: pre-existing branch coverage ----------


def test_buh_step_kw_for_model_none_returns_default() -> None:
    """Line 532-533: model is None/empty -> BUH_STEP_KW_DEFAULT."""
    from custom_components.daikin_cycle_ml.const import (
        BUH_STEP_KW_DEFAULT, buh_step_kw_for_model,
    )
    assert buh_step_kw_for_model(None) == BUH_STEP_KW_DEFAULT
    assert buh_step_kw_for_model("") == BUH_STEP_KW_DEFAULT


def test_buh_step_kw_for_model_uppercased() -> None:
    """Line 534: model key uppercased before dict lookup (unknown -> default)."""
    from custom_components.daikin_cycle_ml.const import (
        BUH_STEP_KW_DEFAULT, buh_step_kw_for_model,
    )
    assert buh_step_kw_for_model("NONEXISTENT_MODEL_XYZ") == BUH_STEP_KW_DEFAULT


def test_models_in_family_basisprofiel_returns_self() -> None:
    """Line 821-822: basis family -> single-item list."""
    from custom_components.daikin_cycle_ml.const import (
        MODEL_BASISPROFIEL, models_in_family,
    )
    assert models_in_family(MODEL_BASISPROFIEL) == [MODEL_BASISPROFIEL]


def test_models_in_family_custom_returns_self() -> None:
    """Line 821-822: custom family -> single-item list."""
    from custom_components.daikin_cycle_ml.const import (
        MODEL_CUSTOM, models_in_family,
    )
    assert models_in_family(MODEL_CUSTOM) == [MODEL_CUSTOM]
