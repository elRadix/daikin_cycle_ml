"""#443 ML v2: behaviour baseline, evaluate_behaviour, per-mode k-means.

Pure-module tests (no Home Assistant). The coordinator / DB wiring is in
tests/test_443_ml_v2_wiring.py.
"""
from __future__ import annotations

import math
import random

import pytest

from custom_components.daikin_cycle_ml.engine.anomaly_engine import evaluate_behaviour
from custom_components.daikin_cycle_ml.ml import kmeans_v2
from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    MAX_DAYS,
    MAX_SAMPLES_PER_MODE,
    AdaptiveThresholds,
)
from custom_components.daikin_cycle_ml.ml.behaviour_baseline import (
    BEHAVIOUR_DIMS,
    ML_VERSION,
    READY_SAMPLES,
    BehaviourBaseline,
    BehaviourScore,
    _Stat,
    behaviour_values,
    feature_index,
    outdoor_band,
    scaled_value,
)
from custom_components.daikin_cycle_ml.ml.features import FEATURE_NAMES


def _vals(dur_min=45.0, dt=5.0, rps=40.0, cop=4.0, lwt=35.0, kw=6.0):
    return {"duration_s": dur_min * 60, "dT_avg": dt, "rps_avg": rps,
            "cop_avg": cop, "lwt_avg": lwt, "thermal_kw_avg": kw}


def _warm(bb, n=40, mode="heating", outdoor=5.0, seed=1):
    rng = random.Random(seed)
    for _ in range(n):
        bb.update(mode, _vals(dur_min=45 * math.exp(rng.gauss(0, 0.1)),
                              dt=5 + rng.gauss(0, 0.3), cop=4 + rng.gauss(0, 0.1)), outdoor)


# ---------- behaviour_values / helpers ----------

def test_behaviour_values_zero_means_missing():
    rec = {"duration_s": 600, "dT_avg": 0.0, "rps_avg": 0, "cop_avg": 0.0,
           "thermal_kw_avg": 0.0}
    v = behaviour_values(rec)
    assert v["duration_s"] == 600.0
    assert all(v[k] is None for k in ("dT_avg", "rps_avg", "cop_avg", "lwt_avg", "thermal_kw_avg"))


def test_behaviour_values_overrides_and_types():
    rec = {"duration_s": True, "dT_avg": -1.5, "cop_avg": 9.0, "rps_avg": "40"}
    v = behaviour_values(rec, cop_avg=3.5, lwt_avg=33.0, thermal_kw_avg=float("nan"))
    assert v["duration_s"] is None          # bool is not a number
    assert v["dT_avg"] == -1.5              # a negative dT is a measurement (defrost)
    assert v["cop_avg"] == 3.5              # override wins
    assert v["lwt_avg"] == 33.0
    assert v["rps_avg"] is None             # strings are not parsed
    assert v["thermal_kw_avg"] is None      # NaN dropped


def test_outdoor_band_and_scaling():
    assert outdoor_band(-3.0) == -4
    assert outdoor_band(5.9) == 4
    assert outdoor_band(8) == 8
    assert outdoor_band(None) is None
    assert outdoor_band("cold") is None
    assert scaled_value("duration_s", 600) == pytest.approx(math.log(10))
    assert scaled_value("duration_s", 10) == 0.0        # floored at 1 minute
    assert scaled_value("cop_avg", 4.2) == 4.2
    assert feature_index("cop_avg") == FEATURE_NAMES.index("cop_avg")
    assert feature_index(None) is None
    for name in BEHAVIOUR_DIMS:   # every dimension maps to a feature
        assert feature_index(name) is not None


def test_stat_from_list_garbage():
    assert _Stat.from_list(None).n == 0
    assert _Stat.from_list(["x", 1, 2]).n == 0
    st = _Stat.from_list([3, 1.5, 0.25])
    assert (st.n, st.mean, st.var) == (3, 1.5, 0.25)
    assert st.to_list() == [3, 1.5, 0.25]


def test_score_empty_properties():
    sc = BehaviourScore(z={}, group="heating")
    assert sc.max_abs_z == 0.0
    assert sc.top is None


# ---------- learning ----------

def test_warm_up_not_scored_until_ready():
    bb = BehaviourBaseline()
    for i in range(READY_SAMPLES - 1):
        bb.update("heating", _vals(), 5.0)
        assert bb.score("heating", _vals(dur_min=5), 5.0).z == {}, i
    bb.update("heating", _vals(), 5.0)
    assert bb.score("heating", _vals(), 5.0).z


