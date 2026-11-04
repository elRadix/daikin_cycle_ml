"""v1.19.8: alerts_today sensor + db queries + coordinator cache."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS
from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    return db


def _mid_day_now() -> float:
    """Noon today (local), avoiding midnight-boundary flakiness in CI."""
    lt = time.localtime()
    today_start = time.mktime(
        (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
    )
    return today_start + 12 * 3600


# 1. db count method exists and works
async def test_db_count_alerts_since(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        await db.async_insert_alert("short_run", "warning", "m1", ts=now - 100)
        await db.async_insert_alert("short_off", "warning", "m2", ts=now - 50)
        await db.async_insert_alert("source_stale", "critical", "m3", ts=now - 10)
        assert (await db.async_count_alerts_since(now - 200)) == 3
        assert (await db.async_count_alerts_since(now - 20)) == 1
    finally:
        await db.async_close()


# 2. db fetch returns dicts
async def test_db_fetch_alerts_since(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        await db.async_insert_alert("short_run", "warning", "msg", ts=now - 10)
        rows = await db.async_fetch_alerts_since(now - 100, limit=10)
        assert len(rows) == 1
        r = rows[0]
        assert r["alert_type"] == "short_run"
        assert r["severity"] == "warning"
        assert r["message"] == "msg"
        assert "ts" in r
    finally:
        await db.async_close()


# 3. fetch respects limit and returns newest first
async def test_db_fetch_alerts_since_limit(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        for i in range(5):
            await db.async_insert_alert(f"t{i}", "warning", f"m{i}", ts=now - 100 + i)
        rows = await db.async_fetch_alerts_since(now - 200, limit=3)
        assert len(rows) == 3
        assert rows[0]["message"] == "m4"
    finally:
        await db.async_close()


# 4. coordinator refresh populates cache with full shape
async def test_coordinator_refresh_populates_cache(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = _mid_day_now()
        await db.async_insert_alert("short_run", "warning", "m1", ts=now - 100)
        await db.async_insert_alert("short_off", "warning", "m2", ts=now - 50)
        await db.async_insert_alert("short_run", "warning", "m3", ts=now - 10)
        c = SimpleNamespace(
            db=db,
            _alerts_today_cache={},
            _alerts_today_cache_ts=0.0,
            _alerts_today_dirty=False,
        )
        await DaikinCycleMLCoordinator._refresh_alerts_today(c, now=now)
        cache = c._alerts_today_cache
        assert cache["total"] == 3
        assert cache["by_type"]["short_run"] == 2
        assert cache["by_type"]["short_off"] == 1
        assert cache["by_severity"]["warning"] == 3
        assert len(cache["alerts"]) == 3
        assert cache["alerts"][0]["type"] == "short_run"
        assert cache["truncated"] is False
    finally:
        await db.async_close()


# 5. old alerts (3 days ago) excluded
async def test_coordinator_refresh_excludes_old(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = _mid_day_now()
        await db.async_insert_alert("short_run", "warning", "recent", ts=now - 60)
        await db.async_insert_alert("short_run", "warning", "old", ts=now - 3 * 86400)
        c = SimpleNamespace(
            db=db,
            _alerts_today_cache={},
            _alerts_today_cache_ts=0.0,
            _alerts_today_dirty=False,
        )
        await DaikinCycleMLCoordinator._refresh_alerts_today(c, now=now)
        assert c._alerts_today_cache["total"] == 1
    finally:
        await db.async_close()


# 6. throttle: skip db hit if < 60s since last refresh
async def test_coordinator_refresh_throttle():
    mock_db = MagicMock()
    mock_db.async_count_alerts_since = AsyncMock(return_value=0)
    mock_db.async_fetch_alerts_since = AsyncMock(return_value=[])
    now = _mid_day_now()
    c = SimpleNamespace(
        db=mock_db,
        _alerts_today_cache={},
        _alerts_today_cache_ts=now - 30.0,
        _alerts_today_dirty=False,
    )
    await DaikinCycleMLCoordinator._refresh_alerts_today(c, now=now)
    mock_db.async_count_alerts_since.assert_not_called()


# 7. dirty flag bypasses throttle
async def test_coordinator_refresh_dirty():
    mock_db = MagicMock()
    mock_db.async_count_alerts_since = AsyncMock(return_value=1)
    mock_db.async_fetch_alerts_since = AsyncMock(return_value=[
        {"ts": time.time(), "alert_type": "short_run", "severity": "warning",
         "message": "m", "aggregated_count": 1}
    ])
    now = _mid_day_now()
    c = SimpleNamespace(
        db=mock_db,
        _alerts_today_cache={},
        _alerts_today_cache_ts=now - 30.0,
        _alerts_today_dirty=True,
    )
    await DaikinCycleMLCoordinator._refresh_alerts_today(c, now=now)
    mock_db.async_count_alerts_since.assert_called_once()


# 8. db error preserves cache
async def test_coordinator_refresh_db_error():
    mock_db = MagicMock()
    mock_db.async_count_alerts_since = AsyncMock(side_effect=RuntimeError("boom"))
    now = _mid_day_now()
    c = SimpleNamespace(
        db=mock_db,
        _alerts_today_cache={"total": 5},
        _alerts_today_cache_ts=0.0,
        _alerts_today_dirty=False,
    )
    await DaikinCycleMLCoordinator._refresh_alerts_today(c, now=now)
    assert c._alerts_today_cache == {"total": 5}


# 9. DataSnapshot has alerts_today field
def test_snap_has_alerts_today_field():
    s = DataSnapshot()
    assert hasattr(s, "alerts_today")
    assert s.alerts_today == {}


# 10. sensor def + attr_fn present
def test_sensor_alerts_today_in_defs():
    keys = [d.get("key") for d in SENSOR_DEFS]
    assert "alerts_today" in keys
    entry = next(d for d in SENSOR_DEFS if d.get("key") == "alerts_today")
    assert "value_fn" in entry
    assert "attr_fn" in entry


def test_sensor_value_fn_and_attr_fn():
    """Exercise value_fn + attr_fn so coverage hits them."""
    from custom_components.daikin_cycle_ml import sensor as sensor_mod
    entry = next(d for d in sensor_mod.SENSOR_DEFS if d.get("key") == "alerts_today")
    snap = DataSnapshot()
    snap.alerts_today = {
        "since": "2026-11-04T00:00:00",
        "total": 5,
        "by_type": {"short_run": 3, "short_off": 2},
        "by_severity": {"warning": 5},
        "alerts": [],
        "truncated": False,
    }
    coord = SimpleNamespace()
    assert entry["value_fn"](snap, coord) == 5
    attrs = entry["attr_fn"](snap, coord)
    assert attrs["total"] == 5
    assert attrs["by_type"]["short_run"] == 3
    assert attrs["since"] == "2026-11-04T00:00:00"


async def test_coordinator_refresh_malformed_ts(tmp_path):
    """Malformed ts -> ts_iso=None fallback (coverage 973-974)."""
    db = await _mk_db(tmp_path)
    try:
        now = _mid_day_now()
        await db.async_insert_alert("short_run", "warning", "valid", ts=now - 60)
        conn = db._require()
        await conn.execute(
            "INSERT INTO alerts (ts, alert_type, severity, message, aggregated_count) "
            "VALUES (?,?,?,?,?)",
            ("not_a_number", "short_off", "warning", "bad_ts", 1),
        )
        await conn.commit()
        c = SimpleNamespace(
            db=db,
            _alerts_today_cache={},
            _alerts_today_cache_ts=0.0,
            _alerts_today_dirty=True,
        )
        await DaikinCycleMLCoordinator._refresh_alerts_today(c, now=now)
        # Malformed ts -> ts_iso None, maar alert blijft in lijst
        bad = [a for a in c._alerts_today_cache.get("alerts", []) if a["type"] == "short_off"]
        assert len(bad) == 1
        assert bad[0]["time"] is None
    finally:
        await db.async_close()
