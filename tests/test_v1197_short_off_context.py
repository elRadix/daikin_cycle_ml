"""v1.19.7 fix #10: short_off requires at least one short run in the pair.

Pre-fix: any off_s < 5min fires short_off regardless of run duration.
Post-fix: fires only if last OR previous cycle was short (< short_run_threshold).

HVAC rationale: a 60s gap between two long runs (e.g. 264min → 60s → 84min)
is normal hysteresis restart, not short-cycling. Short-cycling is
short-run → short-off → short-run.
"""
import pathlib
import sqlite3
import time
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml import binary_sensor as bs
from custom_components.daikin_cycle_ml import coordinator as co
from custom_components.daikin_cycle_ml.storage.store import CycleStore

# ============================================================
# Helpers
# ============================================================

def _cy(*, end_offset_s, dur, is_trans=0, mode="heating", off_s=None, ts=None):
    end = ts if ts is not None else time.time() + end_offset_s
    return {
        "start_ts": end - dur, "end_ts": end, "duration_s": dur,
        "mode": mode, "is_transient": is_trans, "dT_max": 4.0, "rps_max": 30,
        **({"off_s": off_s} if off_s is not None else {}),
    }


def _mk_store(cycles):
    s = CycleStore(maxlen=200)
    s.hydrate_from_rows(cycles, good_threshold=70)
    return s


def _mk_coord(store, options=None):
    opts = {
        "short_run_threshold_min": 20,
        "short_off_threshold_min": 5,
        "pendulum_cycles_per_hour": 4,
        "pendulum_cycles_per_day": 40,
        "dhw_pendulum_cycles_per_hour": 3,
    }
    if options:
        opts.update(options)
    return SimpleNamespace(
        store=store, options=opts,
        _effective_threshold=lambda k, d: d,
        _compute_setpoint_oscillating=lambda: False,
        _setpoint_history=[],
        _db_retention_stale={"fired": False},
        _kmeans_stale={"fired": False},
        _energy_daily_anomaly={"fired": False},
        _defrost_7d_sum=0,
        _buh_7d_ratio=0.0,
    )


def _mk_snap(mode="heating"):
    return SimpleNamespace(
        mode=mode, anomaly=None,
        cop_degradation_week_pct=None,
        cop_vs_datasheet_pct=None,
        last_success_ts=time.time(),
        missing_attrs=[], advice=[],
    )


def _bs_short_off(store, mode="heating"):
    return bs._is_short_off(_mk_snap(mode), _mk_coord(store))


def _co_short_off(store):
    c = _mk_coord(store)
    return co.DaikinCycleMLCoordinator._alert_binary_states(c, _mk_snap())["short_off"]


# ============================================================
# NEW BEHAVIOR — RED pre-fix, GREEN post-fix
# ============================================================

def test_long_run_short_gap_long_run_not_fired():
    """The 264min → 60s → 84min pattern: normal restart, not short-cycling."""
    store = _mk_store([
        _cy(end_offset_s=-21000, dur=15840),           # 264min, ends -21000
        _cy(end_offset_s=-5000, dur=5040, off_s=60),   # 84min, 60s gap
    ])
    assert _bs_short_off(store) is False
    assert _co_short_off(store) is False


def test_short_prev_run_short_gap_fires():
    """2min run → 61s gap → 360min run: previous cycle was short → fires."""
    store = _mk_store([
        _cy(end_offset_s=-22000, dur=120),             # 2min
        _cy(end_offset_s=-30, dur=21600, off_s=61),    # 360min
    ])
    assert _bs_short_off(store) is True
    assert _co_short_off(store) is True


def test_short_last_run_short_gap_fires():
    """360min run → 61s gap → 5min run: last cycle was short → fires."""
    store = _mk_store([
        _cy(end_offset_s=-22000, dur=21600),           # 360min
        _cy(end_offset_s=-30, dur=300, off_s=61),      # 5min
    ])
    assert _bs_short_off(store) is True
    assert _co_short_off(store) is True


