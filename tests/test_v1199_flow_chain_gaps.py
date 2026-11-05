"""v1.19.9 #123 R639: full chain tests for gaps 1, 2, 3.

GAP 1: real ESPAltherma attrs -> build_compat_view -> parse -> classify -> DB.
       No patched_compat. Real attribute names, real values from prod-1.
       This catches attribute-key drifts that unit tests miss.

GAP 2: mode transition detected in _async_update_data -> SETTLE blocks
       subsequent COP sample within 300s. Full detection chain, not
       just "counter was manually set".

GAP 3: reject counter reset at day boundary -> alert can re-fire next day.
       Without this, alert fires once ever.
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
# GAP 1: cold-start, real attrs, no mock of build_compat_view
# ============================================================

@pytest.mark.asyncio
async def test_gap1_cold_start_real_attrs_to_db(tmp_path):
    """Real prod-1 attrs (2026-11-05 09:42) go through full pipeline.

    No patched_compat. Attr keys are the exact ESPAltherma names that
    build_compat_view expects. Value 6.18 cop / lwt 27.8 / out 2.9 is
    a real accepted sample from prod-1.
    """
    db = await _mk_db(tmp_path)
    try:
        c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
        c.db = db
        c.options = {}
        c.hass = MagicMock()
        c._cop_sample_seed_done = True
        c._last_cop_sample_ts = 0.0
        c.cop_sensor_entity = "sensor.cop"
        c._last_mode_change_ts = 0.0
        c._last_observed_mode = ""
        c._cop_rejected_today_count = 0
        c._cop_rejected_today_first_ts = 0.0

        # Mock COP sensor state
        st_cop = MagicMock()
        st_cop.state = "6.18"
        st_cop.attributes = {}
        c.hass.states.get.return_value = st_cop

        # Real ESPAltherma attr names from prod-1 2026-11-05 09:42
        c.data = SimpleNamespace(
            attrs={
                "Leaving water temp. before BUH (R1T)": 27.9,
                "Leaving water temp. after BUH (R2T)": 27.8,
                "Inlet water temp.(R4T)": 25.5,
                "Outdoor air temp.(R1T)": 2.9,
                "Flow sensor (l/min)": 14.6,
                "Defrost Operation": False,
            },
            mode="heating",
            state="running",
            boiler_active=False,
            is_hybrid=False,
            boiler_heat_active=False,
            boiler_dhw_active=False,
            cop=None,
        )
        c._resolve_cop_sample_mode = lambda: "heating"

        # Real build_compat_view (no patched_compat)
        await c._maybe_collect_cop_sample(time.time())

        async with db._conn.execute(
            "SELECT cop, lwt, outdoor, r1t, r4t, flow_lmin, mode, "
            "is_transition_artifact FROM cop_samples"
        ) as cur:
            rows = await cur.fetchall()

        assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
        r = rows[0]
        assert abs(r[0] - 6.18) < 0.01, f"cop={r[0]}"
        assert abs(r[1] - 27.8) < 0.1, f"lwt={r[1]}"
        assert abs(r[2] - 2.9) < 0.1, f"outdoor={r[2]}"
        assert abs(r[3] - 27.9) < 0.1, f"r1t={r[3]}"
        assert abs(r[4] - 25.5) < 0.1, f"r4t={r[4]}"
        assert abs(r[5] - 14.6) < 0.1, f"flow={r[5]}"
        assert r[6] == "heating"
        # Accept class -> flag=0
        assert r[7] == 0, f"flag={r[7]}"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# GAP 2: mode detection chain -> SETTLE blocks sample
# ============================================================

@pytest.mark.asyncio
async def test_gap2_mode_transition_detected_then_settle_blocks(
    tmp_path, patched_compat
):
    """heating -> dhw detected by _track_mode_transition -> SETTLE blocks.

    Tests the FULL chain:
      1. _track_mode_transition(snap, now) detects change
      2. _last_mode_change_ts = now
      3. _maybe_collect_cop_sample within 300s -> blocked
      4. _maybe_collect_cop_sample after 300s -> accepted
    """
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        c._last_mode_change_ts = 0.0
        c._last_observed_mode = ""

        # Tick 1: heating, no change yet (bootstrap sets it)
        snap1 = SimpleNamespace(mode="heating")
        c._track_mode_transition(snap1, now=1000.0)
        assert c._last_observed_mode == "heating"
        assert c._last_mode_change_ts == 1000.0

        # Tick 2: DHW -> change detected
        snap2 = SimpleNamespace(mode="dhw")
        c._track_mode_transition(snap2, now=1500.0)
        assert c._last_observed_mode == "dhw"
        assert c._last_mode_change_ts == 1500.0

        # Tick 3: COP sample at t=1600 (100s after change) -> blocked
        c._last_cop_sample_ts = 0.0
        await c._maybe_collect_cop_sample(1600.0)
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == 0, f"SETTLE should block at age=100s, got {n} rows"

        # Tick 4: COP sample at t=1900 (400s after change) -> accepted
        c._last_cop_sample_ts = 0.0
        await c._maybe_collect_cop_sample(1900.0)
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == 1, f"SETTLE should allow at age=400s, got {n} rows"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# GAP 3: day boundary resets reject counter -> alert can re-fire
# ============================================================

def test_gap3_day_boundary_resets_reject_counter():
    """Reject count reset at local-midnight -> alert fires again next day.

    Setup: coordinator with count=3 at day 2026-11-05.
    Advance to 2026-11-06 -> _maybe_reset_daily_accumulators -> count=0.
    """
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    # Fields touched by _maybe_reset_daily_accumulators
    c._runtime_day_key = "2026-11-05"
    c._energy_day_key = "2026-11-05"
    c._buh_step1_s = 0.0
    c._buh_step2_s = 0.0
    c._prev_defrost = False
    c._defrost_start_ts = None
    c._defrost_count_today = 0
    c._defrost_duration_s = 0.0
    c._energy_acc = {
        "heating": {"th": 1.0, "el": 0.2},
        "dhw": {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    c._energy_hwm = {
        "heating": {"th": 1.0, "el": 0.2},
        "dhw": {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    # Reject state
    c._cop_rejected_today_count = 3
    c._cop_rejected_today_first_ts = 1000.0
    c._cop_rejected_day_key = "2026-11-05"

    # Simulate next day noon
    tomorrow_ts = time.mktime((2026, 11, 6, 12, 0, 0, 0, 0, -1))
    c._maybe_reset_daily_accumulators(tomorrow_ts)

    assert c._cop_rejected_today_count == 0, (
        f"count should reset to 0, got {c._cop_rejected_today_count}"
    )
    assert c._cop_rejected_today_first_ts == 0.0
    assert c._cop_rejected_day_key == "2026-11-06"
    assert c._runtime_day_key == "2026-11-06"

    # Idempotent: same day again -> no double-reset issue
    c._cop_rejected_today_count = 1  # simulate new reject same day
    c._maybe_reset_daily_accumulators(tomorrow_ts + 3600)
    assert c._cop_rejected_today_count == 1, "same-day should not reset"

# ============================================================
# R643: 2 coverage-gap tests voor _track_mode_transition
# ============================================================

def test_track_mode_transition_malformed_mode():
    """R643: non-string mode -> silent return (coordinator line 3056)."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c._last_observed_mode = ""
    c._last_mode_change_ts = 0.0
    # None
    c._track_mode_transition(SimpleNamespace(mode=None), now=1000.0)
    assert c._last_mode_change_ts == 0.0
    assert c._last_observed_mode == ""
    # Int
    c._track_mode_transition(SimpleNamespace(mode=123), now=2000.0)
    assert c._last_mode_change_ts == 0.0
    assert c._last_observed_mode == ""


def test_track_mode_transition_same_mode_no_change():
    """R643: mode == last_observed -> NO change_ts update (line 3059 False branch)."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c._last_observed_mode = "heating"
    c._last_mode_change_ts = 1000.0
    # Same mode -> no change
    c._track_mode_transition(SimpleNamespace(mode="heating"), now=2000.0)
    assert c._last_mode_change_ts == 1000.0  # niet bijgewerkt
    assert c._last_observed_mode == "heating"

