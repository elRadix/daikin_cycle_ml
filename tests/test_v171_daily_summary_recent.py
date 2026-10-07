"""v1.7.1-pre.1: daily_summary_recent cache + sensor tests."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml import sensor as s_mod
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
    _compute_daily_summary_recent,
)


def _make_coord() -> DaikinCycleMLCoordinator:
    """Coordinator stub without __init__ side effects (R258)."""
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = None
    c.options = {}
    c._daily_summary_recent = None
    return c


def _row(
    day: str,
    mode: str,
    *,
    cycles: int = 1,
    total_duration_s: int = 3600,
    duration_max: int | None = 3600,
    quality_sum: int = 80,
    buh_count: int = 0,
    defrost_count: int = 0,
) -> dict[str, Any]:
    return {
        "day": day,
        "mode": mode,
        "cycles": cycles,
        "total_duration_s": total_duration_s,
        "duration_max": duration_max,
        "quality_sum": quality_sum,
        "buh_count": buh_count,
        "defrost_count": defrost_count,
    }


# ---------- _compute_daily_summary_recent ----------

def test_compute_empty_rows_zeroed_payload() -> None:
    out = _compute_daily_summary_recent([])
    assert out["state"] == 0
    assert out["days_available"] == 0
    assert out["days_count"] == 0
    assert out["latest_day"] is None
    assert out["oldest_day"] is None
    assert out["days"] == []
    assert set(out["totals_by_mode"]) == {"heating", "dhw", "cooling"}
    for mode in ("heating", "dhw", "cooling"):
        assert out["totals_by_mode"][mode] == {
            "days": 0, "cycles": 0, "dur_min": 0.0, "buh": 0, "defrost": 0,
        }


def test_compute_single_row_fields() -> None:
    out = _compute_daily_summary_recent([
        _row(
            "2026-10-07", "heating", cycles=2,
            total_duration_s=14405, duration_max=10805,
            quality_sum=170, buh_count=1, defrost_count=1,
        )
    ])
    assert out["state"] == 2
    assert out["days_available"] == 1
    assert out["days_count"] == 1
    assert out["latest_day"] == "2026-10-07"
    assert out["oldest_day"] == "2026-10-07"
    assert len(out["days"]) == 1
    d = out["days"][0]
    assert d["day"] == "2026-10-07"
    assert d["mode"] == "heating"
    assert d["cycles"] == 2
    assert d["dur_min"] == round(14405 / 60.0, 1)
    assert d["dur_min_avg"] == round(14405 / 2 / 60.0, 1)
    assert d["dur_max"] == round(10805 / 60.0, 1)
    assert d["quality_avg"] == round(170 / 2, 1)
    assert d["buh"] == 1
    assert d["defrost"] == 1
    h = out["totals_by_mode"]["heating"]
    assert h["days"] == 1
    assert h["cycles"] == 2
    assert h["dur_min"] == d["dur_min"]
    assert h["buh"] == 1
    assert h["defrost"] == 1


def test_compute_multi_day_sorted_desc() -> None:
    """R312: >=2 distinct days closes the sort back-edge."""
    out = _compute_daily_summary_recent([
        _row("2026-10-05", "heating", cycles=1),
        _row("2026-10-07", "heating", cycles=2),
        _row("2026-10-06", "heating", cycles=3),
    ])
    assert [d["day"] for d in out["days"]] == [
        "2026-10-07", "2026-10-06", "2026-10-05",
    ]
    assert out["latest_day"] == "2026-10-07"
    assert out["oldest_day"] == "2026-10-05"
    assert out["state"] == 6


def test_compute_same_day_multi_mode_sorted_by_mode() -> None:
    out = _compute_daily_summary_recent([
        _row("2026-10-05", "heating", cycles=1),
        _row("2026-10-05", "dhw", cycles=2),
    ])
    assert [d["mode"] for d in out["days"]] == ["heating", "dhw"]
    assert out["days_count"] == 1
    assert out["days_available"] == 1
    assert out["state"] == 3


def test_compute_unknown_mode_skipped_from_totals() -> None:
    out = _compute_daily_summary_recent([_row("2026-10-07", "bogus")])
    assert out["days"][0]["mode"] == "bogus"
    for mode in ("heating", "dhw", "cooling"):
        assert out["totals_by_mode"][mode]["days"] == 0


def test_compute_null_mode_becomes_unknown() -> None:
    r = _row("2026-10-07", "heating")
    r["mode"] = None
    out = _compute_daily_summary_recent([r])
    assert out["days"][0]["mode"] == "unknown"


def test_compute_cycles_zero_defensive() -> None:
    out = _compute_daily_summary_recent([
        _row(
            "2026-10-07", "heating", cycles=0, total_duration_s=0,
            duration_max=0, quality_sum=0,
        )
    ])
    assert out["days"][0]["dur_min_avg"] == 0.0
    assert out["days"][0]["quality_avg"] == 0.0
    assert out["state"] == 0


def test_compute_missing_keys_defensive() -> None:
    out = _compute_daily_summary_recent([{"day": "2026-10-07"}])
    d = out["days"][0]
    assert d["mode"] == "unknown"
    assert d["cycles"] == 0
    assert d["dur_min"] == 0.0
    assert d["dur_max"] == 0.0
    assert d["buh"] == 0
    assert d["defrost"] == 0


def test_compute_null_duration_max_treated_as_zero() -> None:
    r = _row("2026-10-07", "heating")
    r["duration_max"] = None
    out = _compute_daily_summary_recent([r])
    assert out["days"][0]["dur_max"] == 0.0


# ---------- _refresh_daily_summary_recent ----------

async def test_refresh_no_db() -> None:
    c = _make_coord()
    await c._refresh_daily_summary_recent()
    assert c._daily_summary_recent is None


async def test_refresh_happy() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_daily_summary = AsyncMock(
        return_value=[_row("2026-10-07", "heating", cycles=2)]
    )
    await c._refresh_daily_summary_recent()
    assert c._daily_summary_recent is not None
    assert c._daily_summary_recent["state"] == 2
    c.db.async_daily_summary.assert_awaited_once_with(days=36500)


async def test_refresh_swallows_exception() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_daily_summary = AsyncMock(side_effect=RuntimeError("boom"))
    await c._refresh_daily_summary_recent()
    assert c._daily_summary_recent is None


# ---------- daily_summary_recent property ----------

def test_property_returns_cached() -> None:
    c = _make_coord()
    c._daily_summary_recent = {"state": 9}
    assert c.daily_summary_recent == {"state": 9}


def test_property_returns_none_initially() -> None:
    assert _make_coord().daily_summary_recent is None


# ---------- _maybe_rollup_day integration ----------

async def test_rollup_day_refreshes_cache() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_rollup_day = AsyncMock(return_value=1)
    c.db.async_daily_summary = AsyncMock(
        return_value=[_row("2026-10-07", "heating")]
    )
    await c._maybe_rollup_day({"end_ts": time.time()})
    c.db.async_rollup_day.assert_awaited_once()
    c.db.async_daily_summary.assert_awaited_once_with(days=36500)
    assert c._daily_summary_recent is not None


async def test_rollup_day_no_db_skips_refresh() -> None:
    c = _make_coord()
    c._refresh_daily_summary_recent = AsyncMock()
    await c._maybe_rollup_day({"end_ts": time.time()})
    c._refresh_daily_summary_recent.assert_not_awaited()


async def test_rollup_day_option_disabled_skips_refresh() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.options = {"daily_summary_live_enabled": False}
    c._refresh_daily_summary_recent = AsyncMock()
    await c._maybe_rollup_day({"end_ts": time.time()})
    c._refresh_daily_summary_recent.assert_not_awaited()


async def test_rollup_day_invalid_end_ts_skips_refresh() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c._refresh_daily_summary_recent = AsyncMock()
    await c._maybe_rollup_day({"end_ts": "not-a-number"})
    c._refresh_daily_summary_recent.assert_not_awaited()


async def test_rollup_day_exception_skips_refresh() -> None:
    """New early-return branch (b206d64): rollup raises -> no refresh."""
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_rollup_day = AsyncMock(side_effect=RuntimeError("boom"))
    c._refresh_daily_summary_recent = AsyncMock()
    await c._maybe_rollup_day({"end_ts": time.time()})
    c._refresh_daily_summary_recent.assert_not_awaited()


# ---------- _maybe_backfill_daily_summary integration ----------

async def test_backfill_refreshes_cache() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_backfill_daily_summary = AsyncMock(return_value=3)
    c.db.async_daily_summary = AsyncMock(
        return_value=[_row("2026-10-07", "heating")]
    )
    await c._maybe_backfill_daily_summary()
    c.db.async_backfill_daily_summary.assert_awaited_once()
    c.db.async_daily_summary.assert_awaited_once_with(days=36500)
    assert c._daily_summary_recent is not None


async def test_backfill_no_db_skips_refresh() -> None:
    c = _make_coord()
    c._refresh_daily_summary_recent = AsyncMock()
    await c._maybe_backfill_daily_summary()
    c._refresh_daily_summary_recent.assert_not_awaited()


async def test_backfill_exception_skips_refresh() -> None:
    """New early-return branch (b206d64): backfill raises -> no refresh."""
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_backfill_daily_summary = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    c._refresh_daily_summary_recent = AsyncMock()
    await c._maybe_backfill_daily_summary()
    c._refresh_daily_summary_recent.assert_not_awaited()


# ---------- sensor integration ----------

def test_sensor_defs_contains_daily_summary_recent() -> None:
    keys = {d["key"] for d in s_mod.SENSOR_DEFS}
    assert "daily_summary_recent" in keys


def test_sensor_def_has_value_and_attr_fn() -> None:
    entry = next(
        d for d in s_mod.SENSOR_DEFS if d["key"] == "daily_summary_recent"
    )
    assert callable(entry["value_fn"])
    assert entry["attr_fn"] is s_mod._attrs_daily_summary_recent
    assert entry["name"] == "Recent daily summary"
    assert entry["icon"] == "mdi:calendar-range"


def test_attrs_full_payload() -> None:
    payload = {
        "state": 5,
        "days_available": 2,
        "days_count": 2,
        "latest_day": "2026-10-07",
        "oldest_day": "2026-10-06",
        "days": [{"day": "2026-10-07", "mode": "heating"}],
        "totals_by_mode": {"heating": {"days": 1, "cycles": 1}},
    }
    c = MagicMock()
    c.daily_summary_recent = payload
    out = s_mod._attrs_daily_summary_recent(DataSnapshot(), c)
    assert out["days_available"] == 2
    assert out["days_count"] == 2
    assert out["latest_day"] == "2026-10-07"
    assert out["oldest_day"] == "2026-10-06"
    assert out["days"] == [{"day": "2026-10-07", "mode": "heating"}]
    assert out["totals_by_mode"] == {"heating": {"days": 1, "cycles": 1}}
    assert "state" not in out


def test_attrs_none_payload_defaults() -> None:
    c = MagicMock()
    c.daily_summary_recent = None
    out = s_mod._attrs_daily_summary_recent(DataSnapshot(), c)
    assert out["days_available"] == 0
    assert out["days_count"] == 0
    assert out["latest_day"] is None
    assert out["oldest_day"] is None
    assert out["days"] == []
    assert out["totals_by_mode"] == {}


def test_value_fn_extracts_state_from_cache() -> None:
    entry = next(
        d for d in s_mod.SENSOR_DEFS if d["key"] == "daily_summary_recent"
    )
    c = MagicMock()
    c.daily_summary_recent = {"state": 42}
    assert entry["value_fn"](DataSnapshot(), c) == 42


def test_value_fn_none_cache() -> None:
    entry = next(
        d for d in s_mod.SENSOR_DEFS if d["key"] == "daily_summary_recent"
    )
    c = MagicMock()
    c.daily_summary_recent = None
    assert entry["value_fn"](DataSnapshot(), c) is None
