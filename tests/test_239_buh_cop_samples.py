"""#239 item 4: COP samples taken while the backup heater runs.

The thermal side of a COP sample uses R1T, before the BUH (#423), but the
electrical side includes the BUH when a BUH power sensor is configured, so a
sample taken with the BUH on reads far too low for the heat pump. They were
stored without a flag and fed the heating-curve bands and the
COP-vs-datasheet window. Now every sample carries buh_active; the curve advice
reads only samples without the BUH, the datasheet window skips BUH ticks, and
the day / week / month means keep them (system COP, what is paid for).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    _buh_running,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB
from tests.test_218_evlq_hybrid import _cop_coord


@pytest.mark.parametrize(("s1", "s2", "on"), [("ON", "OFF", True), ("OFF", "ON", True), ("OFF", "OFF", False),
                                              (1, 0, True), (None, None, False)])
async def test_the_sample_carries_the_backup_heater_state(s1, s2, on):
    c = _cop_coord(state="running", boiler_active=False)
    c.data.attrs.update({k: v for k, v in (("BUH Step1", s1), ("BUH Step2", s2)) if v is not None})
    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)
    assert c.db.async_insert_cop_sample.await_args.args[0]["buh_active"] == int(on)


def test_buh_running_without_attributes():
    assert _buh_running(None) is False and _buh_running({}) is False


@pytest.fixture
async def db(tmp_path):
    d = CycleDB(tmp_path / "b.db")
    await d.async_open()
    await d.async_initialize()
    try:
        yield d
    finally:
        await d.async_close()


async def test_curve_advice_reads_only_samples_without_the_backup_heater(db):
    import time
    now = time.time()
    for i, (cop, buh) in enumerate(((4.2, 0), (1.6, 1), (4.0, 0))):
        await db.async_insert_cop_sample({"ts": now - 600 + i, "cop": cop, "lwt": 35.0, "outdoor": 2.0,
                                          "mode": "heating", "buh_active": buh})
    every = await db.async_fetch_cop_samples(days=1)
    strict = await db.async_fetch_cop_samples(days=1, include_buh=False)
    assert [r["cop"] for r in every] == [4.2, 1.6, 4.0]          # system COP keeps it
    assert [r["cop"] for r in strict] == [4.2, 4.0]


async def test_the_heating_curve_fetch_asks_for_strict_samples():
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_fetch_cop_samples = AsyncMock(return_value=None)
    c.data = SimpleNamespace(attrs={})
    c._stooklijn_cache, c._stooklijn_cache_ts = {}, 0.0
    await DaikinCycleMLCoordinator._maybe_refresh_stooklijn(c, 10000.0, force=True)
    assert c.db.async_fetch_cop_samples.await_args.kwargs["include_buh"] is False


def test_the_datasheet_window_skips_backup_heater_ticks():
    c = object.__new__(DaikinCycleMLCoordinator)
    c.detector = MagicMock()
    c.detector.snapshot.return_value = {"state": "running", "mode": "heating", "start_ts": 0.0}
    attrs = {"Defrost Operation": "OFF", "BUH Step1": "OFF", "BUH Step2": "OFF"}
    c.data = SimpleNamespace(attrs=attrs)
    assert c._steady_heating_view(10000.0) is not None
    attrs["BUH Step1"] = "ON"
    assert c._steady_heating_view(10000.0) is None
    c._cop_ds_window = None
    c._track_cop_ds_pct(10000.0, -30.0)
    assert list(c._cop_ds_window) == []
