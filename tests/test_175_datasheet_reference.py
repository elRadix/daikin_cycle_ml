"""#175: COP vs datasheet compared with the datasheet at the live point.

cop_vs_datasheet_pct carried the live COP to A7/W35 with a Carnot ratio.
That ratio assumes a constant Carnot efficiency, which no heat pump has:
fed with its own datasheet values, a unit exactly on spec read

    EPRA12EAV3  A-7/W35 -17 %, A7/W45 -13 %, A-2/W45 -27 %, A7/W55 -16 %
    ERGA08EAV3  A-7/W55 -32 %
    EKHBRD011   A7/W65 +12 %       ERRQ014 A7/W65 +20 %

so a healthy LT unit got cop_vs_datasheet_low (< -10 %) at LWT >= 45 or in
frost, and an HT unit could lose up to 20 % unseen. The reference now comes
from the nearest datasheet points; the Carnot ratio only bridges the
remaining distance. Replayed on the bundled datasheets of every model with
more than one point: each point reads 0 %.
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine.model_datasheets import load_bundled
from custom_components.daikin_cycle_ml.engine.physics import (
    carnot_lift_factor,
    datasheet_cop_at,
)
from tests.test_v12211_cop_normalized_fallbacks import _coord

BUNDLED = load_bundled()
MULTI = sorted(m for m, v in BUNDLED.items() if len(v.get("points") or []) > 1)
CASES = [(m, p) for m in MULTI for p in BUNDLED[m]["points"]]


def test_the_replay_covers_lt_and_ht_models():
    assert {"epra12eav3", "erga08eav3", "ekhbrd011", "errq014"} <= set(MULTI)


async def _pct(model: str, cop: float, t_out: float, lwt: float) -> dict:
    c = _coord()
    c.entry.data = {"model": model}
    c._datasheet_merged = BUNDLED
    await c._refresh_datasheet_state(now=1000.0, lwt_now=lwt, t_out=t_out, cop_meas=cop)
    return c._datasheet_cache


@pytest.mark.parametrize(("model", "pt"), CASES, ids=[f"{m}-{p['label']}" for m, p in CASES])
async def test_a_unit_exactly_on_its_datasheet_reads_zero(model, pt):
    out = await _pct(model, float(pt["cop"]), float(pt["t_out"]), float(pt["t_lwc"]))
    assert out["cop_vs_datasheet_pct"] == pytest.approx(0.0, abs=0.01), out
    assert out["reference_point"] == pt["label"] and out["reference_distance_k"] == 0.0
    a7w35 = next(p["cop"] for p in BUNDLED[model]["points"] if p["label"] == "A7/W35")
    assert out["cop_normalized_a7w35"] == pytest.approx(a7w35, abs=0.001)


async def test_no_false_alert_at_a7_w55_but_a_real_loss_still_shows():
    # EPRA12 on spec at A7/W55 (2.94) read -16 %, below the -10 % alert
    assert (await _pct("epra12eav3", 2.94, 7.0, 55.0))["cop_vs_datasheet_pct"] == 0.0
    lost = await _pct("epra12eav3", 2.94 * 0.85, 7.0, 55.0)
    assert lost["cop_vs_datasheet_pct"] == pytest.approx(-15.0, abs=0.01)


async def test_ht_loss_at_w65_is_no_longer_hidden():
    # ERRQ014 at A7/W65 with 15 % less than its datasheet read +2 % before
    out = await _pct("errq014", 3.00 * 0.85, 7.0, 65.0)
    assert out["cop_vs_datasheet_pct"] == pytest.approx(-15.0, abs=0.01)


async def test_between_points_the_reference_lies_between_them():
    out = await _pct("epra12eav3", 4.0, 7.0, 40.0)            # between W35 4.92 and W45 3.57
    assert 3.57 < out["cop_datasheet_live"] < 4.92 and out["reference_points_used"] == 3


async def test_a_single_point_model_keeps_the_carnot_normalisation():
    one = next(m for m, v in BUNDLED.items() if [p["label"] for p in v.get("points") or []] == ["A7/W35"])
    cop, t_out, lwt = 3.2, -2.0, 42.0
    out = await _pct(one, cop, t_out, lwt)
    ref = BUNDLED[one]["points"][0]["cop"]
    old = cop * carnot_lift_factor(7.0, 35.0) / carnot_lift_factor(t_out, lwt)   # the v1.22.11 formula
    assert out["cop_normalized_a7w35"] == pytest.approx(round(old, 3))
    assert out["cop_vs_datasheet_pct"] == pytest.approx(round((old - ref) / ref * 100, 2))


def test_helper_edge_cases():
    pts = [{"label": "A7/W35", "t_out": 7, "t_lwc": 35, "cop": 4.0},
           {"t_out": 7, "t_lwc": 55, "cop": 0}, {"t_out": "x", "cop": 3}, {"cop": 3},
           {"t_out": 30, "t_lwc": 10, "cop": 3.0}]                      # no lift: skipped
    assert datasheet_cop_at(pts, 7.0, 35.0)["cop"] == 4.0
    assert datasheet_cop_at([{"t_out": 2, "t_lwc": 35, "cop": 4.0}], 2.0, 35.0)["point"] == "A2/W35"
    assert datasheet_cop_at(pts, 40.0, 20.0) is None                    # no lift at the live point
    assert datasheet_cop_at([], 7.0, 35.0) is None and datasheet_cop_at(pts[1:4], 7.0, 35.0) is None
    assert carnot_lift_factor(30.0, 10.0) is None


def test_the_sensor_shows_the_reference():
    from types import SimpleNamespace

    from custom_components.daikin_cycle_ml.sensor import _attrs_cop_vs_datasheet_pct
    s = SimpleNamespace(datasheet={"points": [{"label": "A7/W35", "cop": 4.92}]}, datasheet_model="epra12eav3",
                        cop_normalized_a7w35=4.92, cop=2.94, cop_vs_datasheet_pct=0.0,
                        cop_datasheet_ref={"cop_datasheet_live": 2.94, "reference_point": "A7/W55",
                                           "reference_distance_k": 0.0, "reference_points_used": 3})
    a = _attrs_cop_vs_datasheet_pct(s, None)
    assert a["cop_datasheet_live"] == 2.94 and a["reference_point"] == "A7/W55" and a["band"] == "on_spec"
    s.cop_datasheet_ref = None
    assert _attrs_cop_vs_datasheet_pct(s, None)["reference_point"] is None
