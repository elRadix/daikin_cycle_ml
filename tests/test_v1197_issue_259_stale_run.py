"""Issue #259: short_run and short_off must ignore stale (>1h) cycles."""
from __future__ import annotations

import time
from types import SimpleNamespace

from custom_components.daikin_cycle_ml import binary_sensor as bs
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _mk_cycle(*, end_offset_s, dur=300, off_s=None, mode="heating", is_trans=0):
    now = time.time()
    c = {
        "start_ts": now + end_offset_s - dur,
        "end_ts": now + end_offset_s,
        "duration_s": dur, "mode": mode, "is_transient": is_trans,
    }
    if off_s is not None:
        c["off_s"] = off_s
    return c


def _mk_store(cycles):
    s = CycleStore(maxlen=100)
    for c in cycles:
        s.add_cycle(c)
    return s


def _mk_snap(mode="heating"):
    return SimpleNamespace(mode=mode, state="running")


def _mk_coord(store, options=None):
    return SimpleNamespace(store=store, options=options or {}, data=_mk_snap())


def test_issue_259_stale_short_run_does_not_fire():
    store = _mk_store([_mk_cycle(end_offset_s=-7200, dur=300)])
    assert bs._is_short_run(_mk_snap(), _mk_coord(store)) is False


def test_issue_259_just_over_1h_short_run_does_not_fire():
    store = _mk_store([_mk_cycle(end_offset_s=-3601, dur=300)])
    assert bs._is_short_run(_mk_snap(), _mk_coord(store)) is False


def test_issue_259_fresh_short_run_still_fires():
    store = _mk_store([_mk_cycle(end_offset_s=-30, dur=300)])
    assert bs._is_short_run(_mk_snap(), _mk_coord(store)) is True


def test_issue_259_stale_short_off_does_not_fire():
    store = _mk_store([_mk_cycle(end_offset_s=-7200, dur=600, off_s=30)])
    assert bs._is_short_off(_mk_snap(), _mk_coord(store)) is False


def test_issue_259_fresh_short_off_still_fires():
    store = _mk_store([_mk_cycle(end_offset_s=-30, dur=300, off_s=30)])
    assert bs._is_short_off(_mk_snap(), _mk_coord(store)) is True
