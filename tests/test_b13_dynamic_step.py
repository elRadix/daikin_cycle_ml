"""B13 dynamic LWT step + setpoint check + comfort dual-loop."""
from __future__ import annotations

import asyncio
import time

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample,
    StooklijnAdvies,
    analyze_stooklijn,
)


def _mk_settled(n_hist, lwt_hist, lwt_recent, cop=3.0, outdoor=8.0):
    now = time.time()
    samples = [
        CopSample(
            cop=cop, lwt=lwt_hist, outdoor=outdoor, flow_lmin=10.0,
            defrost=False, data_quality="Good", power_stable=True,
            mode="heating", ts=now - (n_hist + 1 - i) * 300,
        )
        for i in range(n_hist)
    ]
    samples.append(
        CopSample(
            cop=cop, lwt=lwt_recent, outdoor=outdoor, flow_lmin=10.0,
            defrost=False, data_quality="Good", power_stable=True,
            mode="heating", ts=now - 30,
        )
    )
    return samples


def _call(samples, setpoint_lwt, indoor=20.5, comfort_min=20.0,
          comfort_max=24.0, rt_setpoint=20.0):
    return analyze_stooklijn(
        samples, comfort_min=comfort_min, indoor_avg=indoor,
        setpoint_lwt=setpoint_lwt, comfort_max=comfort_max,
        rt_setpoint=rt_setpoint,
    )


def test_legacy_no_setpoint_keep():
    a = analyze_stooklijn(_mk_settled(12, 35.0, 35.0))
    assert a.state == "keep"
    assert a.setpoint_lwt is None


def test_legacy_no_setpoint_lower():
    a = analyze_stooklijn(_mk_settled(12, 35.0, 37.0))
    assert a.state == "lower_lwt"
    assert a.step_c == 2
    assert a.delta_c == -2.0


def test_scenario_A_deadband():
    a = _call(_mk_settled(11, 34.2, 35.0), setpoint_lwt=35.0, indoor=20.1)
    assert a.state == "keep"
    assert a.reason == "within_deadband"


def test_scenario_B_lower_2C():
    a = _call(_mk_settled(11, 33.0, 34.6), setpoint_lwt=35.0, indoor=20.5)
    assert a.state == "lower_lwt"
    assert a.step_c == 2
    assert a.delta_c == -2.0
    assert a.doel_setpoint == 33.0


def test_scenario_C_capped_3():
    a = _call(_mk_settled(11, 30.0, 39.0), setpoint_lwt=40.0, indoor=20.5)
    assert a.state == "lower_lwt"
    assert a.step_c == 3
    assert a.delta_c == -3.0


def test_scenario_D_comfort_floor():
    a = _call(_mk_settled(11, 30.0, 40.0), setpoint_lwt=40.0,
              indoor=19.3, comfort_min=20.0)
    assert a.state == "keep"
    assert a.reason == "comfort_floor_reached"


def test_scenario_E_raise():
    a = _call(_mk_settled(11, 32.0, 26.5), setpoint_lwt=27.0, indoor=20.5)
    assert a.state == "raise_lwt"
    assert a.delta_c > 0
    assert a.doel_setpoint is not None
    assert a.doel_setpoint > 27.0


def test_scenario_F_tracking_dampening():
    a = _call(_mk_settled(11, 33.0, 28.6), setpoint_lwt=35.0, indoor=20.5)
    assert a.tracking_error is not None
    assert abs(a.tracking_error) > 1.5
    assert a.step_c <= 1


def test_comfort_ceiling_raise():
    a = _call(_mk_settled(11, 30.0, 26.0), setpoint_lwt=26.0,
              indoor=24.5, comfort_max=24.0)
    assert a.state == "keep"
    assert a.reason == "comfort_ceiling_reached"


def test_no_indoor_sensor():
    a = analyze_stooklijn(
        _mk_settled(11, 33.0, 34.6),
        comfort_min=20.0, indoor_avg=None, setpoint_lwt=35.0,
        comfort_max=24.0, rt_setpoint=20.0,
    )
    assert a.state == "keep"
    assert a.reason == "no_indoor_sensor"


