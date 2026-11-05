"""v1.19.9 #123 R634 FLOW: complete reject -> alert -> message chain.

Unit tests testen individuele stukken (counter++, key bestaat,
message text). Deze flow test bewandelt de VOLLEDIGE keten zoals
die in productie draait:

  1. COP sample binnenkomt (cop=100, fysiek onmogelijk)
  2. classify_cop_sample -> "reject"
  3. _cop_rejected_today_count++
  4. row wordt NIET ge-insert (0 rows in DB)
  5. _alert_binary_states -> cop_physically_impossible=True
  6. _build_alert_context -> count=1
  7. evaluate_alerts -> AlertSpec voor cop_physically_impossible
  8. build_rich_alert -> message bevat count=1

Dit is de "chain of events" test die een unit test NIET dekt.

Source: prod-1 2026-11-05 (RFI #127 Q4 id=148 cop=19.5 analogie).
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
)
from custom_components.daikin_cycle_ml.engine.status_report import (
    build_rich_alert,
)
from tests.test_rollup_concurrency import _mk_db
from tests.test_v1199_cop_gate_wire import (  # noqa: F401
    _mk_gate_coord,
    patched_compat,
)


@pytest.mark.asyncio
async def test_full_reject_chain_produces_alert_and_message(
    tmp_path, patched_compat
):
    """R634 FLOW: reject -> counter -> binary_state -> context -> message.

    Eén test die de hele keten bewandelt zoals productie het doet.
    Faalt als één stap in de keten breekt, ook al werken de anderen.
    """
    db = await _mk_db(tmp_path)
    try:
        # --- STAP 1+2+3+4: sample komt binnen, wordt gerejecteerd ---
        c = _mk_gate_coord(db, cop=100.0, lwt=30.0, outdoor=5.0)
        # Initialize tracking fields zoals productie doet
        c._cop_rejected_today_count = 0
        c._cop_rejected_today_first_ts = 0.0
        c._cop_rejected_today_day_key = ""

        now = time.time()
        await c._maybe_collect_cop_sample(now)

        # STAP 3: counter is verhoogd
        assert c._cop_rejected_today_count == 1, (
            f"counter should be 1, got {c._cop_rejected_today_count}"
        )
        assert c._cop_rejected_today_first_ts == now

        # STAP 4: geen row geinsert
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n_rows = (await cur.fetchone())[0]
        assert n_rows == 0, f"reject should not insert, got {n_rows} rows"

        # --- STAP 5: _alert_binary_states toont True ---
        # Bouw een minimale snap + mock store
        c.store = MagicMock()
        c.store.last_cycle.return_value = None
        c.store.non_transient_today.return_value = []
        c.store.non_transient_in_window.return_value = 0
        c.store.cycles_in_window_mode.return_value = 0
        c.store.count_short_in_window_mode.return_value = 0
        c._compute_setpoint_oscillating = lambda: False
        c._defrost_7d_sum = 0
        c._buh_7d_ratio = 0.0
        c._db_retention_stale = {"fired": False}
        c._kmeans_stale = {"fired": False}
        c._energy_daily_anomaly = {"fired": False}
        snap = SimpleNamespace(
            last_success_ts=now,
            anomaly=None,
            cop_degradation_week_pct=None,
            cop_vs_datasheet_pct=None,
            missing_attrs=[],
        )
        binary_states = c._alert_binary_states(snap)
        assert binary_states["cop_physically_impossible"] is True, (
            "binary_state must be True after reject"
        )

        # --- STAP 6: _build_alert_context bevat count ---
        # Mock de helpers die context bouwen
        c.store.cycles_in_window = MagicMock(return_value=0)
        c._snap_attr = MagicMock(return_value=None)
        c._setpoint_current = MagicMock(return_value=None)
        c._setpoint_target = MagicMock(return_value=None)
        c._setpoint_delta = MagicMock(return_value=None)
        c._last_duration_min = MagicMock(return_value=None)
        c._setpoint_history = []
        c.config_entry = None
        ctx = c._build_alert_context(snap)
        assert "cop_physically_impossible" in ctx
        assert ctx["cop_physically_impossible"]["count"] == 1, (
            f"context count should be 1, got {ctx['cop_physically_impossible'].get('count')}"
        )

        # --- STAP 7: BINARY_ALERT_MAP heeft trigger ---
        assert "cop_physically_impossible" in BINARY_ALERT_MAP
        _bkey, _sev, _template = BINARY_ALERT_MAP["cop_physically_impossible"]
        assert _bkey == "cop_physically_impossible"
        assert _sev == "warning"

        # --- STAP 8: build_rich_alert produceert leesbare message ---
        # Vul context in zoals evaluate_alerts het doet
        alert_ctx = dict(ctx["cop_physically_impossible"])
        msg = build_rich_alert(
            "cop_physically_impossible",
            "warning",
            alert_ctx,
            language="en",
            emoji_enabled=True,
            full_model="EPRA12EAV3",
        )
        # Message moet count en advies bevatten
        assert "1" in msg, f"message should mention count=1: {msg!r}"
        assert "impossible" in msg.lower() or "Physically" in msg, (
            f"message should mention physical impossibility: {msg!r}"
        )
        # Message moet advies bevatten (uit ALERT_ADVICE)
        assert "sensor" in msg.lower() or "calibration" in msg.lower() or "Carnot" in msg, (
            f"message should include advice: {msg!r}"
        )

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_full_accept_chain_produces_no_alert(tmp_path, patched_compat):
    """R634 FLOW: accept -> geen counter -> geen alert -> geen message.

    Symmetrische test: bewijst dat de keten ook correct stil blijft
    als er niets mis is.
    """
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        c._cop_rejected_today_count = 0
        c._cop_rejected_today_first_ts = 0.0

        await c._maybe_collect_cop_sample(time.time())

        # Counter bleef 0
        assert c._cop_rejected_today_count == 0

        # 1 row geinsert
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == 1

        # Binary state False
        c.store = MagicMock()
        c.store.last_cycle.return_value = None
        c.store.non_transient_today.return_value = []
        c.store.non_transient_in_window.return_value = 0
        c.store.cycles_in_window_mode.return_value = 0
        c.store.count_short_in_window_mode.return_value = 0
        c._compute_setpoint_oscillating = lambda: False
        c._defrost_7d_sum = 0
        c._buh_7d_ratio = 0.0
        c._db_retention_stale = {"fired": False}
        c._kmeans_stale = {"fired": False}
        c._energy_daily_anomaly = {"fired": False}
        snap = SimpleNamespace(
            last_success_ts=time.time(),
            anomaly=None,
            cop_degradation_week_pct=None,
            cop_vs_datasheet_pct=None,
            missing_attrs=[],
        )
        binary_states = c._alert_binary_states(snap)
        assert binary_states["cop_physically_impossible"] is False

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
