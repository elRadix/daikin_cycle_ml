"""#478: replay of the reported Performance card (EPRA12EAV3, Hydrosplit).

Reported: -1 °C outdoor, 30 °C water on target, 5.7 kW heat, 1.03 kW, COP
5.49, compressor 36 rps, speed range 15 (typed) - 44 (learned from 179
mild-weather runs). The card said 104 % thermal load, "NO HEADROOM" and
"backup heater has to help": it took the EN 14511 rating points (4.8 / 5.74
kW at A-7 / A2) as the maximum. A Daikin application engineer reviewed the
logic; Daikin's certification sheet 4D133543C gives 7.49 kW at A-7/W35 and
a product-table maximum of 9.97 kW at A7/W35.
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine import model_profile as mp
from tests.test_467_performance_card import MERGED_KEYS, _run, _specs
from tests.test_efficiency_native_card import _case, _set, _text

PROFILE = mp.edit({}, "epra12eav3", fields={"rps_min": 15})
LEARNED_RPS = {"rps_min": 18, "rps_max": 44, "runs": 179}


def _reported(lang: str) -> dict:
    case = _case(lang)
    merged = mp.apply_profile(_specs(case), PROFILE, "epra12eav3", LEARNED_RPS)
    case = _set(case, "hp_specs", **{k: merged.get(k) for k in MERGED_KEYS}, rps_learned=LEARNED_RPS)
    return _set(case, "thermal_power_live", "5.7", outdoor_c=-1, lwt_c=30, lw_setpoint_c=30,
                input_power_w=1030, input_cop=5.49, input_rps=36)


@pytest.fixture(scope="module")
def out() -> dict:
    cases = {lang: _reported(lang) for lang in ("en", "nl", "fr")}
    cases["buh"] = _set(_reported("en"), "buh_active", "on")
    return _run(cases)


def test_reported_case_has_reserve_not_a_limit(out):
    r = out["cases"]["en"]
    # W35 row (30 °C is 5 K away: nearest row) between A-7 (estimate 9.97 x 0.86
    # = 8.57, above the certified 7.49) and A2 (9.97 x 0.95 = 9.47, above 5.74)
    th = 8.57 + (9.47 - 8.57) * (-1 + 7) / 9
    assert r["limits"]["thMax"] == pytest.approx(th, abs=1e-6)
    assert r["loads"]["thermal"] == pytest.approx(5.7 / th * 100, abs=1e-6)   # about 62 %, not 104 %
    assert r["headroom"] == pytest.approx(th - 5.7, abs=1e-6)                 # about 3.5 kW reserve
    assert r["atLimit"] is False and (r["lvl"], r["key"]) == ("good", "ok_efficient")
    assert r["limits"]["fSeen"] is True and r["limits"]["fTop"] is None       # 44 rps: highest seen
    assert r["loads"]["electrical"] == pytest.approx(1.03 / 2.28 * 100, abs=1e-6)
    text = _text(r["html"])
    assert "AT ITS LIMIT" not in text and "backup heater" not in text.lower()
    assert "Maximum = highest speed seen so far" in text and "COP vs rating point" in text
    assert "kW more heat available from the heat pump" in text


def test_backup_heater_on_is_shown_from_its_signal(out):
    r = out["cases"]["buh"]
    assert (r["lvl"], r["key"]) == ("watch", "buh_on") and r["atLimit"] is False
    assert "The backup heater is on while the heat pump still has reserve" in _text(r["html"])


@pytest.mark.parametrize(("lang", "words"), [
    ("en", ["RESERVE", "highest speed seen so far"]),
    ("nl", ["RESERVE", "hoogste toerental tot nu toe"]),
    ("fr", ["RÉSERVE", "vitesse la plus haute vue jusqu"]),
])
def test_texts_in_every_language(out, lang, words):
    text = _text(out["cases"][lang]["html"])
    for w in words:
        assert w in text, (lang, w)
    assert "undefined" not in text and "NaN" not in text
