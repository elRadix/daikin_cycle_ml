"""Tests for engine.timer_health (Batch 8d)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.timer_health import (
    DEFAULT_MAX_DURATION_MIN,
    STALE_THRESHOLD_S,
    clamp_cycle_duration,
    is_stale,
    reconcile,
)


# ---------- clamp_cycle_duration ----------

def test_clamp_none_returns_zero():
    assert clamp_cycle_duration(None) == 0


def test_clamp_str_returns_zero():
    assert clamp_cycle_duration("not-a-number") == 0


def test_clamp_negative_returns_zero():
    assert clamp_cycle_duration(-5) == 0


def test_clamp_valid_truncates():
    assert clamp_cycle_duration(100.9) == 100


def test_clamp_int_ok():
    assert clamp_cycle_duration(1800) == 1800


def test_clamp_caps_at_max():
    # 999999s clamped to 240min=14400s
    assert clamp_cycle_duration(999999) == DEFAULT_MAX_DURATION_MIN * 60


def test_clamp_custom_max_min():
    assert clamp_cycle_duration(999999, max_min=1) == 60


def test_clamp_zero_max_min_collapses():
    assert clamp_cycle_duration(999999, max_min=0) == 0


# ---------- is_stale ----------

def test_is_stale_none_is_true():
    assert is_stale(None) is True


def test_is_stale_fresh_returns_false():
    assert is_stale(1000.0, now=1001.0) is False


def test_is_stale_old_returns_true():
    assert is_stale(1000.0, now=1000.0 + STALE_THRESHOLD_S + 10) is True


def test_is_stale_default_now_uses_clock():
    # very old timestamp -> True (uses time.time internally)
    assert is_stale(1.0) is True


def test_is_stale_at_threshold_returns_false():
    # exactly threshold: (now - last) == threshold, not >, so False
    assert is_stale(1000.0, now=1000.0 + STALE_THRESHOLD_S) is False


# ---------- reconcile ----------

def test_reconcile_none_returns_none():
    assert reconcile(None, 1000.0) is None


def test_reconcile_future_timestamp_returns_none():
    assert reconcile(2000.0, 1000.0) is None


def test_reconcile_gap_too_large_returns_none():
    # 10000s gap vs 30s * 3 = 90s threshold
    assert reconcile(1000.0, 11000.0) is None


def test_reconcile_within_window_returns_last_ts():
    assert reconcile(1000.0, 1010.0) == 1000.0


def test_reconcile_custom_gap_factor():
    # 100s gap, interval=30, factor=10 -> 300s threshold -> OK
    assert reconcile(1000.0, 1100.0, expected_interval_s=30.0, gap_factor=10.0) == 1000.0
