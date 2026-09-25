"""Tests for MultiBaseline (Batch 11a)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.ml.multi_baseline import (
    MODE_UNKNOWN,
    MultiBaseline,
)


def test_get_creates_on_first_access():
    mb = MultiBaseline(2)
    assert mb.modes() == []
    mb.get("Heating")
    assert "Heating" in mb.modes()


def test_separate_baselines_per_mode():
    mb = MultiBaseline(1)
    mb.update("Heating", [10.0])
    mb.update("DHW", [100.0])
    assert mb.get("Heating").mean == [10.0]
    assert mb.get("DHW").mean == [100.0]


def test_unknown_fallback_for_none():
    mb = MultiBaseline(1)
    mb.update(None, [5.0])
    assert MODE_UNKNOWN in mb.modes()
    assert mb.get(None).sample_count == 1


def test_unknown_fallback_for_empty_string():
    mb = MultiBaseline(1)
    mb.update("", [5.0])
    assert MODE_UNKNOWN in mb.modes()


def test_modes_returns_only_populated():
    mb = MultiBaseline(1)
    mb.update("Heating", [1.0])
    assert mb.modes() == ["Heating"]


def test_update_dispatches_to_mode():
    mb = MultiBaseline(1)
    mb.update("Cooling", [3.0])
    mb.update("Cooling", [5.0])
    assert mb.get("Cooling").sample_count == 2


def test_total_samples_sums_all_modes():
    mb = MultiBaseline(1)
    mb.update("Heating", [1.0])
    mb.update("Heating", [2.0])
    mb.update("DHW", [3.0])
    assert mb.total_samples() == 3


def test_to_dict_roundtrip():
    mb = MultiBaseline(2, alpha=0.05)
    mb.update("Heating", [1.0, 2.0])
    mb.update("DHW", [3.0, 4.0])
    d = mb.to_dict()
    mb2 = MultiBaseline.from_dict(d)
    assert sorted(mb2.modes()) == ["DHW", "Heating"]
    assert mb2.total_samples() == 2


def test_from_dict_restores_mean():
    mb = MultiBaseline(1)
    mb.update("Heating", [42.0])
    d = mb.to_dict()
    mb2 = MultiBaseline.from_dict(d)
    assert mb2.get("Heating").mean == [42.0]


def test_dim_property():
    assert MultiBaseline(5).dim == 5


def test_alpha_propagated_to_sub_baseline():
    mb = MultiBaseline(1, alpha=0.2)
    b = mb.get("Heating")
    assert b.alpha == 0.2


def test_alpha_restored_from_dict():
    mb = MultiBaseline(1, alpha=0.2)
    mb2 = MultiBaseline.from_dict(mb.to_dict())
    assert mb2.alpha == 0.2


def test_outlier_skip_propagates():
    mb = MultiBaseline(1, alpha=0.1, outlier_skip_z=2.0,
                       min_samples_before_skip=3)
    for i in range(5):
        mb.update("Heating", [float(i)])
    n = mb.get("Heating").sample_count
    ok = mb.update("Heating", [1e9])
    assert ok is False
    assert mb.get("Heating").sample_count == n


def test_to_json_roundtrip():
    mb = MultiBaseline(2)
    mb.update("DHW", [1.0, 2.0])
    raw = mb.to_json()
    mb2 = MultiBaseline.from_json(raw)
    assert "DHW" in mb2.modes()


def test_from_dict_empty_baselines():
    mb = MultiBaseline.from_dict({"dim": 2})
    assert mb.modes() == []
