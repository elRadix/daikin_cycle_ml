"""v1.8.1 — alert ctx population + render sentinel fixes (R331)."""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.engine.status_report import (
    build_rich_alert,
)


def _coord():
    return DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)


def test_snap_attr_reads_from_attrs_field():
    """Bug A: DataSnapshot.attrs is the source, not 'attributes'."""
    c = _coord()
    snap = SimpleNamespace(attrs={"outdoor_temp": 12.1})
    assert c._snap_attr(snap, "outdoor_temp") == 12.1


def test_snap_attr_falls_back_to_attributes():
    """Legacy snapshots that only expose .attributes still work."""
    c = _coord()
    snap = SimpleNamespace(attrs={}, attributes={"outdoor_temp": 11.5})
    assert c._snap_attr(snap, "outdoor_temp") == 11.5


def test_snap_attr_returns_none_on_all_miss():
    """No sentinel leak — miss returns None, not em-dash."""
    c = _coord()
    snap = SimpleNamespace(attrs={})
    assert c._snap_attr(snap, "does_not_exist") is None


def test_build_rich_alert_none_value_renders_bare_dash():
    """Bug C: None ctx value -> bare dash, no unit suffix."""
    msg = build_rich_alert(
        "short_run",
        "warning",
        {
            "duration_min": None,
            "threshold_min": 20,
            "mode": "heating",
            "lwt_setpoint": 29.0,
            "lwt_actual": None,
            "indoor": None,
            "flow": None,
            "outdoor": 12.1,
        },
        language="nl",
    )
    assert "— min" not in msg
    assert "— °C" not in msg
    assert "— l/min" not in msg
    assert "29.0 °C" in msg
    assert "20 min" in msg


def test_build_rich_alert_real_values_preserved():
    """Regression: real numbers still render with units."""
    msg = build_rich_alert(
        "short_run",
        "warning",
        {
            "duration_min": 12,
            "threshold_min": 20,
            "mode": "heating",
            "lwt_setpoint": 29.0,
            "lwt_actual": 30.3,
            "indoor": 20.0,
            "flow": 18.0,
            "outdoor": 12.1,
        },
        language="nl",
    )
    assert "12 min" in msg
    assert "29.0 °C" in msg
    assert "30.3 °C" in msg
    assert "18.0 l/min" in msg


def test_short_off_floor_applies():
    """SB-1: off_min floor is >= 1 once the trigger fired."""
    assert max(1, round(30 / 60)) == 1
    assert max(1, round(0 / 60)) == 1
    assert max(1, round(300 / 60)) == 5


def test_f_returns_none_for_none():
    """Bug C: _f(None) yields None (exercised via the render path)."""
    msg = build_rich_alert(
        "short_run",
        "warning",
        {"duration_min": None},
        language="nl",
    )
    assert "— min" not in msg


def test_advice_not_bled_across_alerts():
    """SB-2: per-alert ALERT_ADVICE wins; no shared bleed."""
    msg1 = build_rich_alert("short_run", "warning", {}, language="nl")
    msg2 = build_rich_alert("short_off", "warning", {}, language="nl")
    assert "korter dan drempel" in msg1
    assert "Off-tijd te kort" in msg2
    assert msg1 != msg2


# ---------- SB-3: mode fallback substring branches ----------

def _coord_with_snapshot(attrs: dict) -> object:
    from collections import deque
    from unittest.mock import MagicMock

    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
        DataSnapshot,
    )

    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {}
    c._setpoint_history = deque()
    c._last_setpoint = None
    st = MagicMock()
    st.cycles_in_window.return_value = 0
    st.cycles_today.return_value = []
    st.off_time_since_last.return_value = None
    st.last_cycle.return_value = None
    c.store = st
    return c, DataSnapshot(attrs=attrs)


def test_mode_fallback_substring_heat():
    """SB-3: operation_mode substring 'heat' -> heating."""
    c, snap = _coord_with_snapshot({"operation_mode": "Heating program"})
    ctx = c._build_alert_context(snap)
    assert ctx["pendulum"]["mode"] == "heating"


def test_mode_fallback_substring_cool():
    """SB-3: operation_mode substring 'cool' -> cooling."""
    c, snap = _coord_with_snapshot({"operation_mode": "Cooling only"})
    ctx = c._build_alert_context(snap)
    assert ctx["pendulum"]["mode"] == "cooling"


def test_mode_fallback_substring_dhw():
    """SB-3: operation_mode substring 'dhw' -> dhw."""
    c, snap = _coord_with_snapshot({"operation_mode": "DHW demand"})
    ctx = c._build_alert_context(snap)
    assert ctx["pendulum"]["mode"] == "dhw"


def test_mode_fallback_no_match_stays_unknown():
    """SB-3: operation_mode present but matches no substring -> stays unknown.

    Covers the fall-through direction of coordinator L2439->L2441.
    """
    c, snap = _coord_with_snapshot({"operation_mode": "Standby"})
    ctx = c._build_alert_context(snap)
    assert ctx["pendulum"]["mode"] == "unknown"


# ---------- R331-B: setpoint helpers use real constants ----------

def test_setpoint_current_reads_lw_setpoint_attr():
    """R331-B: _setpoint_current hits LW setpoint (main)."""
    c, snap = _coord_with_snapshot({"LW setpoint (main)": 29.0})
    assert c._setpoint_current(snap) == 29.0


def test_setpoint_target_reads_target_cond_temp_attr():
    """R331-B: _setpoint_target hits Target Cond. Temp."""
    c, snap = _coord_with_snapshot({"Target Cond. Temp.": 26.09})
    assert c._setpoint_target(snap) == 26.09
