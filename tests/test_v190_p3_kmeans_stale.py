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


# ==================================================================
# C2 — registration tests
# ==================================================================

def test_notif_id_kmeans_retrain_stale_constant():
    from custom_components.daikin_cycle_ml.const import (
        NOTIF_ID_KMEANS_RETRAIN_STALE, DOMAIN,
    )
    assert NOTIF_ID_KMEANS_RETRAIN_STALE == f"{DOMAIN}_kmeans_retrain_stale"


def test_alert_type_emoji_has_kmeans_retrain_stale():
    from custom_components.daikin_cycle_ml.const import ALERT_TYPE_EMOJI
    assert "kmeans_retrain_stale" in ALERT_TYPE_EMOJI
    assert ALERT_TYPE_EMOJI["kmeans_retrain_stale"] == "\u2699\ufe0f"


def test_alert_dedup_defaults_has_kmeans_retrain_stale():
    from custom_components.daikin_cycle_ml.const import ALERT_DEDUP_DEFAULTS
    assert "kmeans_retrain_stale" in ALERT_DEDUP_DEFAULTS
    assert ALERT_DEDUP_DEFAULTS["kmeans_retrain_stale"] == 1440


def test_binary_alert_map_has_kmeans_retrain_stale():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        BINARY_ALERT_MAP, SEV_INFO,
    )
    assert "kmeans_retrain_stale" in BINARY_ALERT_MAP
    bkey, sev, tmpl = BINARY_ALERT_MAP["kmeans_retrain_stale"]
    assert bkey == "kmeans_retrain_stale"
    assert sev == SEV_INFO
    assert "{hours_since_ok}" in tmpl
    assert "{consecutive_failures}" in tmpl
    assert "{advice}" in tmpl


def test_notif_id_by_type_has_kmeans_retrain_stale():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        NOTIF_ID_BY_TYPE,
    )
    from custom_components.daikin_cycle_ml.const import (
        NOTIF_ID_KMEANS_RETRAIN_STALE,
    )
    assert NOTIF_ID_BY_TYPE["kmeans_retrain_stale"] == NOTIF_ID_KMEANS_RETRAIN_STALE


def test_i18n_notifications_enabled_has_kmeans_key():
    import json
    from pathlib import Path
    for fname in ("strings.json", "translations/en.json", "translations/nl.json"):
        path = Path("custom_components/daikin_cycle_ml") / fname
        d = json.loads(path.read_text(encoding="utf-8"))
        ne = d["options"]["step"]["notifications_enabled"]["data"]
        assert "alert_enabled_kmeans_retrain_stale" in ne, f"missing in {fname}"
        assert len(ne) == 10, f"{fname} has {len(ne)}, expected 10"


def test_i18n_notifications_dedup_has_kmeans_key():
    import json
    from pathlib import Path
    for fname in ("strings.json", "translations/en.json", "translations/nl.json"):
        path = Path("custom_components/daikin_cycle_ml") / fname
        d = json.loads(path.read_text(encoding="utf-8"))
        nd = d["options"]["step"]["notifications_dedup"]["data"]
        assert "alert_agg_kmeans_retrain_stale_min" in nd, f"missing in {fname}"
        assert len(nd) == 18, f"{fname} has {len(nd)}, expected 18"


def test_config_flow_notifications_enabled_has_kmeans_field():
    """config_flow source contains the new toggle in notifications_enabled."""
    from pathlib import Path
    src = Path("custom_components/daikin_cycle_ml/config_flow.py").read_text(encoding="utf-8")
    assert 'alert_enabled_kmeans_retrain_stale' in src


# ==================================================================
# C3 — _compute_kmeans_stale cache helper + _alert_binary_states key
# ==================================================================

@pytest.mark.asyncio
async def test_compute_kmeans_stale_no_db():
    """Empty dict when db is None."""
    c = _bare(db=None)
    assert await c._compute_kmeans_stale() == {}


@pytest.mark.asyncio
async def test_compute_kmeans_stale_fresh_install_no_last_ok():
    """last_ok_ts absent -> fired=False, hours_since_ok=None."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={})
    c = _bare(db=db)
    result = await c._compute_kmeans_stale()
    assert result["fired"] is False
    assert result["hours_since_ok"] is None
    assert result["last_ok_ts"] is None
    assert result["stale_after_days"] == 14


@pytest.mark.asyncio
async def test_compute_kmeans_stale_13_days_no_fire():
    """13 days old: fired=False (under 14-day threshold)."""
    import time as _t
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        return_value={"last_ok_ts": _t.time() - 13 * 86400},
    )
    c = _bare(db=db)
    result = await c._compute_kmeans_stale()
    assert result["fired"] is False
    assert 300 < result["hours_since_ok"] < 330  # ~312 hours


@pytest.mark.asyncio
async def test_compute_kmeans_stale_15_days_fires():
    """15 days old: fired=True."""
    import time as _t
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        return_value={"last_ok_ts": _t.time() - 15 * 86400},
    )
    c = _bare(db=db)
    result = await c._compute_kmeans_stale()
    assert result["fired"] is True
    assert result["hours_since_ok"] > 14 * 24


@pytest.mark.asyncio
async def test_compute_kmeans_stale_db_exception_returns_empty():
    """DB read exception: returns {}, cache untouched."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=RuntimeError("boom"))
    c = _bare(db=db)
    assert await c._compute_kmeans_stale() == {}


@pytest.mark.asyncio
async def test_compute_kmeans_stale_corrupted_failures_count():
    """Non-numeric consecutive_failures -> coerced to 0, no crash."""
    import time as _t
    db = MagicMock()
    db.async_get_model_state = AsyncMock(
        return_value={
            "last_ok_ts": _t.time() - 15 * 86400,
            "consecutive_failures": "not_a_number",
        },
    )
    c = _bare(db=db)
    result = await c._compute_kmeans_stale()
    assert result["consecutive_failures"] == 0


def test_alert_binary_states_has_kmeans_retrain_stale_key():
    """_alert_binary_states returns kmeans_retrain_stale based on cache."""
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
    c = _bare(db=None)
    # Inject minimum attrs the function reads
    import time as _t
    c.options = {}
    c.store = MagicMock()
    c.store.last_cycle = MagicMock(return_value={})
    c.store.off_time_since_last = MagicMock(return_value=None)
    c.store.cycles_in_window = MagicMock(return_value=0)
    c.store.cycles_today = MagicMock(return_value=[])
    c.store.cycles_in_window_mode = MagicMock(return_value=0)
    c._defrost_7d_sum = 0
    c._buh_7d_ratio = 0.0
    c._db_retention_stale = {}
    c._kmeans_stale = {"fired": True}

    states = c._alert_binary_states(DataSnapshot())
    assert "kmeans_retrain_stale" in states
    assert states["kmeans_retrain_stale"] is True

    c._kmeans_stale = {"fired": False}
    states = c._alert_binary_states(DataSnapshot())
    assert states["kmeans_retrain_stale"] is False


@pytest.mark.asyncio
async def test_compute_kmeans_stale_non_dict_state_returns_empty():
    """Coverage: line 2308-2309 — non-dict data returns {}."""
    db = MagicMock()
    # Legacy corrupted: kmeans_state is a list instead of dict
    db.async_get_model_state = AsyncMock(return_value=[1, 2, 3])
    c = _bare(db=db)
    assert await c._compute_kmeans_stale() == {}
