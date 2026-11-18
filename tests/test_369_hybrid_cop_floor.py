"""#369: hybrid datasheet reference, hybrid model aliases, COP floor.

* EVLQ05/08CV3 A7/W35 reference = Daikin EN14511 nominal (5.04 / 4.45),
  not the part-load 5.85 / 5.75 that made cop_vs_datasheet_pct read low.
* Every hybrid indoor/kit code from ESPAltherma's "Altherma(Hybrid)"
  definition resolves to its EVLQ outdoor unit and is treated as hybrid;
  no non-hybrid model changes family or hybrid status.
* A heating/DHW COP sample below 1.0 (start-up transient, #369 prod data
  0.35) is stored flagged so it stays out of every COP aggregate; the
  Carnot classifier contract itself is unchanged.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.config_flow import _is_hybrid_model
from custom_components.daikin_cycle_ml.const import (
    MODEL_ALIASES,
    MODEL_CHOICES,
    MODEL_EVLQ05CV3,
    MODEL_EVLQ08CV3,
    family_for_model,
    resolve_model_key,
)
from custom_components.daikin_cycle_ml.engine.model_datasheets import (
    get_datasheet,
    load_bundled,
)
from custom_components.daikin_cycle_ml.engine.physics import (
    COP_FLOOR,
    below_cop_floor,
    classify_cop_sample,
)
from tests.test_rollup_concurrency import _mk_db
from tests.test_v1199_cop_gate_wire import _make_coord_for_gate

DS = json.loads(
    (Path(__file__).resolve().parent.parent
     / "custom_components/daikin_cycle_ml/data/datasheets.json").read_text()
)["models"]

# --- datasheet ---------------------------------------------------------------


@pytest.mark.parametrize(
    "model,cop,hc,hc_max",
    [(MODEL_EVLQ05CV3, 5.04, 4.40, 5.12), (MODEL_EVLQ08CV3, 4.45, 7.40, 10.02)],
)
def test_evlq_a7w35_is_daikin_nominal(model, cop, hc, hc_max):
    e = DS[model]
    a7 = [p for p in e["points"] if p["label"] == "A7/W35"]
    assert len(a7) == 1 and a7[0]["cop"] == cop and a7[0]["hc"] == hc
    assert e["nom_cop"] == cop and e["hc_max_a7"] == hc_max
    assert e["verified"] is True and "daikin" in e["ref"].lower()


def test_evlq_reference_used_for_normalisation_is_nominal():
    merged = load_bundled()
    for model, cop in ((MODEL_EVLQ05CV3, 5.04), (MODEL_EVLQ08CV3, 4.45)):
        ds = get_datasheet(merged, model)
        ref = next(p for p in ds["points"] if p["label"] == "A7/W35")
        assert ref["cop"] == cop


# --- aliases -----------------------------------------------------------------

HYBRID_05 = ["evlq05cav3", "ehyhbh05aav3", "ehyhbh05afv3", "ehyhbh05aav3u",
             "rhyhbh05aav3", "chyhbh05aav3", "chyhbh05afv3", "ehyhbh05av32"]
HYBRID_08 = ["evlq08cav3", "ehyhbh08aav3", "ehyhbh08afv3", "ehyhbh08aav3u",
             "ehyhbx08aav3", "ehyhbx08afv3", "rhyhbh08aav3", "rhyhbx08aav3",
             "chyhbh08aav3", "chyhbh08afv3", "ehyhbh08av32", "ehyhbx08av3"]


@pytest.mark.parametrize(
    "alias,target",
    [(a, MODEL_EVLQ05CV3) for a in HYBRID_05] + [(a, MODEL_EVLQ08CV3) for a in HYBRID_08],
)
def test_hybrid_alias_resolves_and_is_hybrid(alias, target):
    assert resolve_model_key(alias) == target
    assert family_for_model(alias) == "evlq"
    assert _is_hybrid_model(alias)
    assert get_datasheet(load_bundled(), alias) is not None


def test_issue_369_reported_unit_model_resolves():
    # ESPAltherma "Unit model: EHYHBX08AAV3" on the #369 install
    assert resolve_model_key("EHYHBX08AAV3".lower()) == MODEL_EVLQ08CV3


@pytest.mark.parametrize("model", [m for m in MODEL_CHOICES if not m.startswith("evlq")])
def test_non_hybrid_models_unaffected(model):
    assert not _is_hybrid_model(model)
    assert family_for_model(resolve_model_key(model)) != "evlq"


def test_aliases_only_target_real_models():
    assert set(MODEL_ALIASES.values()) <= set(MODEL_CHOICES)
    # new hybrid aliases never shadow a wizard model
    assert not set(HYBRID_05 + HYBRID_08) & set(MODEL_CHOICES)


# --- COP floor -----------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,cop,expected",
    [("heating", 0.35, True), ("dhw", 0.99, True), ("heating", COP_FLOOR, False),
     ("heating", 3.2, False), ("cooling", 0.5, False), ("unknown", 0.5, False),
     ("heating", None, False)],
)
def test_below_cop_floor(mode, cop, expected):
    assert below_cop_floor(mode, cop) is expected


def test_classifier_contract_unchanged():
    # floor lives outside the classifier: None / no-lift stay not_applicable
    assert classify_cop_sample("heating", None, 5.0, 0.35) == "not_applicable"
    assert classify_cop_sample("heating", 5.0, 5.0, 0.35) == "not_applicable"
    assert classify_cop_sample("heating", 30.0, 10.0, 0.35) == "accept"


async def _collect(tmp_path, monkeypatch, cop: str) -> list[int]:
    db = await _mk_db(tmp_path)
    try:
        c = _make_coord_for_gate(db)
        st = MagicMock()
        st.state = cop
        st.attributes = {"leaving_temp": 30.0, "outdoor_temperature": 10.0}
        c.hass.states.get.return_value = st
        import custom_components.daikin_cycle_ml.coordinator as coord_mod
        monkeypatch.setattr(
            coord_mod, "build_compat_view",
            lambda a: {
                "Leaving water temp. before BUH (R1T)": 30.0,
                "Leaving water temp. after BUH (R2T)": 30.0,
                "Inlet water temp.(R4T)": 25.0,
                "Outdoor air temp.(R1T)": 10.0,
                "Flow sensor (l/min)": 15.0,
                "Defrost Operation": False,
            },
        )
        c._resolve_cop_sample_mode = lambda: "heating"
        await c._maybe_collect_cop_sample(time.time())
        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples"
        ) as cur:
            return [r[0] for r in await cur.fetchall()]
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_low_cop_sample_stored_flagged(tmp_path, monkeypatch):
    assert await _collect(tmp_path, monkeypatch, "0.35") == [1]


async def test_normal_cop_sample_stays_unflagged(tmp_path, monkeypatch):
    assert await _collect(tmp_path, monkeypatch, "3.2") == [0]


async def test_low_cop_excluded_from_cop_today(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        base = {"lwt": 34.0, "outdoor": 9.0, "mode": "heating",
                "source": "interval", "power_stable": True}
        for i, cop in enumerate((3.6, 3.8, 4.0)):
            await db.async_insert_cop_sample({**base, "ts": now - 300 + i, "cop": cop})
        assert below_cop_floor("heating", 0.35)
        await db.async_insert_cop_sample(
            {**base, "ts": now - 10, "cop": 0.35, "is_transition_artifact": 1}
        )
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        c = object.__new__(DaikinCycleMLCoordinator)
        c.db = db
        c._is_hybrid_install = lambda: False
        await c._refresh_cop_today(now)
        assert c._cop_today_cache["cop"] == pytest.approx(3.8)
        assert c._cop_today_cache["cop_min"] == pytest.approx(3.6)
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
