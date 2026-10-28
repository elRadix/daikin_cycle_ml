"""Tests for #188 + #184: v20 thermal R1T/R4T fix (matches raomin ESPAltherma 5382853)."""
from __future__ import annotations
import pytest
from pytest import approx
from unittest.mock import MagicMock
from custom_components.daikin_cycle_ml.engine.thermal import dt_from_attrs
from custom_components.daikin_cycle_ml.storage.db import CycleDB

R1 = "Leaving water temp. before BUH (R1T)"
R1V1 = "Leaving water temp.(R1T)"
R2 = "Leaving water temp. after BUH (R2T)"
R4 = "Inlet water temp.(R4T)"

def test_dt_heating():
    assert dt_from_attrs({R1: 25.0, R4: 18.0}) == 7.0

def test_dt_cooling_abs():
    assert dt_from_attrs({R1: 18.0, R4: 25.0}) == 7.0

def test_dt_v1_short():
    assert dt_from_attrs({R1V1: 25.0, R4: 18.0}) == 7.0

def test_dt_near_zero():
    assert dt_from_attrs({R1: 18.2, R4: 18.0}) is None

def test_dt_fallback_r2t():
    assert dt_from_attrs({R2: 30.0, R4: 25.0}) == 5.0

def test_dt_no_r4t():
    assert dt_from_attrs({R1: 25.0}) is None

_M = MagicMock()
async def _tfs(row, mode="heating"):
    return await CycleDB._thermal_from_sample(_M, row, mode)

@pytest.mark.asyncio
async def test_tfs_heating():
    r = await _tfs({"flow_lmin": 10.0, "lwt": 30.0, "outdoor": 5.0, "r1t": 25.0, "r4t": 18.0})
    assert r == approx(4.869, abs=1e-3)

@pytest.mark.asyncio
async def test_tfs_cooling():
    r = await _tfs({"flow_lmin": 10.0, "lwt": 30.0, "outdoor": 5.0, "r1t": 18.0, "r4t": 25.0}, mode="cooling")
    assert r == approx(4.869, abs=1e-3)

@pytest.mark.asyncio
async def test_tfs_heating_inverted():
    r = await _tfs({"flow_lmin": 10.0, "lwt": 30.0, "outdoor": 5.0, "r1t": 18.0, "r4t": 25.0})
    assert r == 0.0

@pytest.mark.asyncio
async def test_tfs_heating_cap():
    r = await _tfs({"flow_lmin": 15.0, "lwt": 30.0, "outdoor": 5.0, "r1t": 40.0, "r4t": 10.0})
    assert r is None

@pytest.mark.asyncio
async def test_tfs_fallback_legacy():
    r = await _tfs({"flow_lmin": 10.0, "lwt": 20.0, "outdoor": 10.0})
    assert r == approx(6.956, abs=1e-3)

@pytest.mark.asyncio
async def test_tfs_zero_flow_new():
    r = await _tfs({"flow_lmin": 0.0, "lwt": 30.0, "outdoor": 5.0, "r1t": 25.0, "r4t": 18.0})
    assert r == 0.0

@pytest.mark.asyncio
async def test_tfs_no_flow():
    assert await _tfs({"flow_lmin": None, "lwt": 30.0, "outdoor": 5.0}) is None

@pytest.mark.asyncio
async def test_tfs_no_outdoor_legacy():
    assert await _tfs({"flow_lmin": 10.0, "lwt": 30.0, "outdoor": None}) is None