def test_reason_unit_tracking_behind():
    a = _call(_mk_settled(11, 33.0, 30.0), setpoint_lwt=34.0, indoor=20.5)
    assert a.state == "keep"
    assert a.reason == "unit_tracking_behind"
    assert a.step_c == 0


def test_reason_low_confidence():
    a = _call(_mk_settled(4, 33.0, 33.0), setpoint_lwt=34.0, indoor=20.5)
    assert a.state == "keep"
    assert a.reason == "low_confidence"
    assert a.step_c == 0


def test_state_set_canonical_english():
    valid = {"unknown", "no_data", "keep", "lower_lwt", "raise_lwt"}
    a = analyze_stooklijn([])
    assert a.state in valid


def test_dataclass_defaults():
    a = StooklijnAdvies()
    assert a.state == "unknown"
    assert a.step_c == 0
    assert a.delta_c == 0.0
    assert a.comfort_cap == 3.0
    assert a.urgency == 0.0


def test_delta_matches_step_and_direction():
    for sp, hist, recent, ind in [
        (35.0, 33.0, 34.6, 20.5),
        (27.0, 32.0, 26.5, 20.5),
    ]:
        a = _call(_mk_settled(11, hist, recent), setpoint_lwt=sp, indoor=ind)
        if a.state == "lower_lwt":
            assert a.delta_c == -a.step_c
        elif a.state == "raise_lwt":
            assert a.delta_c == a.step_c
        else:
            assert a.delta_c == 0.0


def test_doel_setpoint_equals_setpoint_plus_delta():
    a = _call(_mk_settled(11, 33.0, 34.6), setpoint_lwt=35.0, indoor=20.5)
    if a.state in ("lower_lwt", "raise_lwt"):
        assert a.doel_setpoint is not None
        assert abs(a.doel_setpoint - (35.0 + a.delta_c)) < 0.01


def test_comfort_impact_physics():
    a = _call(_mk_settled(11, 33.0, 34.6), setpoint_lwt=35.0, indoor=20.5)
    if a.state == "lower_lwt":
        assert abs(a.comfort_impact - (a.delta_c * 0.20)) < 0.01


def test_urgency_is_raw_cop_gap():
    a = _call(_mk_settled(11, 30.0, 39.0), setpoint_lwt=40.0, indoor=20.5)
    assert a.urgency == 1.0


def test_all_dhw_no_heating_returns_no_data():
    now = time.time()
    s = [
        CopSample(
            cop=3.0, lwt=45.0, outdoor=8.0, flow_lmin=10.0,
            defrost=False, data_quality="Good", power_stable=True,
            mode="dhw", ts=now - i * 60,
        )
        for i in range(5)
    ]
    a = analyze_stooklijn(s, setpoint_lwt=45.0, indoor_avg=20.5)
    assert a.state == "no_data"
    assert a.reason == "no_recent_heating"


def test_i18n_dicts_symmetric():
    from custom_components.daikin_cycle_ml.const import (
        STOOKLIJN_STATE_LABEL_EN,
        STOOKLIJN_STATE_LABEL_NL,
    )
    assert set(STOOKLIJN_STATE_LABEL_EN.keys()) == set(STOOKLIJN_STATE_LABEL_NL.keys())
    for k in STOOKLIJN_STATE_LABEL_EN:
        en = STOOKLIJN_STATE_LABEL_EN[k]
        nl = STOOKLIJN_STATE_LABEL_NL[k]
        assert ("{step}" in en) == ("{step}" in nl), k


def test_state_label_helpers():
    from custom_components.daikin_cycle_ml.sensor import _state_label
    assert _state_label("lower_lwt", 2, "en") == "Lower LWT by 2 \u00b0C"
    assert _state_label("lower_lwt", 2, "nl") == "Verlaag LWT met 2 \u00b0C"
    assert _state_label("keep", 0, "en") == "Keep current LWT"
    assert _state_label("no_such_state", 0, "en") == "no_such_state"
    assert _state_label("keep", 0, "fr") == "Keep current LWT"
    assert _state_label("behoud", 0, "en") == "Keep current LWT"
    assert _state_label("verlaag_lwt_2c", 0, "en") == "Lower LWT by 2 \u00b0C"
    assert _state_label("geen_data", 0, "en") == "No data"