def test_warm_up_is_unbiased():
    """alpha_eff = 1/n: after the warm-up the mean is the sample mean."""
    bb = BehaviourBaseline()
    xs = [3.0 + 0.05 * i for i in range(20)]
    for x in xs:
        bb.update("heating", {"cop_avg": x})
    mean = bb._groups["heating"]["cop_avg"].mean
    assert mean == pytest.approx(sum(xs) / len(xs), abs=1e-9)


def test_std_floor_limits_z():
    bb = BehaviourBaseline()
    for _ in range(30):
        bb.update("heating", {"dT_avg": 5.0})
    # zero variance: the 0.4 K floor applies, 0.2 K is half a sigma
    assert bb.score("heating", {"dT_avg": 5.2}).z["dT_avg"] == pytest.approx(0.5)


def test_huber_clip_bounds_an_outlier():
    bb = BehaviourBaseline()
    _warm(bb, n=60)
    st = bb._groups["heating"]["cop_avg"]
    before, sd = st.mean, st.std(0.15)
    bb.update("heating", {"cop_avg": 40.0}, 5.0)
    assert st.mean - before <= 0.02 * 3.0 * sd + 1e-9


def test_band_fallback_then_band():
    bb = BehaviourBaseline()
    _warm(bb, n=30, outdoor=5.0)          # band 4 gets 30 samples
    assert bb.score("heating", _vals(), 5.5).group == "heating|4"
    assert bb.score("heating", _vals(), -6.0).group == "heating"   # band -8 empty
    assert bb.score("heating", _vals(), None).group == "heating"
    assert bb.bands("heating") == {4: 30}


def test_missing_dims_are_skipped():
    bb = BehaviourBaseline()
    _warm(bb)
    z = bb.score("heating", {"duration_s": 2700.0, "cop_avg": None}, 5.0).z
    assert set(z) == {"duration_s"}
    assert bb.update("heating", {"cop_avg": None}) is False


def test_persistence_rule():
    bb = BehaviourBaseline()
    _warm(bb, n=60)
    normal = _vals()
    bad = _vals(dt=5.0 + 4.5 * 0.4)        # ~4.5 sigma on dT (floor 0.4 K)
    _sc, alert = bb.observe("heating", bad, 5.0, learn=False)
    assert alert is False                  # once at z 4..6: watch only
    _sc, alert = bb.observe("heating", bad, 5.0, learn=False)
    assert alert is True                   # twice in a row
    bb.observe("heating", normal, 5.0, learn=False)
    assert bb._streak["heating"] == 0
    _sc, alert = bb.observe("heating", _vals(dt=5.0 + 8 * 0.4), 5.0, learn=False)
    assert alert is True                   # z >= 6 once


def test_observe_learns_after_scoring():
    bb = BehaviourBaseline()
    bb.observe("dhw", _vals())
    assert bb.sample_count("dhw") == 1
    bb.observe("dhw", _vals(), learn=False)
    assert bb.sample_count("dhw") == 1


def test_surface_modes_reset_and_alpha():
    bb = BehaviourBaseline(alpha=5)
    assert bb.alpha == 1.0
    assert bb.dim == len(BEHAVIOUR_DIMS)
    _warm(bb, n=3, mode="heating")
    _warm(bb, n=2, mode="dhw", outdoor=None)
    bb.update("", _vals())
    assert bb.modes() == ["dhw", "heating", "unknown"]
    assert bb.total_samples() == 6
    bb.observe("heating", _vals())
    bb.reset("heating")
    assert bb.modes() == ["dhw", "unknown"] and not bb.bands("heating")
    assert "heating" not in bb._streak
    bb.reset()
    assert bb.modes() == [] and bb.total_samples() == 0


# ---------- persistence ----------

def test_round_trip():
    bb = BehaviourBaseline(alpha=0.05)
    _warm(bb, n=30)
    bb.observe("heating", _vals())
    data = bb.to_dict()
    assert data["type"] == "behaviour" and data["version"] == ML_VERSION
    back = BehaviourBaseline.from_dict(data)
    assert back._migrated_from_dim is None
    assert back.alpha == 0.05
    assert back.to_dict() == data


