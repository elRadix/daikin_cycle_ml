"""#508 period reports: the pure engine (periods, degree days, checks, aggregation)."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine import period_reports as pr


# ---------- periods ----------

@pytest.mark.parametrize(("ptype", "day", "key"), [
    ("week", "2026-11-23", "2026-W48"),        # Monday
    ("week", "2026-11-29", "2026-W48"),        # Sunday, same ISO week
    ("week", "2026-11-30", "2026-W49"),
    ("week", "2027-01-01", "2026-W53"),        # ISO year differs from calendar year
    ("week", "2024-12-30", "2025-W01"),
    ("month", "2026-02-28", "2026-02"),
    ("year", "2026-12-31", "2026"),
    ("season", "2026-10-01", "2026/27"),
    ("season", "2026-09-30", "2025/26"),
    ("season", "2099-12-01", "2099/00"),
])
def test_period_key(ptype, day, key):
    assert pr.period_key(ptype, day) == key


@pytest.mark.parametrize(("ptype", "key", "bounds"), [
    ("week", "2026-W53", ("2026-12-28", "2027-01-03")),
    ("week", "2025-W01", ("2024-12-30", "2025-01-05")),
    ("month", "2024-02", ("2024-02-01", "2024-02-29")),
    ("month", "2026-12", ("2026-12-01", "2026-12-31")),
    ("year", "2026", ("2026-01-01", "2026-12-31")),
    ("season", "2026/27", ("2026-10-01", "2027-09-30")),
])
def test_period_bounds(ptype, key, bounds):
    assert pr.period_bounds(ptype, key) == bounds


def test_season_start_month_option():
    assert pr.period_key("season", "2026-09-15", season_start_month=9) == "2026/27"
    assert pr.period_bounds("season", "2026/27", 9) == ("2026-09-01", "2027-08-31")


def test_unknown_period_type():
    with pytest.raises(ValueError):
        pr.period_key("decade", "2026-01-01")
    with pytest.raises(ValueError):
        pr.period_bounds("decade", "2026")


def test_periods_of_day_and_range():
    assert pr.periods_of_day("2026-11-28") == [
        ("week", "2026-W48"), ("month", "2026-11"), ("year", "2026"), ("season", "2026/27")]
    assert pr.day_range("2026-02-27", "2026-03-01") == ["2026-02-27", "2026-02-28", "2026-03-01"]
    assert pr.day_range("2026-03-02", "2026-03-01") == []


def test_default_scheme_per_country():
    assert pr.default_scheme("BE") == "be1515"
    assert pr.default_scheme("fr") == "fr18"
    assert pr.default_scheme("NL") == "nl18"
    assert pr.default_scheme("DE") == "nl18"
    assert pr.default_scheme(None) == "nl18"
    assert set(pr.COUNTRY_SCHEME.values()) <= set(pr.DD_SCHEMES)


# ---------- degree days ----------

def test_degree_days_all_schemes():
    temps = {
        "2026-01-13": {"mean": 4.0},
        "2026-01-14": {"mean": 2.0},
        "2026-01-15": {"mean": 3.0, "min": -1.0, "max": 9.0},
    }
    dd = pr.degree_days("2026-01-15", temps)
    assert set(dd) == set(pr.DD_SCHEMES)
    assert dd["nl18"] == 15.0
    assert dd["nl18w"] == 16.5                       # January x1.1
    teq = 0.6 * 3.0 + 0.3 * 2.0 + 0.1 * 4.0          # 2.8
    assert dd["be1515"] == round(15.0 - teq, 2)
    assert dd["be165"] == round(16.5 - teq, 2)
    assert dd["fr18"] == 14.0                         # (Tmin + Tmax) / 2 = 4
    assert dd["fr17"] == 13.0
    assert dd["fr15"] == 11.0
    assert dd["cdd18"] == 0.0


def test_degree_days_fallbacks_and_summer():
    # No previous days: BE Teq uses the day itself; no min/max: FR uses the mean.
    dd = pr.degree_days("2026-07-01", {"2026-07-01": {"mean": 22.0}})
    assert dd["nl18"] == 0.0 and dd["nl18w"] == 0.0
    assert dd["be1515"] == 0.0 and dd["fr18"] == 0.0
    assert dd["cdd18"] == 4.0
    dd = pr.degree_days("2026-04-01", {"2026-04-01": {"mean": 8.0}})
    assert dd["nl18w"] == 8.0                         # April x0.8
    dd = pr.degree_days("2026-03-01", {"2026-03-01": {"mean": 8.0}})
    assert dd["nl18w"] == 10.0                        # March x1.0


def test_degree_days_without_temperature():
    assert pr.degree_days("2026-01-01", {}) is None
    assert pr.degree_days("2026-01-01", {"2026-01-01": {"mean": float("nan")}}) is None
    assert pr.degree_days("2026-01-01", {"2026-01-01": {"mean": True}}) is None


# ---------- one mode-day ----------

def _src(**kw):
    src = {
        "daily_summary": {"cycles": 4, "runs": 2, "total_duration_s": 7200, "duration_min": 1800,
                          "duration_max": 5400, "quality_sum": 320, "dt_max_sum": 20, "rps_sum": 160,
                          "buh_count": 1, "defrost_count": 2, "transient_count": 0},
        "el_kwh": 2.0, "th_kwh": 8.0,
        "hourly": {"lwt_mean": 32.0, "flow_mean": 15.0, "outdoor_mean": 5.0},
        "samples": {"n": 24, "buh_n": 1, "r4t_mean": 28.0, "dt_mean": 4.0,
                    "heat_kwh": 8.0, "power_kwh": 2.0},
    }
    src.update(kw)
    return src


def test_build_mode_row():
    row = pr.build_mode_row(_src(), sample_interval_s=300.0)
    assert row["cop"] == 4.0
    assert row["runtime_s"] == 7200 and row["run_mean_min"] == 60.0
    assert row["run_max_min"] == 90.0 and row["run_min_min"] == 30.0
    assert row["quality_mean"] == 80.0 and row["rps_mean"] == 40.0 and row["dt_max_mean"] == 5.0
    assert row["lwt_mean"] == 32.0 and row["return_mean"] == 28.0 and row["dt_mean"] == 4.0
    assert row["sample_s"] == 7200 and row["buh_samples"] == 1
    assert pr.check_mode_row(row, 86400) == []


def test_build_mode_row_empty_source():
    row = pr.build_mode_row({}, sample_interval_s=300.0)
    assert row["cop"] is None and row["runtime_s"] == 0 and row["run_mean_min"] is None
    assert row["lwt_mean"] is None and row["quality_mean"] is None
    assert pr.check_mode_row(row, 86400) == []


def test_check_no_energy_and_low_cop():
    row = pr.build_mode_row(_src(el_kwh=0.0, th_kwh=0.0), sample_interval_s=300.0)
    assert pr.check_mode_row(row, 86400) == ["no_energy"]
    row = pr.build_mode_row(_src(el_kwh=2.0, th_kwh=1.5, samples={}), sample_interval_s=300.0)
    assert pr.check_mode_row(row, 86400) == ["cop_out_of_range"]


def test_check_cop_above_physics():
    # 5 °C outdoor, 32 °C water: Carnot 10.4 x 0.65 x 1.05 = 7.1
    row = pr.build_mode_row(_src(th_kwh=16.0, samples={}), sample_interval_s=300.0)
    assert row["cop"] == 8.0
    assert pr.check_mode_row(row, 86400) == ["cop_out_of_range"]
    # Without the temperatures there is no ceiling, only the floor.
    row = pr.build_mode_row(_src(th_kwh=16.0, samples={}, hourly={}), sample_interval_s=300.0)
    assert pr.check_mode_row(row, 86400) == []


def test_check_heat_and_power_mismatch():
    s = {"n": 24, "heat_kwh": 5.0, "power_kwh": 3.0, "dt_mean": 4.0}
    row = pr.build_mode_row(_src(samples=s), sample_interval_s=300.0)
    assert pr.check_mode_row(row, 86400) == ["heat_mismatch", "power_mismatch"]
    # Samples cover 50 % of the runtime: no cross-check, too little to judge.
    s = {"n": 12, "heat_kwh": 2.5, "power_kwh": 1.5}
    row = pr.build_mode_row(_src(samples=s), sample_interval_s=300.0)
    assert pr.check_mode_row(row, 86400) == []
    # 75 % coverage scaled up: 6 / 0.75 = 8 kWh matches.
    s = {"n": 18, "heat_kwh": 6.0, "power_kwh": 1.5}
    row = pr.build_mode_row(_src(samples=s), sample_interval_s=300.0)
    assert pr.check_mode_row(row, 86400) == []


def test_check_runtime_bounds():
    ds = dict(_src()["daily_summary"], total_duration_s=90000)
    row = pr.build_mode_row(_src(daily_summary=ds, samples={}), sample_interval_s=300.0)
    assert "runtime_bounds" in pr.check_mode_row(row, 86400)
    assert "runtime_bounds" not in pr.check_mode_row(row, 90000)   # 25 h DST day


def test_check_outlier():
    hist = [(4.0 + 0.1 * (i % 3), 5.0) for i in range(30)]
    assert pr.check_outlier(2.0, 5.5, hist) is True
    assert pr.check_outlier(4.1, 5.5, hist) is False
    assert pr.check_outlier(2.0, 9.0, hist) is False            # other band
    assert pr.check_outlier(2.0, 5.0, hist[:29]) is False        # too little history
    assert pr.check_outlier(None, 5.0, hist) is False
    assert pr.check_outlier(2.0, None, hist) is False
    flat = [(4.0, 5.0)] * 30                                     # MAD 0 -> floor 0.05
    assert pr.check_outlier(4.1, 5.0, flat) is False
    assert pr.check_outlier(4.3, 5.0, flat) is True


# ---------- whole day ----------

def _modes():
    heat = pr.build_mode_row(_src(), sample_interval_s=300.0)
    heat["checks"] = []
    dhw = pr.build_mode_row(_src(el_kwh=1.0, th_kwh=0.5, samples={}), sample_interval_s=300.0)
    dhw["checks"] = pr.check_mode_row(dhw, 86400)
    return {"heating": heat, "dhw": dhw}


def test_build_all_row():
    day = "2026-01-15"
    temps = {day: {"mean": 3.0, "min": -1.0, "max": 9.0, "source": "all_day"}}
    src = {"runtime_acc": {"buh_total_s": 900, "defrost_count": 3, "defrost_duration_s": 600,
                           "source_fresh_s": 43200},
           "alerts": {"ml_anomaly": 2, "short_cycling": 1}}
    modes = _modes()
    row = pr.build_all_row(day, modes, src, temps, 86400)
    assert row["el_kwh"] == 3.0 and row["th_kwh"] == 8.5
    assert row["cop"] == 4.0                     # the failing DHW day is left out
    assert row["cop_el_kwh"] == 2.0 and row["cop_th_kwh"] == 8.0
    assert row["duty_pct"] == 16.7 and row["runs"] == 4
    assert row["outdoor_mean"] == 3.0 and row["outdoor_source"] == "all_day"
    assert row["degree_days"]["nl18"] == 15.0
    assert row["buh_min"] == 15.0 and row["defrost_count"] == 3 and row["defrost_min"] == 10.0
    assert row["ml_anomalies"] == 2 and row["alerts"]["short_cycling"] == 1
    assert row["coverage"] == 0.5
    assert pr.check_all_row(row, modes) == ["cop_out_of_range", "low_coverage"]


def test_all_row_clock_and_duty_checks():
    row = pr.build_all_row("2026-01-15", {}, {}, {}, 0)
    assert row["duty_pct"] is None and row["coverage"] is None and row["degree_days"] is None
    assert pr.check_all_row(row, {}) == ["clock"]
    row = pr.build_all_row("2026-01-15", {"heating": {"runtime_s": 90000}}, {}, {}, 86400)
    assert pr.check_all_row(row, {}) == ["runtime_bounds"]
    for day_len in (82800, 86400, 90000):
        row = pr.build_all_row("2026-03-29", {}, {"runtime_acc": {"source_fresh_s": day_len}}, {}, day_len)
        assert pr.check_all_row(row, {}) == []


# ---------- periods from days ----------

def _day(day, el, th, *, checks=(), runtime=3600, cycles=2, runs=1, **extra):
    data = {"el_kwh": el, "th_kwh": th, "runtime_s": runtime, "cycles": cycles, "runs": runs,
            "quality_mean": 80.0, "lwt_mean": 30.0, "return_mean": 26.0, "dt_mean": 4.0,
            "flow_mean": 15.0, "rps_mean": 40.0}
    data.update(extra)
    return {"day": day, "data": data, "checks": list(checks)}


def test_aggregate_mode_days():
    days = [
        _day("2026-01-01", 2.0, 8.0, outdoor_mean=2.0, outdoor_min=-3.0, outdoor_max=6.0,
             degree_days={"nl18": 16.0}, buh_min=5.0, alerts={"x": 1}, ml_anomalies=1),
        _day("2026-01-02", 1.0, 5.0, runtime=7200, lwt_mean=36.0, quality_mean=50.0, cycles=6,
             outdoor_mean=4.0, outdoor_min=0.0, outdoor_max=9.0, degree_days={"nl18": 14.0}),
        _day("2026-01-03", 1.0, 0.5, checks=["cop_out_of_range"]),
        {"day": "2026-01-04", "data": {"outdoor_mean": 6.0}, "checks": ["low_coverage"]},
    ]
    agg = pr.aggregate(days, n_days_in_period=7)
    assert agg["el_kwh"] == 4.0 and agg["th_kwh"] == 13.5
    assert agg["cop"] == 4.33 and agg["cop_el_kwh"] == 3.0
    assert agg["runtime_h"] == 4.0 and agg["runs"] == 3 and agg["run_mean_min"] == 80.0
    assert agg["lwt_mean"] == 33.0                     # runtime-weighted
    assert agg["quality_mean"] == 62.0                 # cycle-weighted (2x80 + 6x50 + 2x80) / 10
    assert agg["outdoor_mean"] == 4.0                  # every recorded day, ran or not
    assert agg["outdoor_min"] == -3.0 and agg["outdoor_max"] == 9.0
    assert agg["degree_days"] == {"nl18": 30.0}
    assert agg["buh_min"] == 5.0 and agg["alerts"] == {"x": 1} and agg["ml_anomalies"] == 1
    assert agg["n_days"] == 7 and agg["n_days_recorded"] == 4
    assert agg["n_days_data"] == 3 and agg["n_days_valid"] == 2
    assert agg["coverage_days"] == 0.429
    assert agg["checks"] == {"cop_out_of_range": 1, "low_coverage": 1}


def test_aggregate_whole_day_rows_keep_valid_modes():
    # A whole-day row whose DHW failed still counts its valid heating energy.
    days = [_day("2026-01-01", 3.0, 8.5, checks=["cop_out_of_range"], cop_el_kwh=2.0, cop_th_kwh=8.0),
            _day("2026-01-02", 1.0, 4.0, cop_el_kwh=1.0, cop_th_kwh=4.0)]
    agg = pr.aggregate(days, n_days_in_period=2)
    assert agg["cop"] == 4.0 and agg["cop_el_kwh"] == 3.0
    assert agg["el_kwh"] == 4.0


def test_aggregate_empty():
    agg = pr.aggregate([], n_days_in_period=0)
    assert agg["cop"] is None and agg["run_mean_min"] is None and agg["lwt_mean"] is None
    assert agg["outdoor_mean"] is None and agg["outdoor_min"] is None
    assert agg["coverage_days"] is None and agg["checks"] == {}
