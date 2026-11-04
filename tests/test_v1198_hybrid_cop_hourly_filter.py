"""v1.19.8 #237: hybrid COP hourly sensors must exclude boiler samples."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _mk_hybrid(rows, *, mixed_cop):
    """Stub self for _maybe_refresh_cop_hourly on hybrid install.

    mixed_cop: the value the current rollup path would return (boiler-mixed).
    Used so RED-phase tests fail with clear AssertionError, not AttributeError.
    """
    c = SimpleNamespace(
        _is_hybrid_install=lambda: True,
        _cop_hourly_cache={},
        _cop_hourly_cache_ts=0.0,
        db=MagicMock(),
    )
    c.db.async_fetch_cop_samples = AsyncMock(return_value=rows)
    stats = {
        "n_hours": 10, "n_samples": 10,
        "cop_mean": mixed_cop, "cop_p10": mixed_cop * 0.7,
        "cop_p90": mixed_cop * 1.3,
        "cop_min": mixed_cop * 0.7, "cop_max": mixed_cop * 1.3,
    }
    c.db.async_cop_hourly_stats = AsyncMock(return_value=stats)
    c.db.async_cop_hourly_by_mode = AsyncMock(return_value={"heating": stats})
    c._refresh_cop_curve_recent = AsyncMock()
    return c


def _mk_non_hybrid(stats, by_mode):
    c = SimpleNamespace(
        _is_hybrid_install=lambda: False,
        _cop_hourly_cache={},
        _cop_hourly_cache_ts=0.0,
        db=MagicMock(),
    )
    c.db.async_fetch_cop_samples = AsyncMock()
    c.db.async_cop_hourly_stats = AsyncMock(return_value=stats)
    c.db.async_cop_hourly_by_mode = AsyncMock(return_value=by_mode)
    c._refresh_cop_curve_recent = AsyncMock()
    return c


async def test_hybrid_bypasses_rollup_uses_filtered_samples():
    """Hybrid: fetch_cop_samples(include_boiler=False) + local aggregate."""
    now = time.time()
    pure_rows = [
        {"ts": now - 100 + i, "cop": 4.0, "mode": "heating",
         "boiler_active": 0, "lwt": 35.0, "outdoor": 5.0, "flow_lmin": 10.0}
        for i in range(5)
    ]
    c = _mk_hybrid(pure_rows, mixed_cop=3.0)
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(c, now=now)

    c.db.async_fetch_cop_samples.assert_called()
    call = c.db.async_fetch_cop_samples.call_args
    assert call.kwargs.get("include_boiler") is False

    week = c._cop_hourly_cache["week"]
    heating = week["by_mode"]["heating"]
    assert abs(heating["cop_mean"] - 4.0) < 0.01, (
        f"hybrid COP polluted by boiler: got {heating['cop_mean']}, "
        f"expected 4.0 (pure-HP)"
    )
    assert heating["n_samples"] == 5


async def test_non_hybrid_unchanged():
    """Non-hybrid path uses rollup unchanged."""
    now = time.time()
    stats = {
        "n_hours": 10, "n_samples": 10,
        "cop_mean": 3.0, "cop_p10": 2.1, "cop_p90": 3.9,
        "cop_min": 2.1, "cop_max": 3.9,
    }
    c = _mk_non_hybrid(stats, {"heating": stats})
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(c, now=now)

    week = c._cop_hourly_cache["week"]
    assert week["cop_mean"] == 3.0
    c.db.async_fetch_cop_samples.assert_not_called()


async def test_hybrid_empty_after_filter():
    """Hybrid with only boiler samples: db returns empty, aggregator empty."""
    now = time.time()
    c = _mk_hybrid([], mixed_cop=2.0)
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(c, now=now)

    week = c._cop_hourly_cache["week"]
    assert week["n_samples"] == 0
    assert week["cop_mean"] is None


async def test_hybrid_multi_mode_by_mode_split():
    """Hybrid splits heating + dhw in by_mode correctly."""
    now = time.time()
    heating_rows = [
        {"ts": now - 100 + i, "cop": 4.0, "mode": "heating",
         "boiler_active": 0} for i in range(3)
    ]
    dhw_rows = [
        {"ts": now - 50 + i, "cop": 3.0, "mode": "dhw",
         "boiler_active": 0} for i in range(2)
    ]
    c = _mk_hybrid(heating_rows + dhw_rows, mixed_cop=2.5)
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(c, now=now)

    week = c._cop_hourly_cache["week"]
    assert abs(week["by_mode"]["heating"]["cop_mean"] - 4.0) < 0.01
    assert abs(week["by_mode"]["dhw"]["cop_mean"] - 3.0) < 0.01
    assert week["by_mode"]["heating"]["n_samples"] == 3
    assert week["by_mode"]["dhw"]["n_samples"] == 2


async def test_hybrid_ignores_malformed_rows():
    """Malformed rows (non-dict, missing ts, bad cop) are skipped."""
    now = time.time()
    rows = [
        None,
        {"mode": "heating"},
        {"ts": 1, "cop": 4.0, "mode": "heating"},
        {"ts": now - 100, "mode": "heating"},
        {"ts": now - 100, "cop": -1.0, "mode": "heating"},
        {"ts": now - 100, "cop": 4.0, "mode": "heating"},
    ]
    c = _mk_hybrid(rows, mixed_cop=2.0)
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(c, now=now)

    week = c._cop_hourly_cache["week"]
    assert week["by_mode"]["heating"]["n_samples"] == 1
    assert abs(week["by_mode"]["heating"]["cop_mean"] - 4.0) < 0.01
