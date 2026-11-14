"""v1.22.8: CycleStore.cycles_intersecting edge paths.

Covers the 3 uncovered branches identified in full-suite coverage:
- store.py:336  (cycle without valid start_ts)
- store.py:338  (cycle without valid end_ts)
- store.py:343→332 (cycle with valid numbers but no overlap window)
"""
from __future__ import annotations

from custom_components.daikin_cycle_ml.storage.store import CycleStore


def test_skips_cycle_without_start_ts():
    """Line 336: start_ts not int/float -> continue."""
    store = CycleStore(maxlen=100)
    store.add_cycle({"end_ts": 200.0, "mode": "heating", "is_transient": 0})
    assert store.cycles_intersecting(0.0, 300.0) == []


def test_skips_cycle_with_none_start_ts():
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": None, "end_ts": 200.0,
        "mode": "heating", "is_transient": 0,
    })
    assert store.cycles_intersecting(0.0, 300.0) == []


def test_skips_cycle_with_string_start_ts():
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": "not-a-number", "end_ts": 200.0,
        "mode": "heating", "is_transient": 0,
    })
    assert store.cycles_intersecting(0.0, 300.0) == []


def test_skips_cycle_without_end_ts():
    """Line 338: end_ts not int/float -> continue (open cycles not returned)."""
    store = CycleStore(maxlen=100)
    store.add_cycle({"start_ts": 100.0, "mode": "heating", "is_transient": 0})
    assert store.cycles_intersecting(0.0, 300.0) == []


def test_skips_cycle_with_none_end_ts():
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 100.0, "end_ts": None,
        "mode": "heating", "is_transient": 0,
    })
    assert store.cycles_intersecting(0.0, 300.0) == []


def test_skips_cycle_with_string_end_ts():
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 100.0, "end_ts": "bad",
        "mode": "heating", "is_transient": 0,
    })
    assert store.cycles_intersecting(0.0, 300.0) == []


def test_no_overlap_cycle_before_window():
    """Line 343→332: c_end <= s_ts -> condition False -> loop continues."""
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 0.0, "end_ts": 50.0,  # entirely before window
        "mode": "heating", "is_transient": 0,
    })
    assert store.cycles_intersecting(100.0, 300.0) == []


def test_no_overlap_cycle_after_window():
    """Line 343→332: c_start >= e_ts -> condition False -> loop continues."""
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 400.0, "end_ts": 500.0,  # entirely after window
        "mode": "heating", "is_transient": 0,
    })
    assert store.cycles_intersecting(100.0, 300.0) == []


def test_no_overlap_boundary_touching_end():
    """Boundary: c_end == s_ts (not >) -> no overlap."""
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 50.0, "end_ts": 100.0,  # ends exactly at window start
        "mode": "heating", "is_transient": 0,
    })
    assert store.cycles_intersecting(100.0, 300.0) == []


def test_no_overlap_boundary_touching_start():
    """Boundary: c_start == e_ts (not <) -> no overlap."""
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 300.0, "end_ts": 400.0,  # starts exactly at window end
        "mode": "heating", "is_transient": 0,
    })
    assert store.cycles_intersecting(100.0, 300.0) == []


def test_positive_case_cycle_inside_window():
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 150.0, "end_ts": 250.0,
        "mode": "heating", "is_transient": 0,
    })
    out = store.cycles_intersecting(100.0, 300.0)
    assert len(out) == 1
    assert out[0]["start_ts"] == 150.0


def test_positive_case_cycle_spans_window():
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 50.0, "end_ts": 400.0,
        "mode": "heating", "is_transient": 0,
    })
    assert len(store.cycles_intersecting(100.0, 300.0)) == 1


def test_transient_excluded_by_default():
    """Line 339-342: default exclude_transient=True skips transients."""
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 150.0, "end_ts": 250.0,
        "mode": "heating", "is_transient": 1,
    })
    assert store.cycles_intersecting(100.0, 300.0) == []


def test_transient_included_when_disabled():
    store = CycleStore(maxlen=100)
    store.add_cycle({
        "start_ts": 150.0, "end_ts": 250.0,
        "mode": "heating", "is_transient": 1,
    })
    out = store.cycles_intersecting(100.0, 300.0, exclude_transient=False)
    assert len(out) == 1


def test_mixed_cycles_all_branches():
    """All code paths in one pass: bad start, bad end, transient, overlap, no-overlap."""
    store = CycleStore(maxlen=100)
    store.add_cycle({"end_ts": 200.0})                                 # 336
    store.add_cycle({"start_ts": 100.0})                               # 338
    store.add_cycle({"start_ts": 150.0, "end_ts": 250.0,
                     "is_transient": 1})                                # 342
    store.add_cycle({"start_ts": 0.0, "end_ts": 50.0,
                     "is_transient": 0})                                # 343→332
    store.add_cycle({"start_ts": 400.0, "end_ts": 500.0,
                     "is_transient": 0})                                # 343→332
    store.add_cycle({"start_ts": 150.0, "end_ts": 250.0,
                     "mode": "heating", "is_transient": 0})             # 344 (append)
    out = store.cycles_intersecting(100.0, 300.0)
    assert len(out) == 1
    assert out[0]["mode"] == "heating"


def test_empty_store_returns_empty():
    store = CycleStore(maxlen=100)
    assert store.cycles_intersecting(0.0, 1000.0) == []
