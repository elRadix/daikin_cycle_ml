"""v1.12.5 — kmeans startup backfill + scheduled instrumentation (#125)."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _mk_coord(hass: Any, store: dict[str, Any]) -> DaikinCycleMLCoordinator:
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    coord.hass = hass
    coord.db = MagicMock()

    async def _get(key: str, default: Any = None) -> Any:
        return store.get(key, default)

    async def _set(key: str, value: Any) -> None:
        store[key] = value

    coord.db.async_get_model_state = AsyncMock(side_effect=_get)
    coord.db.async_set_model_state = AsyncMock(side_effect=_set)
    coord._kmeans_backfill_unsub = None
    return coord


def _patch(coord: Any, ret: Any = None) -> AsyncMock:
    m = AsyncMock(
        return_value=ret if ret is not None else {"ok": True, "n": 10, "k": 3}
    )
    setattr(coord, "async_run_kmeans", m)
    return m


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_triggers_when_stale(hass: Any) -> None:
    store: dict[str, Any] = {
        "kmeans_state": {"last_ok_ts": time.time() - 26 * 3600}
    }
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    await coord._run_kmeans_backfill_check(None)
    m.assert_awaited_once()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_no_trigger_when_fresh(hass: Any) -> None:
    store: dict[str, Any] = {
        "kmeans_state": {"last_ok_ts": time.time() - 1 * 3600}
    }
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    await coord._run_kmeans_backfill_check(None)
    m.assert_not_awaited()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_callback_writes_fire_ts_on_non_sunday(hass: Any) -> None:
    store: dict[str, Any] = {"kmeans_state": {}}
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    now = MagicMock()
    now.weekday.return_value = 1
    await coord._async_kmeans_callback(now)
    m.assert_not_awaited()
    assert "last_scheduled_fire_ts" in store["kmeans_state"]


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_callback_writes_outcome_on_too_few(hass: Any) -> None:
    store: dict[str, Any] = {"kmeans_state": {}}
    coord = _mk_coord(hass, store)
    m = _patch(coord, ret={"ok": False, "reason": "too_few", "n": 2})
    now = MagicMock()
    now.weekday.return_value = 6
    await coord._async_kmeans_callback(now)
    state = store["kmeans_state"]
    assert state.get("last_scheduled_outcome") == "too_few"
    assert state.get("last_scheduled_cycles_n") == 2


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_merge_kmeans_state_preserves_existing_keys(hass: Any) -> None:
    store: dict[str, Any] = {
        "kmeans_state": {"centroids": [[1.0, 2.0]], "ts": 123.0}
    }
    coord = _mk_coord(hass, store)
    await coord._merge_kmeans_state({"last_scheduled_fire_ts": 456.0})
    assert store["kmeans_state"]["centroids"] == [[1.0, 2.0]]
    assert store["kmeans_state"]["last_scheduled_fire_ts"] == 456.0


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_setup_kmeans_backfill_idempotent(hass: Any) -> None:
    store: dict[str, Any] = {"kmeans_state": {}}
    coord = _mk_coord(hass, store)
    marker = object()
    coord._kmeans_backfill_unsub = marker
    entry = MagicMock()
    await coord.async_setup_kmeans_backfill(entry)
    assert coord._kmeans_backfill_unsub is marker
    entry.async_on_unload.assert_not_called()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_shutdown_handles_no_timer(hass: Any) -> None:
    coord = _mk_coord(hass, {})
    coord._kmeans_backfill_unsub = None
    setattr(coord, "_async_flush_accumulators", AsyncMock())
    await coord._async_handle_shutdown()
    assert coord._kmeans_backfill_unsub is None


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_shutdown_cancels_pending_timer(hass: Any) -> None:
    coord = _mk_coord(hass, {})
    cancel = MagicMock()
    coord._kmeans_backfill_unsub = cancel
    setattr(coord, "_async_flush_accumulators", AsyncMock())
    await coord._async_handle_shutdown()
    cancel.assert_called_once()
    assert coord._kmeans_backfill_unsub is None


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_shutdown_swallows_cancel_error(hass: Any) -> None:
    coord = _mk_coord(hass, {})
    coord._kmeans_backfill_unsub = MagicMock(
        side_effect=RuntimeError("boom")
    )
    setattr(coord, "_async_flush_accumulators", AsyncMock())
    await coord._async_handle_shutdown()
    assert coord._kmeans_backfill_unsub is None


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_merge_kmeans_state_swallows_write_error(hass: Any) -> None:
    store: dict[str, Any] = {"kmeans_state": {"a": 1}}
    coord = _mk_coord(hass, store)
    coord.db.async_set_model_state = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    await coord._merge_kmeans_state({"b": 2})
    assert store["kmeans_state"]["a"] == 1


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_merge_kmeans_state_handles_no_db(hass: Any) -> None:
    coord = _mk_coord(hass, {"kmeans_state": {"a": 1}})
    coord.db = None
    await coord._merge_kmeans_state({"b": 2})


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_handles_no_db(hass: Any) -> None:
    coord = _mk_coord(hass, {})
    coord.db = None
    coord._kmeans_backfill_unsub = object()
    await coord._run_kmeans_backfill_check(None)
    assert coord._kmeans_backfill_unsub is None


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_handles_read_error(hass: Any) -> None:
    coord = _mk_coord(hass, {})
    coord.db.async_get_model_state = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    m = _patch(coord)
    await coord._run_kmeans_backfill_check(None)
    m.assert_not_awaited()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_handles_non_dict_state(hass: Any) -> None:
    coord = _mk_coord(hass, {})
    coord.db.async_get_model_state = AsyncMock(return_value=[1, 2, 3])
    m = _patch(coord)
    await coord._run_kmeans_backfill_check(None)
    m.assert_not_awaited()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_handles_bad_last_ok_ts(hass: Any) -> None:
    store: dict[str, Any] = {"kmeans_state": {"last_ok_ts": "garbage"}}
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    await coord._run_kmeans_backfill_check(None)
    m.assert_awaited_once()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_handles_missing_last_ok_ts(hass: Any) -> None:
    store: dict[str, Any] = {"kmeans_state": {}}
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    await coord._run_kmeans_backfill_check(None)
    m.assert_awaited_once()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_handles_run_error(hass: Any) -> None:
    store: dict[str, Any] = {
        "kmeans_state": {"last_ok_ts": time.time() - 26 * 3600}
    }
    coord = _mk_coord(hass, store)
    setattr(coord, "async_run_kmeans", AsyncMock(
        side_effect=RuntimeError("boom")
    ))
    await coord._run_kmeans_backfill_check(None)


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_setup_kmeans_backfill_registers_unload(hass: Any) -> None:
    store: dict[str, Any] = {"kmeans_state": {}}
    coord = _mk_coord(hass, store)
    entry = MagicMock()
    await coord.async_setup_kmeans_backfill(entry)
    cancel = coord._kmeans_backfill_unsub
    assert cancel is not None
    entry.async_on_unload.assert_called_once_with(cancel)
    cancel()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_post_migration_fires_when_ready(hass: Any) -> None:
    store: dict[str, Any] = {"data_migration_v1_12_4": {"completed": True}}
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    from unittest.mock import patch as _p, AsyncMock as _AM
    with _p(
        "custom_components.daikin_cycle_ml.services._do_recompute_baseline",
        new=_AM(return_value={"computed": True, "days": 30}),
    ):
        handled = await coord._post_migration_retrain_check(coord.db)
    assert handled is True
    m.assert_awaited_once()
    assert "post_v1124_retrain_v1125" in store
    assert "post_v1124_baseline_v1125" in store


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_post_migration_skips_when_no_marker(hass: Any) -> None:
    store: dict[str, Any] = {}
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    handled = await coord._post_migration_retrain_check(coord.db)
    assert handled is False
    m.assert_not_awaited()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_post_migration_defers_when_incomplete(hass: Any) -> None:
    store: dict[str, Any] = {
        "data_migration_v1_12_4": {"completed": False}
    }
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    handled = await coord._post_migration_retrain_check(coord.db)
    assert handled is True
    m.assert_not_awaited()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_post_migration_skips_when_all_done(hass: Any) -> None:
    store: dict[str, Any] = {
        "data_migration_v1_12_4": {"completed": True},
        "post_v1124_retrain_v1125": {"ts": 1.0},
        "post_v1124_baseline_v1125": {"ts": 1.0},
    }
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    handled = await coord._post_migration_retrain_check(coord.db)
    assert handled is False
    m.assert_not_awaited()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_post_migration_kmeans_fails_no_marker(hass: Any) -> None:
    store: dict[str, Any] = {"data_migration_v1_12_4": {"completed": True}}
    coord = _mk_coord(hass, store)
    m = _patch(coord, ret={"ok": False, "reason": "too_few", "n": 2})
    from unittest.mock import patch as _p, AsyncMock as _AM
    with _p(
        "custom_components.daikin_cycle_ml.services._do_recompute_baseline",
        new=_AM(return_value={"computed": True, "days": 30}),
    ):
        handled = await coord._post_migration_retrain_check(coord.db)
    assert handled is True
    assert "post_v1124_retrain_v1125" not in store
    assert "post_v1124_baseline_v1125" in store


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_post_migration_only_baseline_needed(hass: Any) -> None:
    store: dict[str, Any] = {
        "data_migration_v1_12_4": {"completed": True},
        "post_v1124_retrain_v1125": {"ts": 1.0},
    }
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    from unittest.mock import patch as _p, AsyncMock as _AM
    with _p(
        "custom_components.daikin_cycle_ml.services._do_recompute_baseline",
        new=_AM(return_value={"computed": True, "days": 30}),
    ):
        handled = await coord._post_migration_retrain_check(coord.db)
    assert handled is True
    m.assert_not_awaited()
    assert "post_v1124_baseline_v1125" in store


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_post_migration_baseline_not_computed(hass: Any) -> None:
    store: dict[str, Any] = {
        "data_migration_v1_12_4": {"completed": True},
        "post_v1124_retrain_v1125": {"ts": 1.0},
    }
    coord = _mk_coord(hass, store)
    from unittest.mock import patch as _p, AsyncMock as _AM
    with _p(
        "custom_components.daikin_cycle_ml.services._do_recompute_baseline",
        new=_AM(return_value={"computed": False, "days": 30}),
    ):
        handled = await coord._post_migration_retrain_check(coord.db)
    assert handled is True
    assert "post_v1124_baseline_v1125" not in store


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_falls_through_on_migration_error(hass: Any) -> None:
    store: dict[str, Any] = {}
    coord = _mk_coord(hass, store)
    calls = {"n": 0}
    async def _get(key: str, default: Any = None) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {}
    coord.db.async_get_model_state = AsyncMock(side_effect=_get)
    m = _patch(coord)
    await coord._run_kmeans_backfill_check(None)
    m.assert_awaited_once()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_post_migration_kmeans_only(hass: Any) -> None:
    """Line 1042 FALSE: km=None, bl=present -> kmeans runs, baseline skipped."""
    store: dict[str, Any] = {
        "data_migration_v1_12_4": {"completed": True},
        "post_v1124_baseline_v1125": {"ts": 1.0},
    }
    coord = _mk_coord(hass, store)
    m = _patch(coord)
    handled = await coord._post_migration_retrain_check(coord.db)
    assert handled is True
    m.assert_awaited_once()
    assert "post_v1124_retrain_v1125" in store


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_backfill_non_dict_trigger2(hass: Any) -> None:
    """Line 1085: Trigger 1 returns False, then kmeans_state non-dict."""
    calls = {"n": 0}
    async def _get(key: str, default: Any = None) -> Any:
        calls["n"] += 1
        if key == "data_migration_v1_12_4":
            return None
        return [1, 2, 3]
    coord = _mk_coord(hass, {})
    coord.db.async_get_model_state = AsyncMock(side_effect=_get)
    m = _patch(coord)
    await coord._run_kmeans_backfill_check(None)
    m.assert_not_awaited()
