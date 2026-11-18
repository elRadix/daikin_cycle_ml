"""#193: docs/cycle-thresholds.json is the canonical copy of the defaults.

Fails CI when the published JSON and the code drift apart.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml import const
from custom_components.daikin_cycle_ml.engine import physics, quality_scorer

DOC = json.loads(
    (Path(__file__).resolve().parent.parent / "docs/cycle-thresholds.json")
    .read_text(encoding="utf-8")
)


def test_schema_version():
    assert DOC["schema_version"] == 1


@pytest.mark.parametrize(
    "section,key,code",
    [
        ("cycle_detection", "compressor_running_rps", const.DEFAULT_COMPRESSOR_RPS_THRESHOLD),
        ("cycle_detection", "transient_max_duration_s", const.TRANSIENT_MAX_DURATION_S),
        ("cycle_detection", "fallback_power_threshold_w", const.DEFAULT_FALLBACK_POWER_THRESHOLD_W),
        ("pendulum", "short_run_min", const.DEFAULT_SHORT_RUN_MIN),
        ("pendulum", "short_off_min", const.DEFAULT_SHORT_OFF_MIN),
        ("pendulum", "cycles_per_hour", const.DEFAULT_PENDULUM_CPH),
        ("pendulum", "cycles_per_day", const.DEFAULT_PENDULUM_CPD),
        ("quality", "good_run_min", const.DEFAULT_GOOD_RUN_MIN),
        ("quality", "good_off_min", const.DEFAULT_GOOD_OFF_MIN),
        ("quality", "good_dt_k", const.DEFAULT_GOOD_DT_K),
        ("sanity_gates", "max_cop", const.MAX_COP),
        ("sanity_gates", "max_thermal_kw", const.MAX_THERMAL_KW),
        ("sanity_gates", "cop_floor_heating_dhw", physics.COP_FLOOR),
        ("carnot", "efficiency_factor", physics.CARNOT_EFFICIENCY_FACTOR),
        ("carnot", "accept_margin", physics.ACCEPT_MARGIN),
        ("carnot", "reject_multiplier", physics.REJECT_MULTIPLIER),
    ],
)
def test_json_matches_code(section, key, code):
    assert DOC[section][key] == code, f"{section}.{key}: json != code"


def test_scorer_defaults_match_const():
    # quality_scorer keeps its own copy of the quality defaults
    assert quality_scorer.DEFAULT_GOOD_RUN_MIN == const.DEFAULT_GOOD_RUN_MIN
    assert quality_scorer.DEFAULT_GOOD_OFF_MIN == const.DEFAULT_GOOD_OFF_MIN


def test_carnot_stays_065():
    # internal decision 2026-11-18 (#193): keep the Daikin-confirmed 0.65
    assert DOC["carnot"]["efficiency_factor"] == 0.65


def test_carnot_bands_behave_as_documented():
    # A7/W35: Carnot COP = 308.15 / 28 = 11.0 (classify_cop_sample(mode, lwt, outdoor, cop))
    accept_hi = 11.0 * 0.65 * 1.05
    assert physics.classify_cop_sample("heating", 35.0, 7.0, accept_hi - 0.1) == "accept"
    assert physics.classify_cop_sample("heating", 35.0, 7.0, accept_hi + 0.3) == "flag"
    assert physics.classify_cop_sample("heating", 35.0, 7.0, 11.0 * 1.5 + 1) == "reject"