def test_state_label_format_exception(monkeypatch):
    from custom_components.daikin_cycle_ml import const as _c
    from custom_components.daikin_cycle_ml.sensor import _state_label
    monkeypatch.setitem(
        _c.STOOKLIJN_STATE_LABEL_EN, "_b13_bad", "Value {unknown}"
    )
    assert _state_label("_b13_bad", 0, "en") == "Value {unknown}"


def test_attrs_stooklijn_normal():
    from custom_components.daikin_cycle_ml.sensor import _attrs_stooklijn

    class _C:
        options = {"notification_language": "nl"}

    snap = type("S", (), {"stooklijn_advies": {
        "state": "lower_lwt", "step_c": 2, "setpoint_lwt": 35.0,
        "doel_setpoint": 33.0,
    }})()
    out = _attrs_stooklijn(snap, _C())
    assert out["state_label"] == "Verlaag LWT met 2 \u00b0C"
    assert out["step_c"] == 2
    assert out["huidige_setpoint"] == 35.0
    assert out["doel_setpoint"] == 33.0


def test_attrs_stooklijn_options_exception():
    from custom_components.daikin_cycle_ml.sensor import _attrs_stooklijn

    class _BrokenOpts:
        def __bool__(self):
            return True

        def get(self, k, d=None):
            raise RuntimeError("boom")

    class _C:
        options = _BrokenOpts()

    snap = type("S", (), {"stooklijn_advies": {"state": "keep"}})()
    out = _attrs_stooklijn(snap, _C())
    assert out["state_label"] == "Keep current LWT"


def test_attrs_stooklijn_empty_advies():
    from custom_components.daikin_cycle_ml.sensor import _attrs_stooklijn

    class _C:
        options = {}

    snap = type("S", (), {"stooklijn_advies": None})()
    out = _attrs_stooklijn(snap, _C())
    assert out["state_label"] == "Unknown"


def test_status_report_step_formatting():
    from custom_components.daikin_cycle_ml.engine.status_report import (
        build_stooklijn_report,
    )
    cache = {"state": "lower_lwt", "step_c": 2, "besparing_cop_pct": 4.0,
             "comfort_impact": -0.4, "betrouwbaarheid": 0.9, "samples": 12}
    msg = build_stooklijn_report(cache, language="en", emoji_enabled=False)
    assert "Lower LWT by 2" in msg


def test_status_report_legacy_state_still_works():
    from custom_components.daikin_cycle_ml.engine.status_report import (
        build_stooklijn_report,
    )
    msg = build_stooklijn_report({"state": "verlaag_lwt_2c"},
                                 language="en", emoji_enabled=False)
    assert "Lower LWT by 2" in msg


def test_status_report_step_format_exception(monkeypatch):
    from custom_components.daikin_cycle_ml import const as _c
    from custom_components.daikin_cycle_ml.engine.status_report import (
        build_stooklijn_report,
    )
    monkeypatch.setitem(_c.STOOKLIJN_STATE_LABEL_EN, "_b13_bad", "X {unknown}")
    msg = build_stooklijn_report({"state": "_b13_bad"},
                                 language="en", emoji_enabled=False)
    assert "X {unknown}" in msg


def test_status_report_step_bad_int():
    from custom_components.daikin_cycle_ml.engine.status_report import (
        build_stooklijn_report,
    )
    msg = build_stooklijn_report(
        {"state": "lower_lwt", "step_c": "not_an_int"},
        language="en", emoji_enabled=False,
    )
    assert "Lower LWT by 0" in msg


def _mk_coord_b13(attrs=None, indoor_entity=None, indoor_state=None,
                  cop_rows=None):
    from unittest.mock import AsyncMock, MagicMock
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {}
    c._stooklijn_cache = {}
    c._stooklijn_cache_ts = 0.0
    c.data = type("S", (), {"mode": "heating", "attrs": attrs or {}})()
    c.indoor_temp_entity = indoor_entity
    c.hass = MagicMock()
    if indoor_state is not None:
        st = MagicMock()
        st.state = indoor_state
        c.hass.states.get = MagicMock(return_value=st)
    else:
        c.hass.states.get = MagicMock(return_value=None)
    if cop_rows is not None:
        c.db = MagicMock()
        c.db.async_fetch_cop_samples = AsyncMock(return_value=cop_rows)
    else:
        c.db = None
    return c


