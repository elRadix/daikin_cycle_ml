"""Batch 52b2: recency filter + DHW-aware geen_data."""
import time

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    STOOKLIJN_RECENT_WINDOW_S,
    CopSample,
    StooklijnAdvies,
    analyze_stooklijn,
)


def _mk(cop, lwt, out, mode, ts=0.0, n=6):
    return [
        CopSample(cop=cop, lwt=lwt, outdoor=out, mode=mode, ts=ts,
                  data_quality="Good")
        for _ in range(n)
    ]


def test_stooklijn_advies_has_reason_field():
    a = StooklijnAdvies()
    assert a.reason == ""


def test_cop_sample_has_ts_field():
    s = CopSample(cop=3.0)
    assert s.ts == 0.0


def test_all_dhw_samples_geen_data():
    dhw = _mk(1.0, 55.0, 5.0, "dhw")
    a = analyze_stooklijn(dhw)
    assert a.state == "no_data"
    assert a.reason == "no_recent_heating"
    assert a.huidige_lwt is None
    assert a.optimale_lwt is None
    assert a.samples == 0


def test_dhw_plus_cooling_only_geen_data():
    dhw = _mk(1.0, 55.0, 5.0, "dhw", n=3)
    cool = _mk(3.0, 10.0, 30.0, "cooling", n=3)
    a = analyze_stooklijn(dhw + cool)
    assert a.state == "no_data"


def test_empty_input_returns_default():
    a = analyze_stooklijn([])
    # Legacy behavior: empty input -> default StooklijnAdvies
    assert a.state == "unknown"
    assert a.reason == ""


def test_unknown_mode_still_used():
    unknown = _mk(4.0, 35.0, 5.0, "unknown")
    a = analyze_stooklijn(unknown)
    assert a.state != "no_data"
    assert a.samples == 6


def test_heating_used():
    heating = _mk(4.0, 35.0, 5.0, "heating")
    a = analyze_stooklijn(heating)
    assert a.state != "no_data"
    assert a.samples == 6


def test_old_heating_outside_window_geen_data():
    old_ts = time.time() - STOOKLIJN_RECENT_WINDOW_S - 100
    old = _mk(4.0, 35.0, 5.0, "heating", ts=old_ts)
    a = analyze_stooklijn(old)
    # Samples not filtered out (mode=heating), but recency check rejects
    # all -> recent is None -> geen_data.
    assert a.state == "no_data"


def test_recent_heating_within_window_used():
    fresh_ts = time.time() - 100
    heating = _mk(4.0, 35.0, 5.0, "heating", ts=fresh_ts)
    a = analyze_stooklijn(heating)
    assert a.state != "no_data"
    assert a.reason == ""


def test_explicit_now_parameter():
    old_ts = 1000.0
    heating = _mk(4.0, 35.0, 5.0, "heating", ts=old_ts)
    a = analyze_stooklijn(heating, now=2000.0)
    assert a.state != "no_data"
    a2 = analyze_stooklijn(
        heating, now=old_ts + STOOKLIJN_RECENT_WINDOW_S + 1
    )
    assert a2.state == "no_data"