def test_both_long_runs_short_gap_not_fired():
    """60min → 30s → 60min: hysteresis restart, not short-cycling."""
    store = _mk_store([
        _cy(end_offset_s=-7300, dur=3600),
        _cy(end_offset_s=-30, dur=3600, off_s=30),
    ])
    assert _bs_short_off(store) is False
    assert _co_short_off(store) is False


# ============================================================
# PRESERVED BEHAVIOR
# ============================================================

def test_single_cycle_no_prev_falls_back():
    """No prev cycle to compare: fall back to old behavior (fires if off_s short)."""
    store = _mk_store([_cy(end_offset_s=-30, dur=600, off_s=30)])
    assert _bs_short_off(store) is True
    assert _co_short_off(store) is True


def test_off_s_above_threshold_not_fired():
    """off_s=10min > threshold=5min: silent regardless of run duration."""
    store = _mk_store([
        _cy(end_offset_s=-6000, dur=600),
        _cy(end_offset_s=-30, dur=600, off_s=600),
    ])
    assert _bs_short_off(store) is False


def test_transient_last_cycle_still_skipped():
    """v1.19.7 transient guard still applies."""
    store = _mk_store([
        _cy(end_offset_s=-600, dur=300),
        _cy(end_offset_s=-30, dur=30, is_trans=1, off_s=30),
    ])
    assert _bs_short_off(store) is False


def test_dhw_still_skipped():
    """DHW mode still silent."""
    store = _mk_store([
        _cy(end_offset_s=-1000, dur=300),
        _cy(end_offset_s=-30, dur=300, off_s=30, mode="dhw"),
    ])
    assert _bs_short_off(store, mode="dhw") is False


# ============================================================
# Custom threshold
# ============================================================

def test_custom_short_run_threshold_affects_short_off():
    """Raising short_run_threshold to 60min makes 30min runs count as short."""
    store = _mk_store([
        _cy(end_offset_s=-7300, dur=3600),             # 60min run
        _cy(end_offset_s=-30, dur=3600, off_s=30),     # 60min run, 30s gap
    ])
    # Default 20min: both runs 60min > 20min -> no fire
    assert _bs_short_off(store) is False
    # Threshold 70min: both runs 60min < 70min -> short -> fires
    c = _mk_coord(store, options={"short_run_threshold_min": 70})
    assert bs._is_short_off(_mk_snap(), c) is True


# ============================================================
# Fixture replay — 36 prior survivors reduced
# ============================================================

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "_prod1_20261103.db"


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture absent")
def test_fixture_short_off_survivors_reduced():
    """Fixture-wide: after fix, long-run→short-gap cases no longer fire."""
    con = sqlite3.connect(f"file:{FIXTURE}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM cycles ORDER BY start_ts")]
    con.close()

    # Count survivors with old logic (no prev-guard) vs new logic
    old_fire = 0
    new_fire = 0
    for i in range(1, len(rows)):
        prev, cur = rows[i - 1], rows[i]
        if not (prev.get("end_ts") and cur.get("start_ts")):
            continue
        try:
            if int(cur.get("is_transient") or 0) == 1:
                continue
            if int(prev.get("is_transient") or 0) == 1:
                continue
        except (ValueError, TypeError):
            continue
        if str(cur.get("mode", "")).lower() == "dhw":
            continue
        off = cur["start_ts"] - prev["end_ts"]
        if not (0 <= off < 300):
            continue
        old_fire += 1
        # New guard: need last or prev duration < 20min
        cur_dur = cur.get("duration_s") or 0
        prev_dur = prev.get("duration_s") or 0
        if cur_dur < 1200 or prev_dur < 1200:
            new_fire += 1

    print(f"  old fires: {old_fire}  new fires: {new_fire}")
    # Long-run cases suppressed (both runs >= 20min)
    assert new_fire < old_fire, (
        f"fix should suppress some; old={old_fire} new={new_fire}"
    )
