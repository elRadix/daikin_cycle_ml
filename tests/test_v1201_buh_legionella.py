"""v1.20.1: Legionella BUH penalty exemption (#289).

Legionella runs (DHW tank >= 60°C) require BUH assistance and should
not count as a quality penalty. Legitimate BUH during normal heating
or DHW below 60°C remains penalized.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.engine.quality_scorer import (
    PENALTY_BUH,
    score_cycle,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _good_record():
    return {"duration_s": 3600, "dT_max": 8.0, "buh_used": 0}


# --- RED tests (fail on current code) --------------------------------------


def test_buh_penalty_skipped_during_legionella():
    """RED: DHW cycle at 65°C with BUH -> no penalty (unavoidable)."""
    r = _good_record()
    r["mode"] = "dhw"
    r["dhw_tank_temp"] = 65.0
    r["buh_used"] = 1
    assert score_cycle(r, off_time_s=3600) == 100, (
        f"got {score_cycle(r, off_time_s=3600)}, expected 100 "
        "(legionella BUH should be waived)"
    )


def test_buh_penalty_at_exact_60():
    """RED: dhw_tank_temp == 60.0 -> waived (>= 60 threshold)."""
    r = _good_record()
    r["mode"] = "dhw"
    r["dhw_tank_temp"] = 60.0
    r["buh_used"] = 1
    assert score_cycle(r, off_time_s=3600) == 100


@pytest.mark.asyncio
async def test_cycles_schema_has_dhw_tank_temp(tmp_path):
    """RED: v30 schema adds cycles.dhw_tank_temp REAL column."""
    db = CycleDB(str(tmp_path / "test.db"))
    await db.async_open()
    await db.async_initialize()
    try:
        conn = db._require()
        cur = await conn.execute("PRAGMA table_info(cycles)")
        cols = {row[1] for row in await cur.fetchall()}
        await cur.close()
        assert "dhw_tank_temp" in cols, (
            f"v30 schema missing dhw_tank_temp; cols={sorted(cols)}"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


def test_coordinator_wires_dhw_tank_temp_from_attrs():
    """RED: coordinator imports helper + sets record['dhw_tank_temp']."""
    src = Path(
        "custom_components/daikin_cycle_ml/coordinator.py"
    ).read_text()
    assert "dhw_tank_temp_from_attrs" in src, (
        "coordinator does not import dhw_tank_temp_from_attrs"
    )
    found = any(
        "record[" in line and "dhw_tank_temp" in line
        for line in src.splitlines()
    )
    assert found, (
        "coordinator does not set record['dhw_tank_temp'] before scoring"
    )


# --- Regression guards (must stay GREEN before/after) ----------------------


def test_buh_penalty_applied_dhw_below_60():
    """GREEN: DHW at 55°C with BUH -> penalty (not legionella)."""
    r = _good_record()
    r["mode"] = "dhw"
    r["dhw_tank_temp"] = 55.0
    r["buh_used"] = 1
    assert score_cycle(r, off_time_s=3600) == 100 - PENALTY_BUH


def test_buh_penalty_applied_heating():
    """GREEN: heating with BUH -> penalty (backwards compatible)."""
    r = _good_record()
    r["mode"] = "heating"
    r["buh_used"] = 1
    assert score_cycle(r, off_time_s=3600) == 100 - PENALTY_BUH


def test_buh_penalty_applied_no_tank_temp():
    """GREEN: DHW with BUH but missing dhw_tank_temp -> penalty."""
    r = _good_record()
    r["mode"] = "dhw"
    r["buh_used"] = 1
    assert score_cycle(r, off_time_s=3600) == 100 - PENALTY_BUH


# --- Hypothesis fuzz (R676: ≥200 cases) -----------------------------------


def test_fuzz_buh_penalty_invariants():
    """Fuzz score_cycle: BUH-penalty logic holds under random inputs.

    Properties:
    1. Score always in [0, 100] regardless of garbage inputs.
    2. Legionella waiver only when (mode=='dhw' AND tank>=60 AND buh)
    3. Waived-BUH score == no-BUH score (penalty fully skipped)
    4. Non-waived BUH score == no-BUH score - 10 (penalty fully applied)
    """
    from hypothesis import given, settings
    from hypothesis import strategies as st

    mode_st = st.sampled_from(
        ["heating", "dhw", "cooling", "unknown", "", None]
    )
    temp_st = st.one_of(
        st.none(),
        st.floats(
            min_value=-50.0, max_value=90.0, allow_nan=False,
            allow_infinity=False,
        ),
        st.just(60.0),  # exact boundary
        st.just(59.999),
        st.just(60.001),
    )
    buh_st = st.one_of(
        st.just(0), st.just(1), st.just(True), st.just(False),
        st.none(),
    )
    duration_st = st.one_of(
        st.none(),
        st.floats(
            min_value=0.0, max_value=86400.0 * 3,
            allow_nan=False, allow_infinity=False,
        ),
        st.just(3600.0),
    )
    dt_st = st.one_of(
        st.none(),
        st.floats(
            min_value=-10.0, max_value=30.0,
            allow_nan=False, allow_infinity=False,
        ),
    )

    @settings(max_examples=250, deadline=None)
    @given(
        mode=mode_st,
        tank=temp_st,
        buh=buh_st,
        dur=duration_st,
        dt=dt_st,
    )
    def _prop(mode, tank, buh, dur, dt):
        base = {
            "duration_s": dur,
            "dT_max": dt,
            "buh_used": buh,
            "mode": mode,
            "dhw_tank_temp": tank,
        }
        s = score_cycle(base, off_time_s=3600)
        # Invariant 1: always in range
        assert 0 <= s <= 100, f"score out of range: {s} for {base}"

        # Compare to no-BUH baseline
        no_buh = dict(base)
        no_buh["buh_used"] = 0
        s_no_buh = score_cycle(no_buh, off_time_s=3600)

        # Determine if waiver should apply
        has_buh = bool(buh)
        is_dhw = mode == "dhw"
        has_temp = isinstance(tank, (int, float))
        temp_ok = has_temp and tank >= 60.0
        should_waive = has_buh and is_dhw and temp_ok

        if has_buh:
            if should_waive:
                # Invariant 3: waiver == no-BUH score
                assert s == s_no_buh, (
                    f"waiver mismatch: {s} != {s_no_buh} for {base}"
                )
            else:
                # Invariant 4: penalty applied
                # s_no_buh could be <10, so score floors at 0
                expected = max(0, s_no_buh - 10)
                assert s == expected, (
                    f"penalty mismatch: {s} != {expected} for {base}"
                )

    _prop()


def test_fuzz_score_cycle_never_negative():
    """Fuzz: pathological inputs never produce negative scores."""
    from hypothesis import given, settings
    from hypothesis import strategies as st

    junk = st.one_of(
        st.none(),
        st.just("garbage"),
        st.just([1, 2, 3]),
        st.just({"nested": 1}),
        st.integers(min_value=-1000, max_value=100000),
    )

    @settings(max_examples=200, deadline=None)
    @given(dur=junk, dt=junk, buh=junk)
    def _prop(dur, dt, buh):
        r = {"duration_s": dur, "dT_max": dt, "buh_used": buh}
        s = score_cycle(r, off_time_s=3600)
        assert 0 <= s <= 100, f"garbage input broke range: {s}"

    _prop()


# --- _wire_dhw_tank_temp helper (coordinator wiring) ----------------------


def test_wire_dhw_tank_temp_populates_record():
    """Helper attaches tank temp to DHW record when present."""
    from custom_components.daikin_cycle_ml.coordinator import (
        _wire_dhw_tank_temp,
    )

    rec = {"mode": "dhw", "buh_used": 1}
    attrs = {"DHW tank temp. (R5T)": 65.0}
    _wire_dhw_tank_temp(rec, attrs)
    assert rec["dhw_tank_temp"] == 65.0


def test_wire_dhw_tank_temp_missing_attr_skips():
    """Helper skips DHW record when tank sensor absent."""
    from custom_components.daikin_cycle_ml.coordinator import (
        _wire_dhw_tank_temp,
    )

    rec = {"mode": "dhw", "buh_used": 1}
    _wire_dhw_tank_temp(rec, {})
    assert "dhw_tank_temp" not in rec


def test_wire_dhw_tank_temp_heating_ignored():
    """Helper never touches non-DHW records."""
    from custom_components.daikin_cycle_ml.coordinator import (
        _wire_dhw_tank_temp,
    )

    rec = {"mode": "heating", "buh_used": 1}
    attrs = {"DHW tank temp. (R5T)": 65.0}
    _wire_dhw_tank_temp(rec, attrs)
    assert "dhw_tank_temp" not in rec


def test_wire_dhw_tank_temp_disconnected_probe_skips():
    """Helper skips disconnected R5T probe (-40.7°C sentinel)."""
    from custom_components.daikin_cycle_ml.coordinator import (
        _wire_dhw_tank_temp,
    )

    rec = {"mode": "dhw", "buh_used": 1}
    attrs = {"DHW tank temp. (R5T)": -40.7}
    _wire_dhw_tank_temp(rec, attrs)
    assert "dhw_tank_temp" not in rec
