"""I6 (v1.9.0 P3) — energy_daily_anomaly: persistence + compute helpers.

C1 scope: const + _persist_energy_baseline (Welford) + _compute_energy_daily_anomaly.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    ENERGY_ANOMALY_FLOOR_KWH,
    ENERGY_ANOMALY_MIN_DAYS,
    ENERGY_ANOMALY_SIGMA_THRESHOLD,
)
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _bare(db: Any = None) -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    return c


def _yesterday() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400.0))


# ========== Group A: const ==========

def test_sigma_threshold_is_2():
    assert ENERGY_ANOMALY_SIGMA_THRESHOLD == 2.0


def test_floor_kwh_is_2():
    assert ENERGY_ANOMALY_FLOOR_KWH == 2.0


def test_min_days_is_7():
    assert ENERGY_ANOMALY_MIN_DAYS == 7


# ========== Group B: _persist_energy_baseline ==========

@pytest.mark.asyncio
async def test_persist_no_db_returns():
    c = _bare(db=None)
    await c._persist_energy_baseline()


@pytest.mark.asyncio
async def test_persist_first_day_initializes_n1():
    db = MagicMock()
    y = _yesterday()
    db.async_get_model_state = AsyncMock(side_effect=[
        {},
        {"heating_el_kwh": 5.0, "dhw_el_kwh": 2.0, "cooling_el_kwh": 0.0},
    ])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    db.async_set_model_state.assert_awaited_once()
    key, state = db.async_set_model_state.await_args[0]
    assert key == "thermal_daily_baseline"
    assert state["heating"]["n"] == 1
    assert state["heating"]["mean"] == 5.0
    assert state["heating"]["last_day"] == y
    assert state["dhw"]["n"] == 1
    assert state["cooling"]["n"] == 0
    assert state["cooling"]["last_day"] == y


@pytest.mark.asyncio
async def test_persist_same_last_day_no_persist():
    db = MagicMock()
    y = _yesterday()
    existing = {
        "heating": {"mean": 5.0, "m2": 2.0, "n": 3, "last_day": y},
        "dhw":     {"mean": 2.0, "m2": 0.5, "n": 3, "last_day": y},
        "cooling": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": y},
    }
    db.async_get_model_state = AsyncMock(side_effect=[existing, {}])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    db.async_set_model_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_new_day_welford_advances():
    db = MagicMock()
    y = _yesterday()
    existing = {
        "heating": {"mean": 5.0, "m2": 2.0, "n": 3, "last_day": "2020-01-01"},
        "dhw":     {"mean": 2.0, "m2": 0.5, "n": 3, "last_day": "2020-01-01"},
        "cooling": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": "2020-01-01"},
    }
    db.async_get_model_state = AsyncMock(side_effect=[
        existing,
        {"heating_el_kwh": 7.0, "dhw_el_kwh": 2.0, "cooling_el_kwh": 0.0},
    ])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    key, state = db.async_set_model_state.await_args[0]
    assert state["heating"]["n"] == 4
    assert abs(state["heating"]["mean"] - 5.5) < 1e-9
    assert abs(state["heating"]["m2"] - 5.0) < 1e-9
    assert state["heating"]["last_day"] == y
    assert state["dhw"]["n"] == 4
    assert state["dhw"]["mean"] == 2.0
    assert state["dhw"]["last_day"] == y
    assert state["cooling"]["n"] == 0
    assert state["cooling"]["last_day"] == y


@pytest.mark.asyncio
async def test_persist_missing_yesterday_advances_marker():
    """energy_acc.<yesterday> = None → treated as {}; last_day advances, no Welford update."""
    db = MagicMock()
    y = _yesterday()
    existing = {
        "heating": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""},
        "dhw":     {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""},
        "cooling": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""},
    }
    db.async_get_model_state = AsyncMock(side_effect=[existing, None])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    # None → {} → all x=0 → advance last_day, n preserved (no Welford)
    db.async_set_model_state.assert_awaited_once()
    key, state = db.async_set_model_state.await_args[0]
    assert key == "thermal_daily_baseline"
    for mode in ("heating", "dhw", "cooling"):
        assert state[mode]["n"] == 0
        assert state[mode]["mean"] == 0.0
        assert state[mode]["last_day"] == y


@pytest.mark.asyncio
async def test_persist_state_not_dict_resets():
    """Baseline stored as non-dict → reset to empty, then advance last_day with x=0."""
    db = MagicMock()
    y = _yesterday()
    db.async_get_model_state = AsyncMock(side_effect=[["not", "a", "dict"], {}])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    db.async_set_model_state.assert_awaited_once()
    key, state = db.async_set_model_state.await_args[0]
    assert key == "thermal_daily_baseline"
    for mode in ("heating", "dhw", "cooling"):
        assert state[mode]["n"] == 0
        assert state[mode]["last_day"] == y


@pytest.mark.asyncio
async def test_persist_mode_state_not_dict_initialized():
    """One mode field is None → initialized to zeros; others preserved."""
    db = MagicMock()
    y = _yesterday()
    existing = {
        "heating": {"mean": 5.0, "m2": 2.0, "n": 3, "last_day": "2020-01-01"},
        "dhw":     None,
        "cooling": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""},
    }
    db.async_get_model_state = AsyncMock(side_effect=[
        existing,
        {"heating_el_kwh": 5.0, "dhw_el_kwh": 2.0, "cooling_el_kwh": 0.0},
    ])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    db.async_set_model_state.assert_awaited_once()
    _, state = db.async_set_model_state.await_args[0]
    assert state["heating"]["n"] == 4
    assert state["dhw"]["n"] == 1
    assert state["dhw"]["mean"] == 2.0
    assert state["cooling"]["n"] == 0


@pytest.mark.asyncio
async def test_persist_energy_y_not_dict_returns_early():
    """energy_acc.<yesterday> is a non-dict → early return, no persist."""
    db = MagicMock()
    existing = {
        "heating": {"mean": 5.0, "m2": 2.0, "n": 3, "last_day": "2020-01-01"},
        "dhw":     {"mean": 2.0, "m2": 0.5, "n": 3, "last_day": "2020-01-01"},
        "cooling": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": "2020-01-01"},
    }
    db.async_get_model_state = AsyncMock(side_effect=[existing, ["bad"]])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    db.async_set_model_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_x_valueerror_skips_mode():
    """Corrupt *_el_kwh string → skip that mode; other modes still finalize."""
    db = MagicMock()
    y = _yesterday()
    existing = {
        "heating": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""},
        "dhw":     {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""},
        "cooling": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""},
    }
    db.async_get_model_state = AsyncMock(side_effect=[
        existing,
        {"heating_el_kwh": "not-a-number", "dhw_el_kwh": 3.0, "cooling_el_kwh": 0.0},
    ])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    _, state = db.async_set_model_state.await_args[0]
    # heating skipped (still n=0, last_day unchanged)
    assert state["heating"]["n"] == 0
    assert state["heating"]["last_day"] == ""
    # dhw finalized
    assert state["dhw"]["n"] == 1
    assert state["dhw"]["mean"] == 3.0
    assert state["dhw"]["last_day"] == y


@pytest.mark.asyncio
async def test_persist_n_mean_m2_corrupt_resets():
    """Baseline payload with non-numeric n/mean/m2 → reset to 0 before Welford."""
    db = MagicMock()
    y = _yesterday()
    existing = {
        "heating": {"mean": "bad", "m2": "bad", "n": "bad", "last_day": "2020-01-01"},
        "dhw":     {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""},
        "cooling": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": ""},
    }
    db.async_get_model_state = AsyncMock(side_effect=[
        existing,
        {"heating_el_kwh": 5.0, "dhw_el_kwh": 0.0, "cooling_el_kwh": 0.0},
    ])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    _, state = db.async_set_model_state.await_args[0]
    # After reset: n=0, then Welford with x=5 → n=1, mean=5
    assert state["heating"]["n"] == 1
    assert state["heating"]["mean"] == 5.0
    assert state["heating"]["last_day"] == y


@pytest.mark.asyncio
async def test_persist_outer_exception_caught():
    """db.async_get_model_state raises → outer except fires, no re-raise."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=RuntimeError("db down"))
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    # Should not raise
    await c._persist_energy_baseline()
    db.async_set_model_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_all_already_finalized_no_persist():
    """All modes already at yesterday, energy_y present → changed=False, no persist."""
    db = MagicMock()
    y = _yesterday()
    existing = {
        "heating": {"mean": 5.0, "m2": 2.0, "n": 3, "last_day": y},
        "dhw":     {"mean": 2.0, "m2": 0.5, "n": 3, "last_day": y},
        "cooling": {"mean": 0.0, "m2": 0.0, "n": 0, "last_day": y},
    }
    db.async_get_model_state = AsyncMock(side_effect=[
        existing,
        {"heating_el_kwh": 7.0, "dhw_el_kwh": 2.0, "cooling_el_kwh": 0.0},
    ])
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    await c._persist_energy_baseline()
    db.async_set_model_state.assert_not_awaited()


