"""COV-8A: non-coordinator coverage edges.

Marker: COV8A
"""
from __future__ import annotations


def test_flatten_notify_choice_rejects_non_dict_non_str():
    from custom_components.daikin_cycle_ml.config_flow import (
        _flatten_notify_choice,
    )
    assert _flatten_notify_choice(42) == ""
    assert _flatten_notify_choice([1, 2]) == ""
    assert _flatten_notify_choice(3.14) == ""
    assert _flatten_notify_choice(None) == ""
    assert _flatten_notify_choice("notify.x") == "notify.x"


def test_action_engine_add_skips_duplicate():
    from custom_components.daikin_cycle_ml.engine.action_engine import (
        ActionAdvice, _add,
    )

    def _mk(code):
        return ActionAdvice(priority=1, category="anomaly", code=code,
                            title="t", description="d", context={})

    out = []
    _add(out, _mk("dup_code"))
    _add(out, _mk("dup_code"))
    assert len(out) == 1


def test_cycle_detector_safe_float_bool():
    from custom_components.daikin_cycle_ml.engine.cycle_detector import (
        _safe_float,
    )
    assert _safe_float(True) is None
    assert _safe_float(False) is None
    assert _safe_float(3.5) == 3.5
    assert _safe_float("x") is None
    assert _safe_float(None) is None


def test_cycle_detector_classify_mode_unmatched():
    from custom_components.daikin_cycle_ml.const import ATTR_OPERATION_MODE
    from custom_components.daikin_cycle_ml.engine.cycle_detector import (
        classify_mode,
    )
    assert classify_mode({ATTR_OPERATION_MODE: "totally_unknown"}) == "unknown"
    assert classify_mode({}) == "unknown"


def test_baseline_top_dim_empty():
    from custom_components.daikin_cycle_ml.ml.baseline import Baseline
    b = Baseline(dim=12)
    assert b.top_dim([0.0] * 12) is None


def test_adaptive_thresholds_suggest_empty():
    from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
        AdaptiveThresholds,
    )
    a = AdaptiveThresholds()
    assert a.suggest("heating") == {}


def test_adaptive_thresholds_from_dict_non_list_values():
    from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
        AdaptiveThresholds,
    )
    data = {"min_samples": 5,
            "run_min": {"heating": "not_a_list"},
            "off_min": {"heating": 42},
            "daily_cycles": "nope"}
    a = AdaptiveThresholds.from_dict(data)
    assert isinstance(a, AdaptiveThresholds)
