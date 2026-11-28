"""#508 period comparison: deltas, degree-day normalisation, weather-matched
COP, verdicts, trends and the reference period."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine import report_compare as rc


def _period(**kw):
    data = {"el_kwh": 300.0, "th_kwh": 1200.0, "cop": 4.0, "cop_el_kwh": 300.0, "runtime_h": 300.0,
            "cycles": 150, "runs": 120, "run_mean_min": 150.0, "quality_mean": 80.0,
            "outdoor_mean": 5.0, "buh_min": 60.0, "alerts": {"a": 2, "b": 1}, "ml_anomalies": 1,
            "degree_days": {"nl18": 400.0, "be1515": 300.0}, "coverage_days": 1.0,
            "cop_bands": {"2": [600.0, 150.0, 10], "4": [600.0, 150.0, 10]}}
    data.update(kw)
    return data


def test_derived_values():
    d = rc.derived(_period(), "nl18")
    assert d["dd"] == 400.0 and d["el_per_dd"] == 0.75 and d["th_per_dd"] == 3.0
    assert d["starts_per_h"] == 0.5 and d["buh_share_pct"] == 0.3 and d["alerts_total"] == 3
    assert rc.derived(_period(), "be1515")["el_per_dd"] == 1.0
    mild = rc.derived(_period(degree_days={"nl18": 5.0}, runtime_h=0), "nl18")
    assert mild["el_per_dd"] is None and mild["starts_per_h"] is None and mild["buh_share_pct"] is None
    assert rc.derived({}, "nl18")["dd"] is None


def test_compare_same_period_is_good():
    out = rc.compare(_period(), _period(), "nl18")
    assert out["available"] and not out["partial"]
    assert out["metrics"]["cop"] == {"cur": 4.0, "ref": 4.0, "delta": 0.0, "delta_pct": 0.0}
    assert out["metrics"]["cop_matched"]["bands"] == ["2", "4"]
    assert out["verdicts"]["overall"] == "good"
    assert set(out["verdicts"]) == {"cop", "el_per_dd", "quality_mean", "run_mean_min",
                                    "starts_per_h", "buh_share_pct", "overall"}


def test_colder_month_is_not_worse():
    """More energy and a lower plain COP in a colder month, same COP per band."""
    cold = _period(el_kwh=450.0, cop_el_kwh=450.0, th_kwh=1620.0, cop=3.6,
                   degree_days={"nl18": 600.0},
                   cop_bands={"-2": [420.0, 150.0, 10], "2": [600.0, 150.0, 5], "4": [600.0, 150.0, 5]})
    out = rc.compare(cold, _period(), "nl18")
    assert out["metrics"]["cop"]["delta_pct"] == -10.0
    assert out["metrics"]["cop_matched"]["delta_pct"] == 0.0     # same COP where both had weather
    assert out["metrics"]["el_per_dd"]["delta_pct"] == 0.0       # 0.75 kWh per degree day
    assert out["verdicts"]["cop"] == "good"
    assert out["verdicts"]["el_per_dd"] == "good"


def test_worse_heat_pump_grades_watch_and_act():
    worse = _period(cop_bands={"2": [510.0, 150.0, 10], "4": [510.0, 150.0, 10]},
                    cop_el_kwh=360.0, quality_mean=72.0, run_mean_min=100.0, cycles=300, buh_min=600.0)
    v = rc.compare(worse, _period(), "nl18")["verdicts"]
    assert v["cop"] == "act"                 # -15 % at matching weather
    assert v["el_per_dd"] == "act"           # +20 % per degree day
    assert v["quality_mean"] == "watch"      # -8 points
    assert v["run_mean_min"] == "act"        # -33 %
    assert v["starts_per_h"] == "act"        # doubled
    assert v["buh_share_pct"] == "watch"     # 3.3 % vs 0.3 %: +3 points
    assert v["overall"] == "act"
    slightly = _period(cop_bands={"2": [570.0, 150.0, 10], "4": [570.0, 150.0, 10]})
    assert rc.compare(slightly, _period(), "nl18")["verdicts"]["cop"] == "watch"   # -5 %


def test_plain_cop_used_without_shared_bands():
    cur = _period(cop=3.0, cop_bands={"10": [30.0, 10.0, 1]})
    out = rc.compare(cur, _period(), "nl18")
    assert "cop_matched" not in out["metrics"]
    assert out["verdicts"]["cop"] == "act"
    assert rc.matched_cop({"2": [1, 0, 1], "4": [1, 0, 1]}, {"2": [1, 1, 1], "4": [1, 1, 1]}) is None


def test_partial_period_is_incomplete():
    out = rc.compare(_period(coverage_days=0.5), _period(), "nl18")
    assert out["partial"] and set(out["verdicts"].values()) == {"incomplete"}
    assert rc.is_partial(None) and rc.is_partial({"coverage_days": None})


def test_compare_without_reference_or_metrics():
    assert rc.compare(_period(), None, "nl18") == {"metrics": {}, "verdicts": {}, "partial": True,
                                                    "available": False}
    out = rc.compare({"coverage_days": 1.0}, {"coverage_days": 1.0}, "nl18")
    assert out["verdicts"] == {"overall": "incomplete"}
    assert out["metrics"]["cop"] == {"cur": None, "ref": None, "delta": None, "delta_pct": None}
    zero_ref = rc.compare(_period(), _period(cop=0.0), "nl18")["metrics"]["cop"]
    assert zero_ref["delta"] == 4.0 and zero_ref["delta_pct"] is None


def test_trend():
    up = rc.trend([3.0, 3.2, None, 3.6, 3.8])
    assert up["direction"] == "up" and up["n"] == 4 and up["slope"] == pytest.approx(0.2, abs=1e-3)
    assert rc.trend([4.0, 4.0, 4.0])["direction"] == "flat"
    assert rc.trend([5.0, 4.0, 3.0])["direction"] == "down"
    assert rc.trend([0.0, 0.0, 0.0])["slope_pct"] is None
    assert rc.trend([1.0, None, 2.0]) is None


@pytest.mark.parametrize(("ptype", "key", "prev", "last_year"), [
    ("week", "2026-W01", "2025-W52", "2025-W01"),
    ("week", "2027-W10", "2027-W09", "2026-W10"),
    ("week", "2026-W53", "2026-W52", "2025-W52"),     # 2025 has 52 weeks
    ("month", "2026-01", "2025-12", "2025-01"),
    ("year", "2026", "2025", "2025"),
    ("season", "2026/27", "2025/26", "2025/26"),
])
def test_reference_keys(ptype, key, prev, last_year):
    assert rc.reference_key(ptype, key, "previous") == prev
    assert rc.reference_key(ptype, key, "last_year") == last_year
    assert rc.reference_key(ptype, key, "none") is None


def test_last_year_key_unknown_type():
    with pytest.raises(ValueError):
        rc.last_year_key("decade", "2020")
