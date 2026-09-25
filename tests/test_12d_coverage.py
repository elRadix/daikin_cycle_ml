"""Tests for 12d: coverage boost + edge case coverage."""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    AdaptiveThresholds,
)
from custom_components.daikin_cycle_ml.ml.clustering import (
    classify_clusters,
    nearest_centroid,
)
from custom_components.daikin_cycle_ml.const import (
    ALERT_TYPE_EMOJI,
    MODEL_STATE_ADAPTIVE,
    NOTIF_ID_STATUS,
    SEVERITY_EMOJI,
)

ROOT = Path(__file__).resolve().parent.parent


# ---------- adaptive thresholds edge cases ----------

def test_adaptive_reset_mode():
    at = AdaptiveThresholds(min_samples=2)
    at.observe_cycle("heating", 900.0, 600.0)
    at.reset("heating")
    assert at.sample_count("heating")["run"] == 0


def test_adaptive_reset_all():
    at = AdaptiveThresholds()
    at.observe_cycle("heating", 900.0, 600.0)
    at.observe_day(10)
    at.reset()
    assert at.total_samples() == 0


def test_adaptive_observe_day_invalid():
    at = AdaptiveThresholds()
    assert at.observe_day(None) is False
    assert at.observe_day(-1) is False
    assert at.observe_day("garbage") is False


def test_adaptive_from_dict_missing_keys():
    at = AdaptiveThresholds.from_dict({})
    assert at.total_samples() == 0
    assert at.modes() == []


def test_adaptive_to_dict_roundtrip():
    at = AdaptiveThresholds(min_samples=3)
    at.observe_cycle("heating", 900.0, 600.0)
    at.observe_day(8)
    d = at.to_dict()
    r = AdaptiveThresholds.from_dict(d)
    assert r.sample_count("heating")["run"] == 1
    assert r.min_samples == 3


def test_adaptive_observe_cycle_invalid_values():
    at = AdaptiveThresholds(min_samples=2)
    assert at.observe_cycle("heating", None, None) is False
    assert at.observe_cycle("heating", -5.0, None) is False


# ---------- clustering edge cases ----------

def test_nearest_centroid_all_dim_mismatch():
    assert nearest_centroid([1.0], [[1.0, 2.0]]) is None


def test_classify_two_clusters():
    c = [[100.0, 5.0], [2000.0, 10.0]]
    labels = classify_clusters(c)
    assert labels[0] == "pendulum"
    assert labels[1] == "dhw_like"


def test_classify_three_uniform():
    c = [[1000.0, 5.0], [1100.0, 6.0], [900.0, 4.0]]
    labels = classify_clusters(c)
    assert len(labels) == 3
    assert labels[2] == "pendulum"


def test_classify_three_typical():
    c = [
        [300.0, 3.0, 2.0, 40.0, 25.0, 2.0, 0.0, 0.0],
        [1800.0, 9.0, 7.0, 65.0, 55.0, 2.0, 1.0, 0.0],
        [1500.0, 5.0, 4.0, 45.0, 32.0, 2.0, 0.0, 0.0],
    ]
    labels = classify_clusters(c)
    assert labels[0] == "pendulum"
    assert labels[1] == "dhw_like"
    assert labels[2] == "normal"


def test_nearest_centroid_simple():
    c = [[0.0, 0.0], [10.0, 10.0], [20.0, 20.0]]
    assert nearest_centroid([1.0, 1.0], c) == 0
    assert nearest_centroid([11.0, 11.0], c) == 1
    assert nearest_centroid([19.0, 21.0], c) == 2


def test_classify_empty():
    assert classify_clusters([]) == {}


def test_classify_single():
    assert classify_clusters([[10.0, 5.0]]) == {0: "normal"}


# ---------- notification engine ----------

def test_evaluate_alerts_no_trigger():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        evaluate_alerts,
    )
    assert evaluate_alerts({}, {}, now=1e9) == []


def test_build_status_message_minimal():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_status_message,
    )
    msg = build_status_message({})
    assert "unknown" in msg
    assert "idle" in msg


def test_build_status_message_no_emoji():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_status_message,
    )
    msg = build_status_message({"mode": "dhw"}, emoji_enabled=False)
    assert not msg.startswith(SEVERITY_EMOJI["status"])
    assert "dhw" in msg


def test_build_status_message_full():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_status_message,
    )
    snap = {
        "mode": "heating",
        "state": "running",
        "cycles_today": 12,
        "target_cpd": 8,
        "last_cycle_ago_min": 35,
        "quality_last": 72,
        "anomaly_severity": "normal",
        "baseline_samples": 142,
        "baseline_modes": ["heating", "dhw"],
        "top_advice": "extend off-time",
    }
    msg = build_status_message(snap)
    assert "heating" in msg
    assert "12" in msg
    assert "35" in msg
    assert "extend off-time" in msg


# ---------- constants / wiring sanity ----------

def test_severity_emoji_map_complete():
    for k in ("critical", "warning", "watch", "info", "ok", "status"):
        assert k in SEVERITY_EMOJI
        assert SEVERITY_EMOJI[k]


def test_alert_type_emoji_covers_core():
    for k in ("pendulum", "short_run", "short_off", "ml_anomaly", "setpoint_osc"):
        assert k in ALERT_TYPE_EMOJI


def test_model_state_constants():
    assert MODEL_STATE_ADAPTIVE == "adaptive_thresholds"
    assert NOTIF_ID_STATUS == "daikin_cycle_ml_status"


def test_db_tables_tuple():
    from custom_components.daikin_cycle_ml.diagnostics import DB_TABLES
    for t in ("cycles", "features", "model_state", "alerts", "daily_summary"):
        assert t in DB_TABLES


def test_adaptive_sensor_defs_shape():
    from custom_components.daikin_cycle_ml import sensor as smod
    for d in smod.ADAPTIVE_SENSOR_DEFS:
        assert "key" in d
        assert "name" in d
        assert callable(d.get("value_fn"))


def test_sensor_defs_count_grew():
    from custom_components.daikin_cycle_ml import sensor as smod
    assert len(smod.SENSOR_DEFS) >= 29


def test_translations_have_adaptive_sensor_keys():
    p = ROOT / "translations" / "en.json"
    data = json.loads(p.read_text())
    keys = data["entity"]["sensor"]
    for k in (
        "learned_short_run_min",
        "learned_good_off_min",
        "learned_target_cycles_per_day",
    ):
        assert k in keys


def test_translations_have_cluster_binary_keys():
    p = ROOT / "translations" / "en.json"
    data = json.loads(p.read_text())
    keys = data["entity"]["binary_sensor"]
    for k in ("cluster_pendulum", "cluster_normal", "cluster_dhw_like"):
        assert k in keys

