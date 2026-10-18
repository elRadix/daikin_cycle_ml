"""I2 (v1.9.0 P3) — kmeans_retrain_stale: persistence layer.

C1 scope: _persist_kmeans_attempt helper + wiring into async_run_kmeans.
Coverage target: 8 tests, 100% branch on new code paths.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import KMEANS_STALE_AFTER_DAYS
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _bare(db: Any = None) -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    return c


def _rec(start_ts: float = 100.0) -> dict:
    """Cycle record matching is_valid_record() requirements.

    Field names verified against test_v040_coordinator_coverage.py and
    test_multibaseline_wiring.py: dT_max and dT_avg (not dt_max_k / dt_avg_k).
    """
    return {
        "start_ts": start_ts, "end_ts": start_ts + 100.0,
        "duration_s": 100, "mode": "heating",
        "dT_max": 5.0, "dT_avg": 3.0,
        "rps_max": 40, "rps_avg": 30, "outdoor_temp": 8.0,
        "buh_used": 0, "defrost_used": 0,
    }


# ---------- 1. constant exists ----------

def test_kmeans_stale_after_days_is_14():
    assert KMEANS_STALE_AFTER_DAYS == 14


# ---------- 2. persist success from empty ----------

@pytest.mark.asyncio
async def test_persist_attempt_success_from_empty():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    await c._persist_kmeans_attempt(
        ok=True, extra={"centroids": [[1, 2]], "labels": {0: "a"}, "ts": 1.0},
    )

    db.async_set_model_state.assert_awaited_once()
    key, payload = db.async_set_model_state.await_args[0]
    assert key == "kmeans_state"
    assert payload["centroids"] == [[1, 2]]
    assert payload["labels"] == {0: "a"}
    assert payload["consecutive_failures"] == 0
    assert payload["last_failure_reason"] is None
    assert "last_ok_ts" in payload
    assert "last_attempt_ts" in payload


# ---------- 3. persist failure from empty ----------

@pytest.mark.asyncio
async def test_persist_attempt_failure_from_empty():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    await c._persist_kmeans_attempt(ok=False, reason="too_few")

    db.async_set_model_state.assert_awaited_once()
    _, payload = db.async_set_model_state.await_args[0]
    assert payload["consecutive_failures"] == 1
    assert payload["last_failure_reason"] == "too_few"
    assert "last_ok_ts" not in payload


# ---------- 4. three consecutive failures increments ----------

@pytest.mark.asyncio
async def test_persist_attempt_three_failures_increments():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        return_value={"consecutive_failures": 2, "last_failure_reason": "too_few"},
    )
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    await c._persist_kmeans_attempt(ok=False, reason="kmeans_failed")

    _, payload = db.async_set_model_state.await_args[0]
    assert payload["consecutive_failures"] == 3
    assert payload["last_failure_reason"] == "kmeans_failed"


# ---------- 5. success after failures resets counters ----------

@pytest.mark.asyncio
async def test_persist_attempt_success_after_failures_resets():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        return_value={
            "consecutive_failures": 3,
            "last_failure_reason": "too_few",
            "last_ok_ts": 100.0,
        },
    )
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    await c._persist_kmeans_attempt(
        ok=True, extra={"centroids": [[1]], "labels": {}, "ts": 2.0},
    )

    _, payload = db.async_set_model_state.await_args[0]
    assert payload["consecutive_failures"] == 0
    assert payload["last_failure_reason"] is None
    assert payload["last_ok_ts"] > 100.0
    assert payload["centroids"] == [[1]]


# ---------- 6. async_run_kmeans too_few persists failure ----------

@pytest.mark.asyncio
async def test_run_kmeans_too_few_persists_failure():
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(return_value=[])
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    out = await c.async_run_kmeans(days=7)

    assert out["ok"] is False
    assert out["reason"] == "too_few"
    db.async_set_model_state.assert_awaited_once()
    _, payload = db.async_set_model_state.await_args[0]
    assert payload["last_failure_reason"] == "too_few"
    assert payload["consecutive_failures"] == 1


# ---------- 7. async_run_kmeans kmeans_failed persists failure ----------

@pytest.mark.asyncio
async def test_run_kmeans_kmeans_failed_persists_failure(monkeypatch):
    from custom_components.daikin_cycle_ml.ml import clustering
    db = MagicMock()
    db.async_fetch_cycles = AsyncMock(
        return_value=[_rec(0.0), _rec(1.0), _rec(2.0)],
    )
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    def boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(clustering, "kmeans", boom)
    out = await c.async_run_kmeans(days=7)

    assert out["ok"] is False
    assert out["reason"] == "kmeans_failed"
    db.async_set_model_state.assert_awaited_once()
    _, payload = db.async_set_model_state.await_args[0]
    assert payload["last_failure_reason"] == "kmeans_failed"


# ---------- 8. legacy state preserved ----------

@pytest.mark.asyncio
async def test_persist_attempt_preserves_legacy_payload():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        return_value={
            "centroids": [[5.0, 6.0]],
            "labels": {0: "legacy"},
            "ts": 999.0,
        },
    )
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    await c._persist_kmeans_attempt(ok=False, reason="too_few")

    _, payload = db.async_set_model_state.await_args[0]
    assert payload["centroids"] == [[5.0, 6.0]]
    assert payload["labels"] == {0: "legacy"}
    assert payload["ts"] == 999.0
    assert payload["last_failure_reason"] == "too_few"


# ---------- 9. _persist_kmeans_attempt: db is None ----------

@pytest.mark.asyncio
async def test_persist_attempt_db_none_returns_early():
    """Coverage: guard when self.db is None (defensive getattr path)."""
    c = _bare(db=None)
    # Should not raise, should not attempt to write
    await c._persist_kmeans_attempt(ok=True, extra={"centroids": [[1]]})


# ---------- 10. _persist_kmeans_attempt: read fails ----------

@pytest.mark.asyncio
async def test_persist_attempt_read_exception_swallowed():
    """Coverage: guard when async_get_model_state raises (R366-safe)."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=RuntimeError("read boom"))
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    # Should not raise, should not write (early return on read failure)
    await c._persist_kmeans_attempt(ok=True, extra={"centroids": [[1]]})
    db.async_set_model_state.assert_not_awaited()