def test_coord_setpoint_and_indoor_extracted():
    from custom_components.daikin_cycle_ml.const import ATTR_LW_SETPOINT
    now = time.time()
    rows = [
        {"cop": 3.0, "lwt": 33.0, "outdoor": 8.0, "flow_lmin": 10.0,
         "power_stable": True, "mode": "heating", "ts": now - i * 60}
        for i in range(12)
    ]
    c = _mk_coord_b13(
        attrs={ATTR_LW_SETPOINT: 35.0},
        indoor_entity="sensor.indoor",
        indoor_state="20.5",
        cop_rows=rows,
    )
    asyncio.run(c._maybe_refresh_stooklijn(now, force=True))
    assert c._stooklijn_cache.get("setpoint_lwt") == 35.0


def test_coord_indoor_exception_branch():
    from custom_components.daikin_cycle_ml.const import ATTR_LW_SETPOINT
    now = time.time()
    rows = [
        {"cop": 3.0, "lwt": 33.0, "outdoor": 8.0, "flow_lmin": 10.0,
         "power_stable": True, "mode": "heating", "ts": now - i * 60}
        for i in range(12)
    ]
    c = _mk_coord_b13(
        attrs={ATTR_LW_SETPOINT: 35.0},
        indoor_entity="sensor.indoor",
        indoor_state="not_a_number",
        cop_rows=rows,
    )
    asyncio.run(c._maybe_refresh_stooklijn(now, force=True))
    assert c._stooklijn_cache.get("reason") == "no_indoor_sensor"


def test_coord_no_attrs_no_indoor():
    now = time.time()
    rows = [
        {"cop": 3.0, "lwt": 33.0, "outdoor": 8.0, "flow_lmin": 10.0,
         "power_stable": True, "mode": "heating", "ts": now - i * 60}
        for i in range(12)
    ]
    c = _mk_coord_b13(attrs=None, cop_rows=rows)
    asyncio.run(c._maybe_refresh_stooklijn(now, force=True))
    assert c._stooklijn_cache.get("setpoint_lwt") is None


def test_coord_setpoint_bad_type():
    from custom_components.daikin_cycle_ml.const import ATTR_LW_SETPOINT
    now = time.time()
    rows = [
        {"cop": 3.0, "lwt": 33.0, "outdoor": 8.0, "flow_lmin": 10.0,
         "power_stable": True, "mode": "heating", "ts": now - i * 60}
        for i in range(12)
    ]
    c = _mk_coord_b13(
        attrs={ATTR_LW_SETPOINT: "not_numeric"},
        cop_rows=rows,
    )
    asyncio.run(c._maybe_refresh_stooklijn(now, force=True))
    assert c._stooklijn_cache.get("setpoint_lwt") is None


def test_coord_indoor_state_unavailable():
    from custom_components.daikin_cycle_ml.const import ATTR_LW_SETPOINT
    now = time.time()
    rows = [
        {"cop": 3.0, "lwt": 33.0, "outdoor": 8.0, "flow_lmin": 10.0,
         "power_stable": True, "mode": "heating", "ts": now - i * 60}
        for i in range(12)
    ]
    c = _mk_coord_b13(
        attrs={ATTR_LW_SETPOINT: 35.0},
        indoor_entity="sensor.indoor",
        indoor_state="unavailable",
        cop_rows=rows,
    )
    asyncio.run(c._maybe_refresh_stooklijn(now, force=True))
    assert c._stooklijn_cache.get("reason") == "no_indoor_sensor"


def test_coord_indoor_states_get_none():
    from custom_components.daikin_cycle_ml.const import ATTR_LW_SETPOINT
    now = time.time()
    rows = [
        {"cop": 3.0, "lwt": 33.0, "outdoor": 8.0, "flow_lmin": 10.0,
         "power_stable": True, "mode": "heating", "ts": now - i * 60}
        for i in range(12)
    ]
    c = _mk_coord_b13(
        attrs={ATTR_LW_SETPOINT: 35.0},
        indoor_entity="sensor.indoor",
        indoor_state=None,
        cop_rows=rows,
    )
    asyncio.run(c._maybe_refresh_stooklijn(now, force=True))
    assert c._stooklijn_cache.get("reason") == "no_indoor_sensor"
