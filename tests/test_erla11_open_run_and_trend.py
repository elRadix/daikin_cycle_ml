"""Replay of a diagnostics file (ERLA11DAV3, v1.29.1, corpus).

1. One heating run was open for 16 h across midnight. runtime_compressor_today
   said 35720 s (9.9 h) while its per-mode split said heating_s 0: the state
   adds the open run, the split did not.
2. cop_trend_30d said -11.6 % "at the same weather" from a fit with
   r2 0.03: the fit explained almost nothing, predicted the baseline mean
   whatever the weather, and the colder recent days read as degradation.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import custom_components.daikin_cycle_ml.sensor as sensor_mod
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.engine.cop_degradation import TREND_MIN_R2, analyze_trend

CORPUS = Path(__file__).parent / "fixtures/diagnostics/erla11dav3_1_29_1_855f04b147_202611220955.json"


def _corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def test_open_run_across_midnight_counts_in_the_mode_split(monkeypatch):
    d = _corpus()
    reported = d["entities"]["sensor:runtime_compressor_today"]
    assert reported["state"] == "35720" and reported["attributes"]["heating_s"] == 0   # v1.29.1
    now = d["coordinator"]["last_sample_ts"]
    monkeypatch.setattr(sensor_mod, "_now", lambda: now)
    s = DataSnapshot()
    s.state, s.mode, s.cycle_start_ts = "running", "heating", d["coordinator"]["cycle_start_ts"]
    c = MagicMock()
    c.last_attrs = {}
    c.store.cycles_intersecting.return_value = []
    total = sensor_mod._value_runtime_compressor_today_s(s, c)
    attrs = sensor_mod._attrs_runtime_compressor_today_s(s, c)
    assert total > 0 and attrs["heating_s"] == total and attrs["dhw_s"] == 0
    assert attrs["cycle_count"] == 0 and attrs["avg_cycle_s"] is None    # the run started yesterday


def _rows(points, n=20):
    return [{"ts_hour": i, "outdoor_mean": o, "cop_mean": c, "n_samples": n, "lwt_mean": 30.0}
            for i, (o, c) in enumerate(points)]


def test_trend_needs_a_fit_that_explains_the_weather():
    d = _corpus()
    reported = d["entities"]["sensor:cop_trend_30d"]["attributes"]
    assert reported["fit_r2"] < TREND_MIN_R2 and reported["valid"] is True   # what v1.29.1 reported
    # baseline over 15 K of outdoor whose COP does not follow the weather,
    # recent colder days below its mean (the reported 5.18 vs 4.58)
    base = _rows([(float(o), 5.18 + (0.8 if o % 2 else -0.8)) for o in range(16)])
    recent = _rows([(2.0, 4.58)] * 10, n=30)
    r = analyze_trend(base, recent, set())
    assert r["fit_r2"] < TREND_MIN_R2
    assert r["valid"] is False and r["trend_30d"] is None and r["severity"] == "none"
    assert r["trend_30d_raw"] is not None                                    # still shown raw
