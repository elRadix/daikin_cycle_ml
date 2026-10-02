"""v1.4.1 regression: score_and_count + _cluster_label None."""
from __future__ import annotations

from custom_components.daikin_cycle_ml import coordinator as coord_mod
from custom_components.daikin_cycle_ml import sensor as s_mod
from custom_components.daikin_cycle_ml.coordinator import score_and_count
from custom_components.daikin_cycle_ml.engine.quality_scorer import score_cycle


class _Snap:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _CoordStub:
    def __init__(self, labels=None):
        self._cluster_labels = labels or {}

    def cluster_label(self, cid):
        return self._cluster_labels.get(cid)


class _BadCoord:
    def cluster_label(self, cid):
        raise RuntimeError('boom')


class _StoreStub:
    def __init__(self, raise_off=False, raise_inc=False):
        self._counters = {}
        self._raise_off = raise_off
        self._raise_inc = raise_inc

    def off_time_since_last(self, now):
        if self._raise_off:
            raise RuntimeError('off boom')
        return None

    def increment(self, key, delta=1):
        if self._raise_inc:
            raise RuntimeError('inc boom')
        self._counters[key] = self._counters.get(key, 0) + delta
        return self._counters[key]


# --- _cluster_label (BUG-4) ---


def test_cluster_label_returns_none_when_no_cluster():
    assert s_mod._cluster_label(_Snap(cluster_id=None), _CoordStub()) is None


def test_cluster_label_returns_none_when_label_missing():
    assert s_mod._cluster_label(_Snap(cluster_id=99), _CoordStub()) is None


def test_cluster_label_returns_none_on_exception():
    assert s_mod._cluster_label(_Snap(cluster_id=1), _BadCoord()) is None


def test_cluster_label_returns_label_when_present():
    c = _CoordStub({7: 'normal'})
    assert s_mod._cluster_label(_Snap(cluster_id=7), c) == 'normal'


# --- score_cycle unit ---


def test_score_cycle_empty_record_returns_100():
    assert score_cycle({}) == 100


def test_score_cycle_returns_int_in_range():
    rec = {'duration_s': 3600, 'dT_max': 8.0, 'buh_used': False}
    result = score_cycle(rec)
    assert isinstance(result, int)
    assert 0 <= result <= 100


# --- score_and_count integration (BUG-2/BUG-3) ---


def test_score_and_count_good_cycle():
    rec = {'duration_s': 3600, 'dT_max': 8.0}
    s = _StoreStub()
    score_and_count(rec, None, s, 0.0)
    assert rec['quality_score'] == 100
    assert s._counters.get('good_cycles_today') == 1
    assert 'bad_cycles_today' not in s._counters


def test_score_and_count_bad_cycle():
    rec = {'duration_s': 60, 'dT_max': 1.0, 'buh_used': True}
    s = _StoreStub()
    score_and_count(rec, None, s, 0.0)
    assert rec['quality_score'] == 40
    assert s._counters.get('bad_cycles_today') == 1
    assert 'good_cycles_today' not in s._counters


def test_score_and_count_boundary_70_is_good():
    rec = {'duration_s': 60}
    s = _StoreStub()
    score_and_count(rec, None, s, 0.0)
    assert rec['quality_score'] == 70
    assert s._counters.get('good_cycles_today') == 1


def test_score_and_count_exception_sets_none(monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError('boom')
    monkeypatch.setattr(coord_mod, 'score_cycle', _boom)
    rec = {'duration_s': 3600}
    s = _StoreStub()
    score_and_count(rec, None, s, 0.0)
    assert rec['quality_score'] is None
    assert 'good_cycles_today' not in s._counters
    assert 'bad_cycles_today' not in s._counters


def test_score_and_count_off_time_exception_swallowed():
    rec = {'duration_s': 3600}
    s = _StoreStub(raise_off=True)
    score_and_count(rec, None, s, 0.0)
    assert rec['quality_score'] == 100
    assert s._counters.get('good_cycles_today') == 1


def test_score_and_count_increment_exception_swallowed():
    rec = {'duration_s': 3600}
    s = _StoreStub(raise_inc=True)
    score_and_count(rec, None, s, 0.0)
    assert rec['quality_score'] == 100
