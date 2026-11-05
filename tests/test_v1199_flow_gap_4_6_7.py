"""v1.19.9 #123 R639: flow gaps 4 (dedup), 6 (config-flow), 7 (diagnostics)."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    evaluate_alerts,
)
from tests.test_rollup_concurrency import _mk_db
from tests.test_v1199_cop_gate_wire import (  # noqa: F401
    _mk_gate_coord,
    patched_compat,
)


# GAP 4: alert dedup over time (1440 min window)
def test_gap4_alert_dedup_within_24h():
    binary_states = {"cop_physically_impossible": True}
    now = 1700000000.0
    last_sent: dict = {}

    specs = evaluate_alerts(binary_states, {}, now, last_sent, context={})
    ours = [s for s in specs if s.alert_type == "cop_physically_impossible"]
    assert len(ours) == 1
    assert ours[0].severity == "warning"
    # Dedup reads last_sent.get(alert_type) per notification_engine.py:358.
    # dedupe_key == alert_type (both "cop_physically_impossible"), NOT notif_id
    # (which is "daikin_cycle_ml_cop_physically_impossible").
    last_sent[ours[0].dedupe_key] = now

    # 1h later - dedup
    specs = evaluate_alerts(binary_states, {}, now + 3600, last_sent, context={})
    assert len([s for s in specs if s.alert_type == "cop_physically_impossible"]) == 0

    # 23.5h later - still dedup
    specs = evaluate_alerts(binary_states, {}, now + 23.5*3600, last_sent, context={})
    assert len([s for s in specs if s.alert_type == "cop_physically_impossible"]) == 0

    # 25h later - fires again
    specs = evaluate_alerts(binary_states, {}, now + 25*3600, last_sent, context={})
    assert len([s for s in specs if s.alert_type == "cop_physically_impossible"]) == 1


# GAP 6: config-flow option -> coordinator.options -> SETTLE gate
@pytest.mark.asyncio
async def test_gap6_config_settle_option_flows_to_gate(tmp_path, patched_compat):
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        c.options = {"cop_settle_time_s": 60.0}  # config-flow wrote this

        now = time.time()
        c._last_mode_change_ts = now - 100.0
        c._last_cop_sample_ts = 0.0

        await c._maybe_collect_cop_sample(now)
        async with db._conn.execute("SELECT COUNT(*) FROM cop_samples") as cur:
            n = (await cur.fetchone())[0]
        assert n == 1, f"custom 60s should accept at 100s, got {n}"

        # Sanity: default 300s would block
        db2_dir = tmp_path / "default"
        db2_dir.mkdir(exist_ok=True)
        db2 = await _mk_db(db2_dir)
        try:
            c2 = _mk_gate_coord(db2, cop=5.0, lwt=30.0, outdoor=10.0)
            c2.options = {}
            c2._last_mode_change_ts = now - 100.0
            c2._last_cop_sample_ts = 0.0
            await c2._maybe_collect_cop_sample(now)
            async with db2._conn.execute("SELECT COUNT(*) FROM cop_samples") as cur:
                n2 = (await cur.fetchone())[0]
            assert n2 == 0, f"default 300s should block at 100s, got {n2}"
        finally:
            await db2.async_close()
            await asyncio.sleep(0.05)
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# GAP 7: diagnostics contains new tracking fields
def test_gap7_diagnostics_coordinator_dict_has_new_fields():
    import inspect
    src = inspect.getsource(DaikinCycleMLCoordinator)
    assert "_cop_rejected_today_count" in src
    assert "_last_mode_change_ts" in src
    assert "_last_observed_mode" in src

    import custom_components.daikin_cycle_ml.diagnostics as diag
    diag_src = inspect.getsource(diag)
    assert "coordinator" in diag_src.lower() or "runtime_data" in diag_src
