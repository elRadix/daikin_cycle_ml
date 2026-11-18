"""#288: bivalent installs (HP + external boiler) get the same trusted
boiler-signal handling as EVLQ hybrids; everything else is unchanged.

Opt-in is the ESPAltherma register "Bivalent Operation" (commented out by
default). Present -> boiler demand signals drive the cycle-close guard,
alert suppression and boiler-only COP sample skip, exactly like a hybrid.
Absent -> monovalent behaviour, byte-for-byte as before (v1.17.2 guard
against template drift stays in force).
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_BIVALENT_OPERATION,
    MODEL_CHOICES,
    resolve_model_key,
)
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.engine.attribute_compat import build_compat_view
from custom_components.daikin_cycle_ml.engine.thermal import (
    bivalent_present_from_attrs,
    boiler_signals_trusted,
)
from tests.test_rollup_concurrency import _mk_db
from tests.test_v1199_cop_gate_wire import _make_coord_for_gate

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "attrs,expected",
    [({}, False), ({ATTR_BIVALENT_OPERATION: None}, False),
     ({ATTR_BIVALENT_OPERATION: "OFF"}, True), ({ATTR_BIVALENT_OPERATION: False}, True),
     ({ATTR_BIVALENT_OPERATION: "ON"}, True)],
)
def test_bivalent_present(attrs, expected):
    assert bivalent_present_from_attrs(attrs) is expected


def test_german_label_resolves():
    assert bivalent_present_from_attrs(build_compat_view({"Bivalenter Betrieb": "ON"}))


def test_label_exists_in_espaltherma_beta():
    labels = json.loads((ROOT / "docs/MODEL_ATTRIBUTES.json").read_text())["labels"]
    assert ATTR_BIVALENT_OPERATION in labels and len(labels[ATTR_BIVALENT_OPERATION]) > 20


@pytest.mark.parametrize(
    "hyb,biv,expected",
    [(False, False, False), (True, False, True), (False, True, True),
     (True, True, True), (MagicMock(), False, False), (False, 1, False)],
)
def test_boiler_signals_trusted(hyb, biv, expected):
    assert boiler_signals_trusted(SimpleNamespace(is_hybrid=hyb, is_bivalent=biv)) is expected


def test_trusted_defaults_for_legacy_snapshots():
    assert boiler_signals_trusted(SimpleNamespace()) is False
    assert boiler_signals_trusted(SimpleNamespace(is_hybrid=True)) is True


def _alerts_coord(**snap):
    c = object.__new__(DaikinCycleMLCoordinator)
    c.data = SimpleNamespace(state="idle", boiler_dhw_active=False, **snap)
    return c


def test_alert_kwargs_bivalent_boiler_honoured():
    kw = _alerts_coord(is_hybrid=False, is_bivalent=True, boiler_active=True)._boiler_kwargs_for_alerts()
    assert kw["boiler_active"] is True and kw["hp_running"] is False


def test_alert_kwargs_monovalent_unchanged():
    kw = _alerts_coord(is_hybrid=False, is_bivalent=False, boiler_active=True)._boiler_kwargs_for_alerts()
    assert kw["boiler_active"] is False


async def _collect(tmp_path, monkeypatch, *, bivalent: bool) -> int:
    db = await _mk_db(tmp_path)
    try:
        c = _make_coord_for_gate(db)
        c.data.state = "idle"          # HP off, boiler heating (Direct SH)
        c.data.boiler_active = True
        c.data.boiler_heat_active = True
        c.data.is_bivalent = bivalent
        st = MagicMock()
        st.state = "4.0"
        st.attributes = {"leaving_temp": 30.0, "outdoor_temperature": 2.0}
        c.hass.states.get.return_value = st
        import custom_components.daikin_cycle_ml.coordinator as coord_mod
        monkeypatch.setattr(
            coord_mod, "build_compat_view",
            lambda a: {
                "Leaving water temp. before BUH (R1T)": 30.0,
                "Leaving water temp. after BUH (R2T)": 30.0,
                "Inlet water temp.(R4T)": 25.0,
                "Outdoor air temp.(R1T)": 2.0,
                "Flow sensor (l/min)": 15.0,
                "Defrost Operation": False,
            },
        )
        c._resolve_cop_sample_mode = lambda: "heating"
        await c._maybe_collect_cop_sample(time.time())
        async with db._conn.execute("SELECT COUNT(*) FROM cop_samples") as cur:
            return (await cur.fetchone())[0]
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_bivalent_boiler_only_sample_skipped(tmp_path, monkeypatch):
    assert await _collect(tmp_path, monkeypatch, bivalent=True) == 0


async def test_monovalent_sample_still_collected(tmp_path, monkeypatch):
    assert await _collect(tmp_path, monkeypatch, bivalent=False) == 1


@pytest.mark.parametrize(
    "alias,target",
    [("erga04evh", "erga04eav3"), ("erga06evh", "erga06eav3"), ("erga08evh", "erga08eav3"),
     ("erga04evh7", "erga04eav3"), ("erga06evh7", "erga06eav3")],
)
def test_erga_evh_aliases(alias, target):
    assert resolve_model_key(alias) == target
    assert alias not in MODEL_CHOICES