@pytest.mark.parametrize("payload, dim", [
    ({"dim": 12, "alpha": 0.01, "baselines": {}}, 12),         # v1 MultiBaseline
    ({"type": "behaviour", "version": 1, "dim": 6}, 6),        # other ML version
    (None, 0),
    ({"type": "behaviour"}, 0),
])
def test_from_dict_mismatch_is_flagged(payload, dim):
    bb = BehaviourBaseline.from_dict(payload)
    assert bb._migrated_from_dim == dim
    assert bb.total_samples() == 0


def test_from_dict_skips_bad_entries():
    bb = BehaviourBaseline.from_dict({
        "type": "behaviour", "version": ML_VERSION,
        "groups": {"heating": {"cop_avg": [30, 4.0, 0.01], "bogus": [1, 1, 1]},
                   "dhw": "broken"},
        "streak": {"heating": 1, "dhw": True, "x": "2"},
    })
    assert bb.modes() == ["heating"]
    assert set(bb._groups["heating"]) == {"cop_avg"}
    assert bb._streak == {"heating": 1}


def test_summary_shows_minutes_and_bands():
    bb = BehaviourBaseline()
    for _ in range(30):
        bb.update("heating", _vals(dur_min=40.0), 5.0)
    s = bb.summary()
    h = s["modes"]["heating"]
    assert s["version"] == ML_VERSION
    assert h["samples"] == 30 and h["bands"] == {4: 30} and h["streak"] == 0
    assert h["dims"]["duration_s"]["mean"] == pytest.approx(40.0, abs=0.01)
    assert h["dims"]["cop_avg"]["std"] == 0.15     # the floor


# ---------- evaluate_behaviour ----------

def test_evaluate_not_ready():
    res = evaluate_behaviour(BehaviourBaseline(), "heating", _vals(), 5.0)
    assert res.is_anomaly is False
    assert res.details["reason"] == "not_ready"


def test_evaluate_alert_maps_to_feature_index():
    bb = BehaviourBaseline()
    _warm(bb, n=60)
    bad = _vals(cop=2.0)
    first = evaluate_behaviour(bb, "heating", bad, 5.0, learn=False)
    assert first.is_anomaly is True                # z >> 6 on COP
    assert first.top_dim == FEATURE_NAMES.index("cop_avg")
    assert first.top_dim_value == 2.0
    assert first.details["ml_version"] == 2
    assert first.details["top_dim_name"] == "cop_avg"
    assert first.details["group"] == "heating|4"
    assert first.severity == "critical"


def test_evaluate_watch_is_not_an_alert():
    bb = BehaviourBaseline()
    _warm(bb, n=60)
    res = evaluate_behaviour(bb, "heating", _vals(dt=5.0 + 1.0), 5.0,
                             options={"anomaly_watch_z": 1.0})
    assert res.is_anomaly is False
    assert res.severity in ("watch", "warn")


# ---------- k-means v2 ----------

def _cyc(mode, dur_min, **kw):
    rec = {"mode": mode, "duration_s": dur_min * 60, "dT_avg": 5.0, "rps_avg": 40.0,
           "cop_avg": 4.0, "thermal_kw_avg": 6.0, "is_transient": 0}
    rec.update(kw)
    return rec


def _train_set():
    rng = random.Random(3)
    rows = [_cyc("heating", rng.uniform(8, 14)) for _ in range(20)]
    rows += [_cyc("heating", rng.uniform(45, 60)) for _ in range(40)]
    rows += [_cyc("heating", rng.uniform(200, 240)) for _ in range(20)]
    rows += [_cyc("dhw", rng.uniform(30, 40), lwt_avg=50.0) for _ in range(15)]
    rows += [_cyc("heating", 1, is_transient=1) for _ in range(30)]
    rows += [_cyc("heating", 9, boiler_contribution_samples=3) for _ in range(30)]
    rows += [_cyc("cooling", 30) for _ in range(5)]          # too few for a model
    rows += [{"mode": "heating", "duration_s": None, "is_transient": 0}]
    return rows


