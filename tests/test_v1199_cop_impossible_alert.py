"""v1.19.9 #123 R634: cop_physically_impossible alert + reject tracking.

When the 3-tier classifier rejects a COP sample (>1.5x Carnot),
the coordinator must track it so an alert fires that day:

  reject -> _cop_rejected_today_count++
         -> _cop_rejected_today_first_ts (if first)
         -> binary_states["cop_physically_impossible"] = True
         -> alert fires (dedup 1440 min, max 1x/day)
         -> reset at local-midnight

Source: prod-1 2026-11-05. No rejects observed on prod-1 today
(0/148), but future co-fire days with mode-switch artifacts will
trigger (RFI #127 Q4 id=148 cop=19.5 would have been a reject if
it exceeded 1.5x Carnot at that lwt/outdoor pair).
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from tests.test_rollup_concurrency import _mk_db
from tests.test_v1199_cop_gate_wire import (  # noqa: F401
    _mk_gate_coord,
    patched_compat,
)


# ============================================================
# Coordinator tracking: reject increments count
# ============================================================

@pytest.mark.asyncio
async def test_reject_increments_today_count(tmp_path, patched_compat):
    """R634: one reject -> count=1."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=100.0, lwt=30.0, outdoor=5.0)
        c._cop_rejected_today_count = 0
        c._cop_rejected_today_first_ts = 0.0
        await c._maybe_collect_cop_sample(time.time())
        assert c._cop_rejected_today_count == 1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_reject_records_first_ts(tmp_path, patched_compat):
    """R634: first reject sets first_ts; later rejects do not overwrite."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=100.0, lwt=30.0, outdoor=5.0)
        c._cop_rejected_today_count = 0
        c._cop_rejected_today_first_ts = 0.0
        t0 = 1700000000.0
        await c._maybe_collect_cop_sample(t0)
        first = c._cop_rejected_today_first_ts
        assert first == t0
        # Second reject
        c._last_cop_sample_ts = 0.0
        await c._maybe_collect_cop_sample(t0 + 10)
        assert c._cop_rejected_today_first_ts == first
        assert c._cop_rejected_today_count == 2
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_accept_does_not_increment_reject_count(tmp_path, patched_compat):
    """R634: accepted sample leaves counter untouched."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        c._cop_rejected_today_count = 0
        c._cop_rejected_today_first_ts = 0.0
        await c._maybe_collect_cop_sample(time.time())
        assert c._cop_rejected_today_count == 0
        assert c._cop_rejected_today_first_ts == 0.0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# Alert wiring: binary_states + context
# ============================================================

def test_binary_states_returns_key():
    """R634: _alert_binary_states returns cop_physically_impossible."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {}
    c._cop_rejected_today_count = 0
    c._defrost_7d_sum = 0
    c._buh_7d_ratio = 0.0
    c._db_retention_stale = {"fired": False}
    c._kmeans_stale = {"fired": False}
    c._energy_daily_anomaly = {"fired": False}
    c.store = MagicMock()
    c.store.last_cycle.return_value = None
    c.store.non_transient_today.return_value = []
    c.store.non_transient_in_window.return_value = 0
    c.store.cycles_in_window_mode.return_value = 0
    c.store.count_short_in_window_mode.return_value = 0
    c._compute_setpoint_oscillating = lambda: False
    snap = SimpleNamespace(
        last_success_ts=time.time(),
        anomaly=None,
        cop_degradation_week_pct=None,
        cop_vs_datasheet_pct=None,
        missing_attrs=[],
    )
    result = c._alert_binary_states(snap)
    assert "cop_physically_impossible" in result
    assert result["cop_physically_impossible"] is False
    # Now with rejects
    c._cop_rejected_today_count = 3
    result = c._alert_binary_states(snap)
    assert result["cop_physically_impossible"] is True


def test_alert_registered_in_const():
    """R634: NOTIF_ID + group + dedup + emoji present."""
    from custom_components.daikin_cycle_ml import const
    assert hasattr(const, "NOTIF_ID_COP_PHYSICALLY_IMPOSSIBLE")
    # Group map
    assert "cop_physically_impossible" in const.ALERT_GROUP_MAP
    # Dedup
    assert const.ALERT_DEDUP_DEFAULTS.get("cop_physically_impossible") == 1440
    # Emoji
    assert "cop_physically_impossible" in const.ALERT_TYPE_EMOJI


def test_alert_registered_in_notification_engine():
    """R634: BINARY_ALERT_MAP + NOTIF_ID_BY_TYPE present."""
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        BINARY_ALERT_MAP,
        NOTIF_ID_BY_TYPE,
    )
    assert "cop_physically_impossible" in BINARY_ALERT_MAP
    assert "cop_physically_impossible" in NOTIF_ID_BY_TYPE


def test_alert_titles_and_schema_present():
    """R634: ALERT_TITLES en/nl + ALERT_SCHEMA + ALERT_ADVICE present."""
    from custom_components.daikin_cycle_ml.engine.status_report import (
        ALERT_ADVICE,
        ALERT_SCHEMA,
        ALERT_TITLES,
    )
    assert "cop_physically_impossible" in ALERT_TITLES["en"]
    assert "cop_physically_impossible" in ALERT_TITLES["nl"]
    assert "cop_physically_impossible" in ALERT_SCHEMA
    assert "cop_physically_impossible" in ALERT_ADVICE["en"]
    assert "cop_physically_impossible" in ALERT_ADVICE["nl"]

# ============================================================
# R643: defensive branches in reject-increment (line 3267, 3270)
# ============================================================

@pytest.mark.asyncio
async def test_reject_handles_malformed_counter(tmp_path, patched_compat):
    """R643: counter=None -> defensive reset naar 1 (coordinator line 3267)."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=100.0, lwt=30.0, outdoor=5.0)
        c._cop_rejected_today_count = None  # type: ignore[assignment]
        c._cop_rejected_today_first_ts = 0.0
        await c._maybe_collect_cop_sample(time.time())
        assert c._cop_rejected_today_count == 1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_reject_handles_malformed_first_ts(tmp_path, patched_compat):
    """R643: first_ts=string -> defensive reset naar now (coordinator line 3270)."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=100.0, lwt=30.0, outdoor=5.0)
        c._cop_rejected_today_count = 0
        c._cop_rejected_today_first_ts = "bad"  # type: ignore[assignment]
        t0 = time.time()
        await c._maybe_collect_cop_sample(t0)
        assert c._cop_rejected_today_first_ts == t0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)