# ========== Group C: _compute_energy_daily_anomaly ==========

@pytest.mark.asyncio
async def test_compute_no_db_returns_empty():
    c = _bare(db=None)
    assert await c._compute_energy_daily_anomaly() == {}


@pytest.mark.asyncio
async def test_compute_baseline_not_dict_returns_empty():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=["bad"])
    c = _bare(db=db)
    assert await c._compute_energy_daily_anomaly() == {}


@pytest.mark.asyncio
async def test_compute_energy_today_not_dict_returns_empty():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=[{}, ["bad"]])
    c = _bare(db=db)
    assert await c._compute_energy_daily_anomaly() == {}


@pytest.mark.asyncio
async def test_compute_mode_not_dict_skipped():
    """heating is None → skipped; dhw fires on its own."""
    db = MagicMock()
    baseline = {
        "heating": None,
        "dhw": {"n": 10, "mean": 2.0, "m2": 2.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 999.0, "dhw_el_kwh": 10.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is True
    assert result["mode"] == "dhw"


@pytest.mark.asyncio
async def test_compute_mode_payload_corrupt_skipped():
    """heating n/mean/m2 corrupt → skipped; dhw fires."""
    db = MagicMock()
    baseline = {
        "heating": {"n": "bad", "mean": "bad", "m2": "bad"},
        "dhw": {"n": 10, "mean": 2.0, "m2": 2.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 999.0, "dhw_el_kwh": 10.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is True
    assert result["mode"] == "dhw"


@pytest.mark.asyncio
async def test_compute_insufficient_history_no_fire():
    """n < 7 for all modes → no fire."""
    db = MagicMock()
    baseline = {
        "heating": {"n": 5, "mean": 2.0, "m2": 1.0},
        "dhw":     {"n": 6, "mean": 2.0, "m2": 1.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 999.0, "dhw_el_kwh": 999.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is False


@pytest.mark.asyncio
async def test_compute_sigma_zero_no_fire():
    """m2=0 → sigma=0 → skip (no div-by-zero)."""
    db = MagicMock()
    baseline = {
        "heating": {"n": 10, "mean": 2.0, "m2": 0.0},
        "dhw":     {"n": 0, "mean": 0.0, "m2": 0.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 999.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is False


@pytest.mark.asyncio
async def test_compute_today_el_corrupt_skipped():
    """heating today_el = 'bad' → skipped; dhw fires."""
    db = MagicMock()
    baseline = {
        "heating": {"n": 10, "mean": 2.0, "m2": 2.0},
        "dhw":     {"n": 10, "mean": 2.0, "m2": 2.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": "bad", "dhw_el_kwh": 10.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is True
    assert result["mode"] == "dhw"


@pytest.mark.asyncio
async def test_compute_below_floor_no_fire():
    """today_el < 2.0 → skip even if z huge."""
    db = MagicMock()
    baseline = {
        "heating": {"n": 10, "mean": 0.5, "m2": 0.1},
        "dhw":     {"n": 0, "mean": 0.0, "m2": 0.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 1.5}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is False


@pytest.mark.asyncio
async def test_compute_below_threshold_no_fire():
    """z < 2σ → no fire (mean=5, sigma=2, today=8 → z=1.5)."""
    db = MagicMock()
    baseline = {
        "heating": {"n": 10, "mean": 5.0, "m2": 40.0},
        "dhw":     {"n": 0, "mean": 0.0, "m2": 0.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 8.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is False


@pytest.mark.asyncio
async def test_compute_fires_above_threshold():
    """z > 2σ + today_el > floor → fires with full dict shape."""
    db = MagicMock()
    # mean=5, sigma=1, today=10 → z=5 > 2
    baseline = {
        "heating": {"n": 10, "mean": 5.0, "m2": 10.0},
        "dhw":     {"n": 0, "mean": 0.0, "m2": 0.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 10.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is True
    assert result["mode"] == "heating"
    assert result["today_el_kwh"] == 10.0
    assert result["baseline_el_mean"] == 5.0
    assert result["baseline_el_sigma"] == 1.0
    assert result["z_score"] == 5.0
    assert result["samples"] == 10
    assert result["threshold_sigma"] == 2.0


@pytest.mark.asyncio
async def test_compute_multi_mode_highest_z_wins():
    """heating z=5, dhw z=10 → dhw wins."""
    db = MagicMock()
    baseline = {
        "heating": {"n": 10, "mean": 5.0, "m2": 10.0},
        "dhw":     {"n": 10, "mean": 2.0, "m2": 10.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 10.0, "dhw_el_kwh": 12.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is True
    assert result["mode"] == "dhw"
    assert result["z_score"] == 10.0


@pytest.mark.asyncio
async def test_compute_none_exceed_no_fire():
    """All modes below threshold → default fired=False, mode=None."""
    db = MagicMock()
    baseline = {
        "heating": {"n": 10, "mean": 5.0, "m2": 40.0},
        "dhw":     {"n": 10, "mean": 3.0, "m2": 40.0},
        "cooling": {"n": 10, "mean": 1.0, "m2": 40.0},
    }
    today = {"heating_el_kwh": 6.0, "dhw_el_kwh": 4.0, "cooling_el_kwh": 2.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is False
    # Display mode = heating (highest today_el=6.0)
    assert result["mode"] == "heating"
    assert result["today_el_kwh"] == 6.0
    assert result["baseline_el_mean"] == 5.0
    assert result["baseline_el_sigma"] == 2.0
    assert result["z_score"] == 0.5
    assert result["samples"] == 10


@pytest.mark.asyncio
async def test_compute_outer_exception_returns_empty():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=RuntimeError("db down"))
    c = _bare(db=db)
    assert await c._compute_energy_daily_anomaly() == {}


@pytest.mark.asyncio
async def test_compute_lower_z_after_fire_kept_first():
    """Heating fires first with z=15.8; dhw exceeds threshold (z=9.5) but
    doesn't beat heating's z — heating wins, dhw block not entered.

    Covers branch 2418->2392 (if z > best: false → loop back).
    """
    db = MagicMock()
    # heating: mean=5, m2=1, n=10 → sigma=0.316; today=10 → z=15.8
    # dhw:     mean=2, m2=1, n=10 → sigma=0.316; today=5  → z=9.5
    baseline = {
        "heating": {"n": 10, "mean": 5.0, "m2": 1.0},
        "dhw":     {"n": 10, "mean": 2.0, "m2": 1.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 10.0, "dhw_el_kwh": 5.0}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is True
    assert result["mode"] == "heating"
    assert result["z_score"] == round((10.0 - 5.0) / (1.0 / 10) ** 0.5, 2)


# ---------- C4: schema / titles / advice / labels ----------

def test_energy_daily_anomaly_schema_has_5_fields():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_SCHEMA
    assert "energy_daily_anomaly" in ALERT_SCHEMA
    entry = ALERT_SCHEMA["energy_daily_anomaly"]
    assert len(entry) == 5
    fields = [f[1] for f in entry]
    assert fields == ["today_el_kwh", "baseline_el_mean", "baseline_el_sigma", "z_score", "mode"]


def test_energy_daily_anomaly_titles():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_TITLES
    assert ALERT_TITLES["en"]["energy_daily_anomaly"] == "Energy daily anomaly"
    assert ALERT_TITLES["nl"]["energy_daily_anomaly"] == "Energie-dagelijkse afwijking"


def test_energy_daily_anomaly_advice():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_ADVICE
    assert "energy_daily_anomaly" in ALERT_ADVICE["en"]
    assert "energy_daily_anomaly" in ALERT_ADVICE["nl"]
    assert len(ALERT_ADVICE["en"]["energy_daily_anomaly"]) > 10
    assert len(ALERT_ADVICE["nl"]["energy_daily_anomaly"]) > 10


def test_energy_daily_anomaly_label_keys():
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_LABELS
    for lang in ("en", "nl"):
        for key in ("today_el_kwh", "baseline_el_mean", "baseline_el_sigma", "z_score"):
            assert key in ALERT_LABELS[lang], f"ALERT_LABELS[{lang}] missing {key}"


def test_energy_daily_anomaly_renders_emoji():
    from custom_components.daikin_cycle_ml.const import ALERT_TYPE_EMOJI
    assert ALERT_TYPE_EMOJI["energy_daily_anomaly"] == "\u26a1\ufe0f"


# ---------- C5: dispatch / render end-to-end ----------

def test_energy_daily_anomaly_build_rich_alert_en():
    """Fired ctx renders via build_rich_alert with all schema fields."""
    from custom_components.daikin_cycle_ml.engine.status_report import build_rich_alert
    ctx = {
        "today_el_kwh": 15.5,
        "baseline_el_mean": 5.0,
        "baseline_el_sigma": 1.0,
        "z_score": 10.5,
        "mode": "heating",
        "advice": "Check valves.",
    }
    out = build_rich_alert("energy_daily_anomaly", "info", ctx, language="en")
    assert "Energy daily anomaly" in out
    assert "15.5" in out
    assert "heating" in out
    assert "10.5" in out


def test_energy_daily_anomaly_binary_alert_map_format():
    """BINARY_ALERT_MAP template formats with fire ctx (no literal {placeholders})."""
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        BINARY_ALERT_MAP,
        _format_message,
    )
    _, _, template = BINARY_ALERT_MAP["energy_daily_anomaly"]
    ctx = {
        "today_el_kwh": 15.5,
        "baseline_el_mean": 5.0,
        "baseline_el_sigma": 1.0,
        "z_score": 10.5,
        "mode": "heating",
        "advice": " Check valves.",
    }
    out = _format_message(template, ctx)
    assert "15.5" in out
    assert "heating" in out
    assert "Energy daily anomaly" in out
    # No unresolved placeholders for the fields we populated
    for placeholder in ("{today_el_kwh}", "{mode}", "{z_score}", "{baseline_el_mean}"):
        assert placeholder not in out, f"unresolved {placeholder}"


@pytest.mark.asyncio
async def test_compute_display_populated_when_not_fired_n_lt_min():
    """Prod state: n=1 baseline, today 5.88 kWh -> display shows real values, not zeros."""
    db = MagicMock()
    baseline = {
        "heating": {"n": 1, "mean": 2.51, "m2": 0.0},
        "dhw":     {"n": 0, "mean": 0.0, "m2": 0.0},
        "cooling": {"n": 0, "mean": 0.0, "m2": 0.0},
    }
    today = {"heating_el_kwh": 5.88}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is False
    assert result["mode"] == "heating"
    assert result["today_el_kwh"] == 5.88
    assert result["baseline_el_mean"] == 2.51
    assert result["baseline_el_sigma"] == 0.0
    assert result["z_score"] == 0.0
    assert result["samples"] == 1
    assert result["threshold_sigma"] == 2.0


@pytest.mark.asyncio
async def test_compute_all_modes_corrupt_energy_falls_back_zero():
    """All 3 modes' today_el corrupt -> fallback zero-dict, fired False."""
    db = MagicMock()
    baseline = {
        "heating": {"n": 10, "mean": 5.0, "m2": 40.0},
        "dhw":     {"n": 10, "mean": 3.0, "m2": 40.0},
        "cooling": {"n": 10, "mean": 1.0, "m2": 40.0},
    }
    today = {"heating_el_kwh": "bad", "dhw_el_kwh": "bad", "cooling_el_kwh": "bad"}
    db.async_get_model_state = AsyncMock(side_effect=[baseline, today])
    c = _bare(db=db)
    result = await c._compute_energy_daily_anomaly()
    assert result["fired"] is False
    assert result["mode"] is None
    assert result["today_el_kwh"] == 0.0
    assert result["baseline_el_mean"] == 0.0
    assert result["samples"] == 0
    assert result["threshold_sigma"] == 2.0


# ---------- C6: short_run duration_min store fallback ----------

def test_build_alert_context_short_run_falls_back_to_store():
    """When snap.last_record is None, duration_min comes from store.last_cycle."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
        DataSnapshot,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    # Provide required attrs accessed by _build_alert_context
    c.options = {}
    c._kmeans_stale = {}
    c._db_retention_stale = {}
    c._energy_daily_anomaly = {}
    class _Store:
        def last_cycle(self):
            return {"duration_s": 900}
    c.store = _Store()
    snap = DataSnapshot()
    snap.last_record = None
    ctx = c._build_alert_context(snap)
    assert ctx["short_run"]["duration_min"] == 15


def test_build_alert_context_short_run_store_raises_keeps_none():
    """Store.last_cycle() exception -> duration_min stays None (graceful)."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
        DataSnapshot,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {}
    c._kmeans_stale = {}
    c._db_retention_stale = {}
    c._energy_daily_anomaly = {}
    class _Store:
        def last_cycle(self):
            raise RuntimeError("db down")
    c.store = _Store()
    snap = DataSnapshot()
    snap.last_record = None
    ctx = c._build_alert_context(snap)
    assert ctx["short_run"]["duration_min"] is None
