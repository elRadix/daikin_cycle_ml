"""v1.12.0: record_short_run / record_short_off wiring (issue #105 wiring)."""
from __future__ import annotations

import pytest

import custom_components.daikin_cycle_ml.coordinator as co
from custom_components.daikin_cycle_ml.coordinator import score_and_count
from custom_components.daikin_cycle_ml.storage.store import CycleStore


@pytest.fixture
def patched_score(monkeypatch):
    """Replace score_cycle with a fixed scorer (returns 50 -> bad_cycles)."""
    monkeypatch.setattr(co, "score_cycle", lambda *a, **k: 50)


def _rec(dur):
    return {"duration_s": dur, "start_ts": 1000.0, "end_ts": 1000.0 + (dur or 0)}


def _store_with_off(off_s):
    s = CycleStore()
    s.off_time_since_last = lambda now: off_s
    return s


def test_records_short_run_when_below_threshold(patched_score):
    """dur 10 min < 20 min default -> short_runs_today=1."""
    s = _store_with_off(3600.0)  # off ok, not short
    score_and_count(_rec(dur=600), {}, s, now=2000.0)
    assert s.get("short_runs_today") == 1
    assert s.get("short_offs_today", 0) == 0


def test_skips_short_run_when_above_threshold(patched_score):
    """dur 30 min > 20 min default -> no short_run recorded."""
    s = _store_with_off(3600.0)
    score_and_count(_rec(dur=1800), {}, s, now=2000.0)
    assert s.get("short_runs_today", 0) == 0


def test_skips_short_run_when_dur_none(patched_score):
    """duration_s None -> isinstance False -> skipped."""
    s = _store_with_off(3600.0)
    score_and_count({"duration_s": None}, {}, s, now=2000.0)
    assert s.get("short_runs_today", 0) == 0


def test_records_short_off_when_below_threshold(patched_score):
    """off 1 min < 5 min default -> short_offs_today=1, no short_run."""
    s = _store_with_off(60.0)
    score_and_count(_rec(dur=1800), {}, s, now=2000.0)
    assert s.get("short_offs_today") == 1
    assert s.get("short_runs_today", 0) == 0


def test_skips_short_off_when_above_threshold(patched_score):
    """off 10 min > 5 min default -> no short_off."""
    s = _store_with_off(600.0)
    score_and_count(_rec(dur=1800), {}, s, now=2000.0)
    assert s.get("short_offs_today", 0) == 0


def test_skips_short_off_when_off_s_none(patched_score):
    """off_time_since_last returns None (empty store) -> skipped."""
    s = _store_with_off(None)
    score_and_count(_rec(dur=1800), {}, s, now=2000.0)
    assert s.get("short_offs_today", 0) == 0


def test_isolates_record_short_run_exception(patched_score):
    """record_short_run raises -> scoring still runs, bad_cycles=1."""
    s = _store_with_off(3600.0)

    def boom():
        raise RuntimeError("boom")

    s.record_short_run = boom
    score_and_count(_rec(dur=600), {}, s, now=2000.0)
    # Score 50 < 70 -> bad_cycles_today; proves pipeline continued
    assert s.get("bad_cycles_today") == 1


def test_isolates_record_short_off_exception(patched_score):
    """record_short_off raises -> scoring still runs, bad_cycles=1."""
    s = _store_with_off(60.0)

    def boom():
        raise RuntimeError("boom")

    s.record_short_off = boom
    score_and_count(_rec(dur=1800), {}, s, now=2000.0)
    assert s.get("bad_cycles_today") == 1
