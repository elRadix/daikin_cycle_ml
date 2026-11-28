"""#515: prod-1 audit (EPRA12EAV3, v1.31.0), replayed on its diagnostics.

Fixture: tests/fixtures/diagnostics/epra12eav3_1_31_0_441e207ca5_202611281225.json
(the maintainer's prod install, 24/7 heating, backup-heater meter set).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml import sensor as s_mod
from custom_components.daikin_cycle_ml.const import ATTR_BUH_STEP1, DB_BUSY_MAX_SKIPS
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from tests.test_build_alert_context import _bare_coord, _default_store_mock
from tests.test_c5_coordinator_methods import _bare

FIX = Path(__file__).parent / "fixtures/diagnostics/epra12eav3_1_31_0_441e207ca5_202611281225.json"
DOC = json.loads(FIX.read_text())
ENT = DOC["entities"]
OPTS = DOC["entry"]["options"]


def _attrs(key: str) -> dict:
    return ENT[f"sensor:{key}"]["attributes"]


# --- COP sensors: own mode only, no "unknown" bucket --------------------------

def _period_data(entity: str) -> dict:
    a = _attrs(entity)
    keys = ("n_hours", "n_samples", "cop_p10", "cop_p90", "cop_min", "cop_max", "by_mode")
    return {k: a[k] for k in keys if k in a}


def test_mode_sensors_hold_their_own_mode_only():
    month = _period_data("cop_mean_month")
    assert "unknown" in month["by_mode"]                         # the prod data
    snap = SimpleNamespace(cop_hourly_month=month, cop_hourly_day=_period_data("cop_mean_day"))
    for mode in ("heating", "dhw", "cooling"):
        out = s_mod._attrs_cop_hourly_mode(mode, "month")(snap, None)
        assert "by_mode" not in out and out["mode"] == mode
    heat = s_mod._attrs_cop_hourly_mode("heating", "month")(snap, None)
    assert (heat["n_samples"], heat["n_hours"]) == (6672, 662)
    assert s_mod._attrs_cop_hourly_mode("cooling", "day")(snap, None)["n_samples"] is None


def test_mean_sensor_drops_the_unknown_bucket_keeps_the_totals():
    snap = SimpleNamespace(cop_hourly_month=_period_data("cop_mean_month"))
    out = s_mod._attrs_cop_hourly("month")(snap, None)
    assert set(out["by_mode"]) == {"heating", "dhw"}
    assert out["n_samples"] == 7258                              # 6672 + 580 + 6 unknown


# --- backup-heater energy ------------------------------------------------------

def _buh_coord(meter: str | None, snap: dict) -> SimpleNamespace:
    return SimpleNamespace(
        entry=SimpleNamespace(data={"model": "epra12eav3"}), options=dict(OPTS),
        buh_power_sensor=meter, runtime_snapshot=snap,
    )


def test_buh_energy_uses_the_configured_step_power():
    a = _attrs("runtime_buh_today")
    assert (a["buh_energy_kwh_est"], a["buh_energy_source"]) == (3.693, "computed")   # 3 + 3 kW
    assert (OPTS["buh_step1_kw"], OPTS["buh_step2_kw"]) == (2, 3)
    c = _buh_coord(None, {})
    # 3707 s x 2 kW + 724 s x 3 kW
    assert s_mod._buh_energy_kwh_est(c, a["step1_s"], a["step2_s"]) == pytest.approx(2.663, abs=0.001)


def test_buh_energy_from_the_meter_when_set():
    a = _attrs("runtime_buh_today")
    snap = {"buh_step1_s": a["step1_s"], "buh_step2_s": a["step2_s"], "buh_meter_kwh": 2.4567}
    out = s_mod._buh_energy(_buh_coord(OPTS["buh_power_sensor_entity"], snap), snap, 3707, 724)
    assert out == {"buh_energy_kwh_est": 2.457, "buh_energy_source": "power_meter"}
    # no meter configured: the step estimate
    assert s_mod._buh_energy(_buh_coord(None, snap), snap, 3707, 724)["buh_energy_source"] == "computed"


def test_meter_power_is_summed_each_tick_and_survives_a_restart():
    c = _bare()
    c.buh_power_sensor = OPTS["buh_power_sensor_entity"]
    c._last_runtime_tick_ts = 1000.0
    c._last_buh_meter_w = 3000.0
    c._tick_buh_and_defrost({ATTR_BUH_STEP1: True}, 1030.0)      # 3 kW for 30 s
    assert c._buh_meter_kwh == pytest.approx(0.025)
    c._last_buh_meter_w = 0.0
    c._tick_buh_and_defrost({ATTR_BUH_STEP1: False}, 1060.0)
    assert c._buh_meter_kwh == pytest.approx(0.025)
    assert c.runtime_snapshot["buh_meter_kwh"] == pytest.approx(0.025)
    c.buh_power_sensor = None                                     # no meter: nothing summed
    c._last_buh_meter_w = 3000.0
    c._tick_buh_and_defrost({ATTR_BUH_STEP1: True}, 1090.0)
    assert c._buh_meter_kwh == pytest.approx(0.025)


# --- ml_anomaly: the mode of the run that was scored ----------------------------

def test_ml_anomaly_names_the_closed_runs_mode():
    # #515: a 918 min heating run closed by the switch to hot water was reported
    # as "Mode: DHW, Last run: 918 min"
    st = _default_store_mock()
    st.last_cycle.return_value = {"mode": "heating", "duration_s": 55080}
    c = _bare_coord(store=st)
    ctx = c._build_alert_context(DataSnapshot(mode="dhw"))
    assert ctx["ml_anomaly"]["mode"] == "heating"
    assert ctx["ml_anomaly"]["last_duration_min"] == 918
    # the live mode still names the other alerts
    assert ctx["short_cycling_pattern"]["mode"] == "dhw"
    st.last_cycle.return_value = {"mode": "unknown", "duration_s": 600}
    assert c._build_alert_context(DataSnapshot(mode="dhw"))["ml_anomaly"]["mode"] == "dhw"


# --- database refreshes wait for nobody ----------------------------------------

@pytest.mark.asyncio
async def test_refreshes_skip_while_the_accumulator_write_is_pending():
    timing = DOC["coordinator_timing"]
    assert timing["tick_duration_max_phases_ms"]["persist_acc"] > 1900       # the 2 s budget
    assert timing["tick_duration_max_phases_ms"]["cop_hourly"] > 3000        # waited behind it
    c = _bare()
    assert c._db_write_pending() is False                         # no write
    gate = asyncio.Event()
    c._persist_task = asyncio.ensure_future(gate.wait())
    assert [c._db_write_pending() for _ in range(DB_BUSY_MAX_SKIPS)] == [True] * DB_BUSY_MAX_SKIPS
    assert c._db_write_pending() is False                         # never stalls for good
    assert c._db_write_pending() is True
    gate.set()
    await c._persist_task
    assert c._db_write_pending() is False and c._db_busy_skips == 0


# --- the second install (ERLA11DAV3, monolithic, 3.8 days up) -------------------

FIX2 = Path(__file__).parent / "fixtures/diagnostics/erla11dav3_1_31_0_855f04b147_202611281233.json"
DOC2 = json.loads(FIX2.read_text())


def test_sample_rate_past_a_day_uses_the_24h_window():
    from custom_components.daikin_cycle_ml.diagnostics import _sampling_snapshot
    sm = DOC2["sampling"]
    assert sm["sample_rate_pct"] == 26.5 and sm["samples_last_24h"] == 2878       # reported
    assert DOC2["coordinator_timing"]["uptime_s"] > 86400
    c = SimpleNamespace(_samples_window_primed=True, _samples_last_24h=2878,
                        _samples_expected_since_start=10876, _samples_expected_24h=2880)
    out = _sampling_snapshot(c)
    assert out["samples_window"] == "24h" and out["sample_rate_pct"] == 99.9
    c._samples_window_primed, c._samples_last_24h, c._samples_expected_since_start = False, 406, 406
    assert _sampling_snapshot(c)["sample_rate_pct"] == 100.0


def test_sampling_window_primes_after_a_day(monkeypatch):
    import time as _t
    c = _bare()
    c._samples_window_primed = False
    c._uptime_start_monotonic = _t.monotonic() - 90000
    from collections import deque
    c._tick_timestamps = deque()
    c._record_tick_health()
    assert c._samples_window_primed is True


def test_cop_vs_datasheet_is_for_space_heating_only():
    a = DOC2["entities"]["sensor:cop_vs_datasheet_pct"]
    assert a["state"] == "-47.95" and DOC2["coordinator"]["mode"] == "dhw"     # reported
    snap = SimpleNamespace(state="running", mode="dhw", cop_vs_datasheet_pct=-47.95, datasheet={},
                           datasheet_model="erla11dav3", cop_normalized_a7w35=2.514, cop=2.02,
                           cop_datasheet_ref={})
    assert s_mod._value_cop_vs_datasheet_pct(snap, None) is None
    attrs = s_mod._attrs_cop_vs_datasheet_pct(snap, None)
    assert attrs["deviation_pct"] is None and attrs["band"] is None
    snap.mode = "heating"
    assert s_mod._value_cop_vs_datasheet_pct(snap, None) == -47.95
    assert s_mod._attrs_cop_vs_datasheet_pct(snap, None)["band"] == "critical"


def test_tick_budget_seen_on_the_second_install():
    ph = DOC2["coordinator_timing"]["tick_duration_max_phases_ms"]
    assert ph["cop_hourly"] > 10000 and "persist_acc" not in ph   # no write to wait for


@pytest.mark.asyncio
async def test_slow_refresh_goes_on_in_the_background(monkeypatch):
    import custom_components.daikin_cycle_ml.coordinator as cm
    monkeypatch.setattr(cm, "REFRESH_TICK_BUDGET_S", 0.05)
    c = _bare()
    c._persist_task = None
    calls: list[str] = []
    gate = asyncio.Event()

    def fn(name, slow=False):
        async def run(now):
            calls.append(name)
            if slow:
                await gate.wait()
        return run

    c._refresh_cop_today = fn("cop_today")
    c._maybe_refresh_stooklijn = fn("stooklijn")
    c._maybe_refresh_cop_hourly = fn("cop_hourly", slow=True)
    c._maybe_refresh_cop_degradation = fn("cop_degradation")
    c._maybe_refresh_spf = fn("spf")
    await asyncio.wait_for(c._refresh_db_views(1.0), 1.0)          # not held by cop_hourly
    assert calls == ["cop_today", "stooklijn", "cop_hourly", "cop_degradation", "spf"]
    await c._refresh_db_views(2.0)                                  # cop_hourly still running
    assert calls.count("cop_hourly") == 1 and calls.count("spf") == 2
    gate.set()
    await asyncio.sleep(0)
    await c._refresh_db_views(3.0)
    assert calls.count("cop_hourly") == 2


@pytest.mark.asyncio
async def test_db_busy_skips_every_refresh():
    c = _bare()
    gate = asyncio.Event()
    c._persist_task = asyncio.ensure_future(gate.wait())
    c._refresh_cop_today = None                                     # would fail if called
    await c._refresh_db_views(1.0)
    gate.set()
    await c._persist_task


@pytest.mark.asyncio
async def test_late_failure_is_logged_not_raised(monkeypatch, caplog):
    import custom_components.daikin_cycle_ml.coordinator as cm
    monkeypatch.setattr(cm, "REFRESH_TICK_BUDGET_S", 0.01)
    c = _bare()

    async def boom():
        await asyncio.sleep(0.05)
        raise RuntimeError("db gone")

    await c._bounded_refresh("x", boom())
    await asyncio.sleep(0.1)
    assert "background refresh failed: db gone" in caplog.text

    async def slow_ok():
        await asyncio.sleep(0.05)

    await c._bounded_refresh("y", slow_ok())
    await asyncio.sleep(0.1)
    task = c._refresh_tasks["y"]
    assert task.done() and task.exception() is None


# --- #514 install: the backup heater alone is not a compressor run ---------------

FIX3 = Path(__file__).parent / "fixtures/diagnostics/erga08evh7_1_31_0_1c75d1de16_202611261526.json"
DOC3 = json.loads(FIX3.read_text())


def test_backup_heater_on_the_power_meter_is_not_a_compressor_run():
    from custom_components.daikin_cycle_ml.const import ATTR_BUH_STEP1, ATTR_INV_FREQUENCY_RPS
    from custom_components.daikin_cycle_ml.engine.cycle_detector import detect_compressor_on
    last = DOC3["store"]["last_cycle"]
    # the reported "hot-water run": 2 min, compressor at 0 rps, backup heater on
    assert (last["duration_s"], last["rps_max"], last["buh_used"], last["mode"]) == (120, 0.0, True, "dhw")
    assert last["quality_penalties"]["short_run"] > 0
    opts = DOC3["entry"]["options"]                 # fallback_power_threshold_w 200
    heater = {ATTR_INV_FREQUENCY_RPS: 0, ATTR_BUH_STEP1: "ON"}
    assert detect_compressor_on(heater, opts, power_w=3100.0) is False
    # power still counts when the speed is unknown, or no heater explains it
    assert detect_compressor_on({ATTR_BUH_STEP1: "ON"}, opts, power_w=3100.0) is True
    assert detect_compressor_on({ATTR_INV_FREQUENCY_RPS: 0, ATTR_BUH_STEP1: "OFF"}, opts, power_w=900.0) is True
    assert detect_compressor_on({ATTR_INV_FREQUENCY_RPS: 18, ATTR_BUH_STEP1: "ON"}, opts, power_w=3500.0) is True
