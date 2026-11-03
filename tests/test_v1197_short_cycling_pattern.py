"""v1.19.7 #11: short_cycling_pattern detection tests."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import binary_sensor as bs
from custom_components.daikin_cycle_ml.const import (
    DEFAULT_SHORT_CYCLING_MIN_CYCLES,
    DEFAULT_SHORT_CYCLING_WINDOW_MIN,
    MODE_DHW,
    MODE_HEATING,
    NOTIF_ID_SHORT_CYCLING_PATTERN,
    ALERT_DEDUP_DEFAULTS,
    ALERT_GROUP_MAP,
    ALERT_TYPE_EMOJI,
)
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
    NOTIF_ID_BY_TYPE,
)
from custom_components.daikin_cycle_ml.engine.status_report import (
    ALERT_ADVICE,
    ALERT_SCHEMA,
    ALERT_TITLES,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _cycle(now, end_offset_s, dur_s, mode=MODE_HEATING, is_transient=0):
    return {
        "start_ts": now + end_offset_s - dur_s,
        "end_ts": now + end_offset_s,
        "duration_s": dur_s,
        "mode": mode,
        "is_transient": is_transient,
    }


def _store_with(cycles):
    s = CycleStore(maxlen=200)
    for c in cycles:
        s.add_cycle(c)
    return s


def _coord(store, options=None):
    return SimpleNamespace(store=store, options=options or {})


def test_count_short_basic():
    now = time.time()
    store = _store_with([
        _cycle(now, -100, 60),
        _cycle(now, -500, 90),
        _cycle(now, -1000, 120),
    ])
    assert store.count_short_in_window_mode(now, 3600, 1200, MODE_HEATING) == 3


def test_count_short_filters_duration():
    now = time.time()
    store = _store_with([
        _cycle(now, -100, 60),
        _cycle(now, -500, 1500),
        _cycle(now, -1000, 90),
    ])
    assert store.count_short_in_window_mode(now, 3600, 1200, MODE_HEATING) == 2


def test_count_short_filters_mode():
    now = time.time()
    store = _store_with([
        _cycle(now, -100, 60, mode=MODE_HEATING),
        _cycle(now, -200, 60, mode=MODE_DHW),
        _cycle(now, -300, 60, mode=MODE_HEATING),
    ])
    assert store.count_short_in_window_mode(now, 3600, 1200, MODE_HEATING) == 2
    assert store.count_short_in_window_mode(now, 3600, 1200, MODE_DHW) == 1


def test_count_short_filters_transient():
    now = time.time()
    store = _store_with([
        _cycle(now, -100, 60, is_transient=0),
        _cycle(now, -200, 60, is_transient=1),
        _cycle(now, -300, 60, is_transient=0),
    ])
    assert store.count_short_in_window_mode(now, 3600, 1200, MODE_HEATING) == 2


def test_count_short_future_guard():
    """Cycles starting >60s in future are excluded (mirrors cycles_in_window_mode)."""
    now = time.time()
    store = _store_with([
        _cycle(now, -100, 60),
        _cycle(now, +200, 60),
        _cycle(now, -200, 60),
    ])
    assert store.count_short_in_window_mode(now, 3600, 1200, MODE_HEATING) == 2


def test_count_short_skips_invalid_fields():
    now = time.time()
    store = _store_with([
        {"start_ts": "bad", "duration_s": 60, "mode": MODE_HEATING, "is_transient": 0},
        {"start_ts": now - 100, "duration_s": "bad", "mode": MODE_HEATING, "is_transient": 0},
        _cycle(now, -200, 60),
    ])
    assert store.count_short_in_window_mode(now, 3600, 1200, MODE_HEATING) == 1


def test_pattern_three_short_true():
    now = time.time()
    store = _store_with([
        _cycle(now, -100, 60),
        _cycle(now, -500, 90),
        _cycle(now, -1000, 120),
    ])
    assert bs._is_short_cycling_pattern(None, _coord(store)) is True


def test_pattern_two_short_false():
    now = time.time()
    store = _store_with([_cycle(now, -100, 60), _cycle(now, -500, 90)])
    assert bs._is_short_cycling_pattern(None, _coord(store)) is False


def test_pattern_long_runs_false():
    now = time.time()
    store = _store_with([
        _cycle(now, -100, 1500),
        _cycle(now, -2000, 1500),
        _cycle(now, -4000, 1500),
    ])
    assert bs._is_short_cycling_pattern(None, _coord(store)) is False


def test_pattern_custom_options():
    now = time.time()
    store = _store_with([_cycle(now, -100, 60), _cycle(now, -500, 90)])
    c = _coord(store, options={
        "short_cycling_window_min": 30,
        "short_cycling_min_cycles": 2,
    })
    assert bs._is_short_cycling_pattern(None, c) is True


def test_pattern_missing_store_method_returns_false():
    c = SimpleNamespace(store=MagicMock(spec=[]), options={})
    assert bs._is_short_cycling_pattern(None, c) is False


def test_pattern_non_numeric_return_returns_false():
    m = MagicMock()
    m.count_short_in_window_mode = MagicMock(return_value="not-a-number")
    c = SimpleNamespace(store=m, options={})
    assert bs._is_short_cycling_pattern(None, c) is False


def test_short_runs_returns_newest_first():
    now = time.time()
    store = _store_with([
        _cycle(now, -100, 60),
        _cycle(now, -500, 90),
        _cycle(now, -1000, 120),
    ])
    rows = store.short_runs_in_window_mode(now, 3600, 1200, MODE_HEATING, limit=10)
    assert len(rows) == 3
    assert rows[0]["start_ts"] > rows[1]["start_ts"] > rows[2]["start_ts"]
    for r in rows:
        assert set(r.keys()) == {"start_ts", "duration_s"}


def test_short_runs_respects_limit():
    now = time.time()
    store = _store_with([_cycle(now, -i * 100, 60) for i in range(1, 16)])
    rows = store.short_runs_in_window_mode(now, 3600, 1200, MODE_HEATING, limit=5)
    assert len(rows) == 5


def test_attrs_returns_dict_with_all_keys():
    now = time.time()
    store = _store_with([
        _cycle(now, -100, 60),
        _cycle(now, -500, 90),
        _cycle(now, -1000, 120),
    ])
    c = _coord(store, options={
        "short_cycling_window_min": 60,
        "short_cycling_min_cycles": 3,
        "short_run_threshold_min": 20,
    })
    r = bs._short_cycling_pattern_attrs(None, c)
    assert isinstance(r, dict)
    assert r["window_min"] == 60
    assert r["min_cycles_threshold"] == 3
    assert r["short_run_threshold_min"] == 20
    assert r["pattern_count_60min"] == 3
    assert len(r["recent_short_runs"]) == 3


def test_attrs_returns_none_on_exception():
    c = SimpleNamespace(store=MagicMock(spec=[]), options={})
    assert bs._short_cycling_pattern_attrs(None, c) is None


def test_all_registries_have_short_cycling_pattern():
    assert "short_cycling_pattern" in BINARY_ALERT_MAP
    assert "short_cycling_pattern" in NOTIF_ID_BY_TYPE
    assert "short_cycling_pattern" in ALERT_SCHEMA
    assert "short_cycling_pattern" in ALERT_TITLES["en"]
    assert "short_cycling_pattern" in ALERT_TITLES["nl"]
    assert "short_cycling_pattern" in ALERT_ADVICE["en"]
    assert "short_cycling_pattern" in ALERT_ADVICE["nl"]
    assert "short_cycling_pattern" in ALERT_TYPE_EMOJI
    assert "short_cycling_pattern" in ALERT_GROUP_MAP
    assert "short_cycling_pattern" in ALERT_DEDUP_DEFAULTS


def test_alert_schema_has_minimum_tuples():
    assert len(ALERT_SCHEMA["short_cycling_pattern"]) >= 4


def test_notif_id_format():
    assert NOTIF_ID_SHORT_CYCLING_PATTERN.endswith("_short_cycling_pattern")


def test_defaults():
    assert DEFAULT_SHORT_CYCLING_WINDOW_MIN == 60
    assert DEFAULT_SHORT_CYCLING_MIN_CYCLES == 3


def test_dedup_window():
    assert ALERT_DEDUP_DEFAULTS["short_cycling_pattern"] == 60
