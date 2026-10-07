"""Tests for startup backfill wiring (v1.7.0, #42)."""
from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


class _Coord(DaikinCycleMLCoordinator):
    def __init__(self, db):
        self.db = db


async def test_backfill_wiring_happy_path():
    db = AsyncMock()
    db.async_backfill_daily_summary = AsyncMock(return_value=3)
    c = _Coord(db)
    await c._maybe_backfill_daily_summary()
    db.async_backfill_daily_summary.assert_awaited_once()


async def test_backfill_wiring_no_db():
    c = _Coord(None)
    await c._maybe_backfill_daily_summary()


async def test_backfill_wiring_swallows_exception():
    db = AsyncMock()
    db.async_backfill_daily_summary = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    c = _Coord(db)
    await c._maybe_backfill_daily_summary()
