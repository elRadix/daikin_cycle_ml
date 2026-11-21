"""#473: the Performance card with maximum heat learned from this installation.

The fixture's hp_specs with the bundled EPRA12EAV3 entry is merged by the
integration's own apply_profile with learned bands, so the card reads what
production writes. #478: a learned value is a lower bound; at A3/W30 the
unit delivered 9.8 kW, above the 9.57 kW estimate, so the learned value
holds there; the thermal dial says "Learned from your runs" and the
profile shows the "Learned" chip with "from N samples".
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine import model_profile as mp
from tests.test_efficiency_native_card import _case, _set, _text
from tests.test_467_performance_card import MERGED_KEYS, _run, _specs

LEARNED = {"bands": [{"t_out": 3.0, "t_lwc": 30.0, "hmax": 9.8, "n": 412, "days": 9, "reconstructed": 380}],
           "full_speed_samples": 430, "rps_threshold": 57.6, "skipped_bands": 2}


def _learned(lang: str) -> dict:
    case = _case(lang)
    merged = mp.apply_profile(_specs(case), None, "epra12eav3", None, LEARNED)
    return _set(case, "hp_specs", **{k: merged.get(k) for k in MERGED_KEYS}, hmax_learned=LEARNED)


@pytest.fixture(scope="module")
def out() -> dict:
    return _run({lang: _learned(lang) for lang in ("en", "nl", "fr")})


def test_learned_point_is_used_where_the_datasheet_has_none(out):
    r = out["cases"]["en"]
    # 5.2 °C / 33 °C: water between the learned W30 row (A3 9.8 kW, 2.2 K away)
    # and the W35 row (A2 estimate 9.47 / A7 Daikin maximum 9.97)
    w35 = 9.47 + (9.97 - 9.47) * (5.2 - 2) / 5
    th = 9.8 + (w35 - 9.8) * (33 - 30) / 5
    assert r["limits"]["thMax"] == pytest.approx(th, abs=1e-6)
    assert r["limits"]["thLearned"] is True
    assert r["loads"]["thermal"] == pytest.approx(5.02 / th * 100, abs=1e-6)


@pytest.mark.parametrize(("lang", "note", "chip", "samples"), [
    ("en", "Learned from your runs at full speed", "Learned", "from 412 samples"),
    ("nl", "Geleerd uit je runs op vol toerental", "Geleerd", "uit 412 metingen"),
    ("fr", "Appris de vos cycles à pleine vitesse", "Appris", "sur 412 mesures"),
])
def test_texts_in_every_language(out, lang, note, chip, samples):
    text = _text(out["cases"][lang]["html"])
    assert note in text and chip in text and samples in text
    assert "undefined" not in text and "NaN" not in text