# ---------- 11. _persist_kmeans_attempt: write fails ----------

@pytest.mark.asyncio
async def test_persist_attempt_write_exception_swallowed():
    """Coverage: guard when async_set_model_state raises (R366-safe)."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_set_model_state = AsyncMock(side_effect=RuntimeError("write boom"))
    c = _bare(db=db)
    # Should not raise
    await c._persist_kmeans_attempt(ok=False, reason="too_few")


# ---------- 12. coverage: non-dict existing state (line 832->834 branch) ----------

@pytest.mark.asyncio
async def test_persist_attempt_existing_state_not_dict():
    """Coverage: line 832->834 — existing is non-dict, coerced to {}."""
    db = MagicMock()
    # Legacy corrupted state: a string instead of dict
    db.async_get_model_state = AsyncMock(return_value="corrupted_not_a_dict")
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    await c._persist_kmeans_attempt(ok=False, reason="too_few")

    db.async_set_model_state.assert_awaited_once()
    _, payload = db.async_set_model_state.await_args[0]
    # Non-dict existing was discarded; state built from scratch
    assert payload["consecutive_failures"] == 1
    assert payload["last_failure_reason"] == "too_few"


# ---------- 13. coverage: non-numeric consecutive_failures (lines 841-842) ----------

@pytest.mark.asyncio
async def test_persist_attempt_prev_failures_not_convertible():
    """Coverage: lines 841-842 — int(prev) raises, prev_i falls back to 0."""
    db = MagicMock()
    # Legacy corrupted state: consecutive_failures is a string that can't be int()'d
    db.async_get_model_state = AsyncMock(
        return_value={"consecutive_failures": "not_a_number"},
    )
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    await c._persist_kmeans_attempt(ok=False, reason="too_few")

    db.async_set_model_state.assert_awaited_once()
    _, payload = db.async_set_model_state.await_args[0]
    # Non-numeric prev treated as 0, incremented to 1
    assert payload["consecutive_failures"] == 1
    assert payload["last_failure_reason"] == "too_few"


# ---------- 14. coverage: success path with no extra payload (line 832->834) ----------

@pytest.mark.asyncio
async def test_persist_attempt_success_without_extra():
    """Coverage: line 832->834 — ok=True, extra=None, skips state.update()."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        return_value={"centroids": [[1, 2]], "labels": {0: "a"}, "ts": 5.0},
    )
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)

    # Success with no extra — centroids/labels from existing must survive
    await c._persist_kmeans_attempt(ok=True, extra=None)

    db.async_set_model_state.assert_awaited_once()
    _, payload = db.async_set_model_state.await_args[0]
    assert payload["centroids"] == [[1, 2]]
    assert payload["labels"] == {0: "a"}
    assert payload["ts"] == 5.0
    assert payload["consecutive_failures"] == 0
    assert payload["last_failure_reason"] is None
    assert "last_ok_ts" in payload
