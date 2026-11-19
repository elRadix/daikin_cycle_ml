"""#423: data correctness + polish from the prod-1 analysis (2026-11-19)."""
from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import PERSIST_TICK_BUDGET_S
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    _alias_copies,
)
from custom_components.daikin_cycle_ml.engine import notification_engine as ne
from custom_components.daikin_cycle_ml.engine.attribute_reader import (
    _normalize,
    is_numeric_key,
    read,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import _compute_dt
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
    resolve_attrs,
)
from custom_components.daikin_cycle_ml.engine.runtime_source import (
    read_native_defrost_count,
)
from custom_components.daikin_cycle_ml.sensor import _attrs_learned, _value_learned
from tests.test_369_hybrid_cop_floor import _make_coord_for_gate, _mk_db
from tools import parse_espaltherma_catalog as tool

R1T = "Leaving water temp. before BUH (R1T)"
R2T = "Leaving water temp. after BUH (R2T)"
R4T = "Inlet water temp.(R4T)"

# --- 1. "0" / "1" stay numbers for numeric attributes --------------------------------


@pytest.mark.parametrize("key,raw,expected", [
    ("Stats: Defrosts today", "1", 1.0),
    ("Stats: Compressor starts today", " 0", 0.0),
    ("Unit meter: Compressor starts", "1", 1.0),
    ("Flow sensor (l/min)", "0", 0.0),
    ("INV frequency (rps)", "1", 1.0),
    ("BUH Step1", "1", True),                 # on/off stays bool
    ("Defrost Operation", "0", False),
    ("Stats: COP estimated", "ON", True),     # not a number: unchanged path
    (None, "1", True),
])
def test_normalize_numeric_first(key, raw, expected):
    assert _normalize(raw, key) == expected
    assert type(_normalize(raw, key)) is type(expected)


def test_is_numeric_key():
    assert is_numeric_key("Stats: Anything") and is_numeric_key("Flow sensor (l/min)")
    assert not is_numeric_key("BUH Step1") and not is_numeric_key(None)


def test_monolithic_read_keeps_counter_one():
    st = SimpleNamespace(attributes={"Stats: Defrosts today": "1", "BUH Step1": "1"})
    attrs = read(st)
    assert read_native_defrost_count(attrs) == 1.0       # was None (True rejected)
    assert attrs["BUH Step1"] is True


async def test_v2_entity_state_one_is_a_number(hass):
    hass.states.async_set("sensor.espaltherma_stats_heat_output_kw", "1")
    hass.states.async_set("sensor.espaltherma_buh_step1", "1")
    res = resolve_attrs(hass)
    assert res.attrs["Stats: Heat output (kW)"] == 1.0
    assert res.attrs["BUH Step1"] is True


# --- 3. dT and curve LWT from R1T ----------------------------------------------------


def test_dt_uses_r1t_before_buh():
    # BUH running: R2T 35.5 (BUH heat) vs R1T 31.0, inlet 29.0
    assert _compute_dt({R1T: 31.0, R2T: 35.5, R4T: 29.0}) == 2.0
    assert _compute_dt({R2T: 35.5, R4T: 29.0}) == 6.5       # no R1T: fallback
    assert _compute_dt({R4T: 29.0}) is None


async def _stored_lwt(tmp_path, monkeypatch, view: dict[str, Any]) -> float:
    db = await _mk_db(tmp_path)
    try:
        c = _make_coord_for_gate(db)
        st = MagicMock()
        st.state = "4.5"
        st.attributes = {}
        c.hass.states.get.return_value = st
        import custom_components.daikin_cycle_ml.coordinator as coord_mod
        monkeypatch.setattr(coord_mod, "build_compat_view", lambda a: dict(view))
        c._resolve_cop_sample_mode = lambda: "heating"
        await c._maybe_collect_cop_sample(time.time())
        async with db._conn.execute("SELECT lwt FROM cop_samples") as cur:
            return float((await cur.fetchone())[0])
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


BASE = {R4T: 29.0, "Outdoor air temp.(R1T)": 9.6, "Flow sensor (l/min)": 18.0,
        "Defrost Operation": False}


async def test_cop_sample_lwt_prefers_r1t(tmp_path, monkeypatch):
    assert await _stored_lwt(tmp_path, monkeypatch, {**BASE, R1T: 31.0, R2T: 35.5}) == 31.0


async def test_cop_sample_lwt_falls_back_to_r2t(tmp_path, monkeypatch):
    assert await _stored_lwt(tmp_path, monkeypatch, {**BASE, R2T: 35.5}) == 35.5


# --- 5. learned_thresholds shows the value in use -------------------------------------


class _Adaptive:
    def __init__(self, learned: Any) -> None:
        self.learned = learned

    def learn_short_run_min(self, mode: Any) -> Any:
        if isinstance(self.learned, Exception):
            raise self.learned
        return self.learned

    def learn_good_off_min(self, mode: Any) -> int:
        return 20

    def learn_target_cycles_per_day(self) -> int:
        return 4


def _lc(effective: Any, learned: Any) -> SimpleNamespace:
    def eff(key: str, default: int) -> Any:
        if isinstance(effective, Exception):
            raise effective
        return effective

    return SimpleNamespace(
        adaptive=_Adaptive(learned), options={"adaptive_thresholds_enabled": True},
        _resolve_adaptive_mode=lambda: "heating", _effective_threshold=eff,
    )


def test_learned_state_is_value_in_use():
    c = _lc(10, 2)                                       # prod-1: learned 2, used 10
    assert _value_learned(None, c) == 10                 # type: ignore[arg-type]
    attrs = _attrs_learned(None, c)                      # type: ignore[arg-type]
    assert attrs["short_run_learned_min"] == 2 and attrs["short_run_effective_min"] == 10


