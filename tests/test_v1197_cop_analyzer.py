"""v1.19.7 target: engine/cop_analyzer.py.

Real API verified via inspect:
  analyze_stooklijn(samples: list[CopSample], ...) -> StooklijnAdvies
  bucket_for_outdoor(temp: float | None) -> str
  CopSample is a dataclass — must be constructed, not dicts.
"""
import time
import pytest
from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample, StooklijnAdvies, analyze_stooklijn, bucket_for_outdoor,
)


def _sample(*, cop=3.5, lwt=35.0, outdoor=5.0, ts=None, mode="heating"):
    return CopSample(
        cop=cop, lwt=lwt, outdoor=outdoor, mode=mode,
        ts=ts if ts is not None else time.time(),
        power_stable=True, data_quality="good",
    )


def test_empty_returns_stooklijn_advies():
    r = analyze_stooklijn([])
    assert isinstance(r, StooklijnAdvies)


def test_cooling_only_returns_no_data():
    """All cooling: filtered out (heating/unknown only) -> state='no_data'."""
    samples = [_sample(mode="cooling") for _ in range(10)]
    r = analyze_stooklijn(samples)
    assert r.state == "no_data"
    assert r.reason == "no_recent_heating"


def test_negative_outdoor_heating():
    """-15°C: no crash, returns advies."""
    samples = [_sample(outdoor=-15.0, lwt=42.0, cop=2.2) for _ in range(20)]
    r = analyze_stooklijn(samples, now=time.time())
    assert isinstance(r, StooklijnAdvies)


def test_insufficient_bucket_samples():
    """<5 samples in bucket: early return, still StooklijnAdvies."""
    samples = [_sample(outdoor=5.0) for _ in range(3)]
    r = analyze_stooklijn(samples, now=time.time())
    assert isinstance(r, StooklijnAdvies)


def test_multi_bucket_input():
    """Outdoor from -15 to +15: multi-bucket aggregation works."""
    samples = []
    for outdoor in (-15.0, -5.0, 5.0, 15.0):
        for _ in range(15):
            samples.append(_sample(
                outdoor=outdoor, lwt=35.0 + abs(outdoor) * 0.3,
                cop=4.0 - abs(outdoor) * 0.05,
            ))
    r = analyze_stooklijn(samples, now=time.time())
    assert isinstance(r, StooklijnAdvies)


def test_bucket_for_outdoor_various():
    for temp in (-20.0, -10.0, 0.0, 5.0, 15.0):
        b = bucket_for_outdoor(temp)
        assert isinstance(b, str)


def test_bucket_for_outdoor_none():
    assert isinstance(bucket_for_outdoor(None), str)


def test_zero_and_negative_cop_robust():
    """Invalid COP values: no crash."""
    samples = [
        _sample(cop=0.0), _sample(cop=-1.0), _sample(cop=3.5),
    ]
    r = analyze_stooklijn(samples, now=time.time())
    assert isinstance(r, StooklijnAdvies)
