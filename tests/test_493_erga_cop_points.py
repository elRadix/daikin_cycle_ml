"""Discussion #493: every COP point of the ERGA brochure is in the datasheets.

Daikin's Altherma 3 R W brochure (ERGA04EV / ERGA06EVH / ERGA08EVH7)
lists COP and capacity at A7 and A-7 for 35, 45 and 55 °C water. A7/W35
matches the daikin.eu product table; A7/W45 keeps the product-table value
(EN 14511, dT 5); the other four come from the brochure.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODELS = json.loads((ROOT / "custom_components/daikin_cycle_ml/data/datasheets.json").read_text())["models"]

EXPECTED = {   # (t_out, t_lwc): (cop, kW)
    "erga04eav3": {(7, 35): (5.10, 4.3), (-7, 35): (3.01, 5.48), (7, 45): (3.65, 4.6), (-7, 45): (2.30, 5.24),
                   (7, 55): (2.65, 4.90), (-7, 55): (1.60, 4.37)},
    "erga06eav3": {(7, 35): (4.85, 6.0), (-7, 35): (2.91, 6.40), (7, 45): (3.50, 5.9), (-7, 45): (2.32, 6.36),
                   (7, 55): (2.70, 5.81), (-7, 55): (1.74, 5.72)},
    "erga08eav3": {(7, 35): (4.60, 7.5), (-7, 35): (2.80, 7.42), (7, 45): (3.50, 7.8), (-7, 45): (2.31, 7.74),
                   (7, 55): (2.70, 7.51), (-7, 55): (1.83, 7.43)},
}
EXPECTED["erga08evh7"] = EXPECTED["erga08eav3"]


@pytest.mark.parametrize("model", sorted(EXPECTED))
def test_all_six_brochure_conditions(model):
    pts = {(p["t_out"], p["t_lwc"]): (p["cop"], p["hc"]) for p in MODELS[model]["points"]}
    assert pts == pytest.approx(EXPECTED[model]) and len(MODELS[model]["points"]) == 6
    for p in MODELS[model]["points"]:
        assert p["label"] == f"A{p['t_out']}/W{p['t_lwc']}"
    assert "#493" in MODELS[model]["ref"]
    # physics: colder air or warmer water never raises the COP
    for (to, tw), (cop, _) in pts.items():
        if (to - 14, tw) in pts:
            assert pts[(to - 14, tw)][0] < cop
        if (to, tw + 10) in pts:
            assert pts[(to, tw + 10)][0] < cop