def test_learned_errors():
    c = _lc(RuntimeError("x"), RuntimeError("y"))
    assert _value_learned(None, c) is None               # type: ignore[arg-type]
    assert _attrs_learned(None, c)["short_run_learned_min"] is None  # type: ignore[arg-type]


# --- 6. log on change only -----------------------------------------------------------


def test_aggregation_suppression_logged_once(caplog):
    ne._SUPPRESS_LOGGED.clear()
    now = time.time()
    states = {"cop_vs_datasheet_low": True}
    last = {"cop_vs_datasheet_low": now - 60}
    with caplog.at_level(logging.DEBUG, logger=ne.__name__):
        for i in range(5):
            ne.evaluate_alerts(states, {}, now + i * 30, last)
    assert sum("suppressing cop_vs_datasheet_low" in r.message for r in caplog.records) == 1


async def test_datasheet_gate1_logged_on_change(caplog):
    c = object.__new__(DaikinCycleMLCoordinator)
    c.entry = MagicMock()
    c.entry.data = {"model": "epra12eav3"}
    c._datasheet_user_loaded = True
    c._datasheet_defaults = None
    c._datasheet_cache = {}
    c._datasheet_user = {}
    from custom_components.daikin_cycle_ml.engine.model_datasheets import load_bundled
    c._datasheet_merged = load_bundled()
    with caplog.at_level(logging.DEBUG):
        for _ in range(4):
            await c._refresh_datasheet_state(time.time(), 33.9, 9.6, None)
        await c._refresh_datasheet_state(time.time(), None, 9.6, None)
    hits = [r for r in caplog.records if "gate-1 null" in r.message]
    assert len(hits) == 2                                 # cop missing, then lwt too


# --- 7. diagnostics without alias copies ----------------------------------------------


def test_alias_copies():
    attrs = {"Operation Mode": "Heating", "Betriebsart": "Heating",
             "Mode de fonctionnement": "Heating",
             "Outdoor air temp.(R1T)": 9.6, "R1T-Outdoor air temp.": 9.6,
             "Defrost Operation": False, "Abtauung": True}
    out = _alias_copies(attrs)
    assert {"Betriebsart", "Mode de fonctionnement", "R1T-Outdoor air temp."} <= out
    assert "Abtauung" not in out                          # differs: a real value
    assert _alias_copies({"Betriebsart": "Heating"}) == frozenset()


# --- 8. catalog tool collects every HaSensor table -------------------------------------


def test_catalog_tool_reads_ha_tables(tmp_path):
    src = tmp_path / "esp"
    (src / "data").mkdir(parents=True)
    (src / "src").mkdir()
    (src / "data" / "catalog_names.txt").write_text("[M]\nA\n", encoding="utf-8")
    (src / "src" / "main.cpp").write_text(
        'static const HaSensor DIII_LABELS[] = {\n  {"E0: Leaving water (C)", 1},\n'
        '  {"RAM: Outdoor load (%)", -1, 105},\n};\n'
        'const HaSensor S[] = {{"Stats: Defrosts today", ESP_SENSOR_COUNT}};\n',
        encoding="utf-8",
    )
    assert tool.parse_extras(src) == [
        "E0: Leaving water (C)", "RAM: Outdoor load (%)", "Stats: Defrosts today"]


# --- 2. bounded accumulator write ---------------------------------------------------


def _persist_coord(delay: float) -> DaikinCycleMLCoordinator:
    c = object.__new__(DaikinCycleMLCoordinator)
    calls: list[float] = []

    async def slow(now: float) -> None:
        await asyncio.sleep(delay)
        calls.append(now)

    c._maybe_persist_accumulators = slow  # type: ignore[method-assign]
    c._calls = calls  # type: ignore[attr-defined]
    return c


async def test_slow_write_does_not_hold_the_tick(monkeypatch):
    import custom_components.daikin_cycle_ml.coordinator as coord_mod
    monkeypatch.setattr(coord_mod, "PERSIST_TICK_BUDGET_S", 0.05)
    c = _persist_coord(0.3)
    t0 = time.monotonic()
    await c._persist_accumulators_bounded(1.0)
    assert time.monotonic() - t0 < 0.25                  # tick continued
    await c._persist_accumulators_bounded(2.0)           # still pending: skipped
    await asyncio.sleep(0.4)
    assert c._calls == [1.0]                              # type: ignore[attr-defined]
    await c._persist_accumulators_bounded(3.0)
    await asyncio.sleep(0.4)
    assert c._calls == [1.0, 3.0]                         # type: ignore[attr-defined]


async def test_fast_write_completes_in_tick():
    c = _persist_coord(0.0)
    await c._persist_accumulators_bounded(5.0)
    assert c._calls == [5.0]                              # type: ignore[attr-defined]
    assert PERSIST_TICK_BUDGET_S == 2.0


async def test_flush_waits_for_pending_write():
    c = _persist_coord(0.1)
    done: list[str] = []

    async def mark(name: str) -> None:
        done.append(name)

    for n in ("_persist_runtime_acc", "_persist_energy_acc", "_persist_detector_state"):
        setattr(c, n, lambda n=n: mark(n))
    c._persist_task = asyncio.ensure_future(c._maybe_persist_accumulators(7.0))
    await c._async_flush_accumulators()
    assert c._calls == [7.0] and len(done) == 3          # type: ignore[attr-defined]

    async def boom() -> None:
        raise RuntimeError("x")

    c._persist_task = asyncio.ensure_future(boom())
    await c._async_flush_accumulators()                   # error swallowed
    assert len(done) == 6