def test_kmeans_v2_per_mode_absolute_labels():
    st = kmeans_v2.train(_train_set(), short_run_min=20)
    assert st["version"] == kmeans_v2.KMEANS_VERSION
    assert set(st["modes"]) == {"dhw", "heating"}
    heat = st["modes"]["heating"]
    assert heat["n"] == 80                     # transients / co-fire / no-duration out
    assert sorted(heat["labels"]) == ["long_cycle", "normal", "pendulum"]
    assert "lwt_avg" not in heat["dims"]       # never measured for heating
    assert "lwt_avg" in st["modes"]["dhw"]["dims"]
    assert st["modes"]["dhw"]["labels"] == ["normal"] * len(st["modes"]["dhw"]["labels"])
    lbl = kmeans_v2.labels(st)
    assert lbl[kmeans_v2.assign(st, "heating", behaviour_values(_cyc("heating", 10)))] == "pendulum"
    assert lbl[kmeans_v2.assign(st, "heating", behaviour_values(_cyc("heating", 230)))] == "long_cycle"
    dhw_id = kmeans_v2.assign(st, "dhw", behaviour_values(_cyc("dhw", 35)))
    assert dhw_id is not None and dhw_id >= st["modes"]["dhw"]["id_base"]
    assert len(kmeans_v2.centroids(st)) == st["k"]


def test_kmeans_v2_assign_none_paths():
    st = kmeans_v2.train(_train_set())
    vals = behaviour_values(_cyc("heating", 50))
    assert kmeans_v2.assign(None, "heating", vals) is None
    assert kmeans_v2.assign(st, "cooling", vals) is None
    assert kmeans_v2.assign(st, None, vals) is None
    assert kmeans_v2.assign(st, "heating", {"duration_s": None}) is None
    broken = {"modes": {"heating": {"dims": ["duration_s"], "mu": [1.0], "sd": [1.0],
                                    "centroids": [], "id_base": 0}}}
    assert kmeans_v2.assign(broken, "heating", vals) is None
    assert kmeans_v2.assign({"modes": {"heating": {"dims": []}}}, "heating", vals) is None


def test_kmeans_v2_labels_centroids_robust():
    assert kmeans_v2.labels(None) == {}
    assert kmeans_v2.centroids(None) == []
    st = {"modes": {"a": {"id_base": 10, "labels": ["normal"], "centroids": [[1.0]]},
                    "b": {"labels": ["x"]},
                    "c": {"id_base": 0, "centroids": [[0.0]], "labels": ["pendulum"]}}}
    assert kmeans_v2.labels(st) == {10: "normal", 0: "pendulum"}
    assert kmeans_v2.centroids(st) == [[0.0], [1.0]]


def test_kmeans_v2_too_few():
    st = kmeans_v2.train([_cyc("heating", 40)] * 5)
    assert st["modes"] == {} and st["n"] == 0 and st["k"] == 0


# ---------- adaptive thresholds ----------

def test_adaptive_short_run_is_p5():
    at = AdaptiveThresholds(min_samples=20)
    for m in range(1, 101):        # 1..100 minutes
        at.observe_cycle("heating", m * 60.0)
    assert at.learn_short_run_min("heating") == 6     # p5 of 1..100 = 5.95


def test_adaptive_history_is_bounded():
    at = AdaptiveThresholds()
    for i in range(MAX_SAMPLES_PER_MODE + 50):
        at.observe_cycle("heating", 600.0 + i, 300.0)
    for i in range(MAX_DAYS + 5):
        at.observe_day(i)
    d = at.to_dict()
    assert len(d["run_min"]["heating"]) == MAX_SAMPLES_PER_MODE
    assert len(d["off_min"]["heating"]) == MAX_SAMPLES_PER_MODE
    assert len(d["daily_cycles"]) == MAX_DAYS
    assert d["run_min"]["heating"][-1] == pytest.approx((600.0 + MAX_SAMPLES_PER_MODE + 49) / 60)
    big = {"run_min": {"h": [1.0] * (MAX_SAMPLES_PER_MODE + 9)},
           "off_min": {"h": [1.0] * (MAX_SAMPLES_PER_MODE + 9)},
           "daily_cycles": list(range(MAX_DAYS + 9))}
    back = AdaptiveThresholds.from_dict(big).to_dict()
    assert len(back["run_min"]["h"]) == MAX_SAMPLES_PER_MODE
    assert len(back["off_min"]["h"]) == MAX_SAMPLES_PER_MODE
    assert len(back["daily_cycles"]) == MAX_DAYS


def test_adaptive_replace_run_samples():
    at = AdaptiveThresholds()
    at.observe_cycle("dhw", 60.0)
    kept = at.replace_run_samples({"heating": [600.0, -1, True, "x", 1200.0], "dhw": [0]})
    assert kept == 2
    assert at.to_dict()["run_min"] == {"heating": [10.0, 20.0]}
