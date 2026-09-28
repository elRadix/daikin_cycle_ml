"""COV-8B: coordinator + remaining module edges.

Marker: COV8B
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _find_fn(mod, marker):
    for name in dir(mod):
        obj = getattr(mod, name)
        if not inspect.isfunction(obj):
            continue
        try:
            src = inspect.getsource(obj)
        except Exception:
            continue
        if marker in src:
            return obj
    return None


def test_cov8b_cop_analyzer_skip_dhw_mode():
    from custom_components.daikin_cycle_ml.engine import cop_analyzer as m
    fn = _find_fn(m, "for s in samples:")
    assert fn is not None, "helper not found"
    # heating sample -> False branch of mode check (kept)
    s1 = m.CopSample(cop=3.0, lwt=35.0, outdoor=5.0,
                     flow_lmin=10.0, power_stable=True,
                     mode="heating", ts=1000.0)
    # dhw sample -> True branch (continue)
    s2 = m.CopSample(cop=2.5, lwt=45.0, outdoor=5.0,
                     flow_lmin=10.0, power_stable=True,
                     mode="dhw", ts=2000.0)
    result = fn([s1, s2])
    assert isinstance(result, dict)


def test_cov8b_cycle_detector_accumulate_no_rps():
    from custom_components.daikin_cycle_ml.engine.cycle_detector import (
        CycleDetector,
    )
    d = CycleDetector.__new__(CycleDetector)
    d._rps_samples = []
    d._dt_samples = []
    d._outdoor_samples = []
    d._lwt_samples = []
    d._accumulate({})
    assert d._rps_samples == []


async def test_cov8b_setup_baseline_persistence_no_db():
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = None
    c._baseline_save_unsub = MagicMock()
    c.async_load_adaptive_state = AsyncMock(return_value=None)
    await c.async_setup_baseline_persistence()


def test_cov8b_accumulate_cycle_samples_indoor_no_state():
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.detector = SimpleNamespace(state="active")
    c.indoor_temp_entity = "sensor.indoor"
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    c._cycle_lwt_sum = 0.0
    c._cycle_lwt_count = 0
    c._cycle_indoor_sum = 0.0
    c._cycle_indoor_count = 0
    c._accumulate_cycle_samples({})


async def test_cov8b_collect_cycle_averages_no_avg_cop_attr():
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock(spec=[])
    c._cycle_lwt_sum = 0.0
    c._cycle_lwt_count = 0
    c._cycle_indoor_sum = 0.0
    c._cycle_indoor_count = 0
    record = {"start_ts": 100.0, "end_ts": 200.0}
    result = await c._collect_cycle_averages(record)
    assert isinstance(result, tuple) and len(result) == 3


def test_cov8b_build_alert_context_no_duration():
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {}
    c._setpoint_history = []
    c.store = MagicMock()
    c.store.cycles_in_window = MagicMock(return_value=0)
    c.store.cycles_today = MagicMock(return_value=[])
    c.store.last_cycle = MagicMock(return_value=None)
    c.store.off_time_since_last = MagicMock(return_value=None)
    c._setpoint_current = MagicMock(return_value=None)
    c._setpoint_target = MagicMock(return_value=None)
    c._setpoint_delta = MagicMock(return_value=None)
    c._snap_attr = MagicMock(return_value=None)
    c._avg_duration_min = MagicMock(return_value=None)
    snap = SimpleNamespace(last_record={"mode": "heating"}, advice=[])
    result = c._build_alert_context(snap)
    assert "short_run" in result


async def test_cov8b_diag_empty_stooklijn_cache():
    from custom_components.daikin_cycle_ml import diagnostics as diag
    fn = _find_fn(diag, "_stooklijn_cache")
    assert fn is not None, "diag helper not found"
    coord = SimpleNamespace(
        _stooklijn_cache={},
        _cop_today_cache={},
        db=None,
    )
    sig = inspect.signature(fn)
    args = []
    for pname, p in sig.parameters.items():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if pname in ("coord", "coordinator"):
            args.append(coord)
        elif pname == "options":
            args.append({})
        else:
            args.append(None)
    if inspect.iscoroutinefunction(fn):
        await fn(*args)
    else:
        fn(*args)


async def test_cov8b_diag_no_counters_snapshot():
    from custom_components.daikin_cycle_ml import diagnostics as diag
    fn = _find_fn(diag, "counters_snapshot")
    assert fn is not None, "diag helper not found"
    store = SimpleNamespace()
    snap = SimpleNamespace(attrs={})
    coord = SimpleNamespace(store=store, db=None)
    sig = inspect.signature(fn)
    args = []
    for pname, p in sig.parameters.items():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if pname in ("coord", "coordinator"):
            args.append(coord)
        elif pname == "store":
            args.append(store)
        elif pname == "snap":
            args.append(snap)
        else:
            args.append(None)
    if inspect.iscoroutinefunction(fn):
        await fn(*args)
    else:
        fn(*args)
