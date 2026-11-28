"""#523 / #522: "COP heating today" unknown while the heat pump is idle.

Replay of the reporter's diagnostics (tests/fixtures/diagnostics,
epra08eav3_1_31_0_b63203fae1_*, an ERRA08EAV37 on the EPRA08EAV3 profile):
detector idle, today's heating COP 2.83 over 50 samples, the combined COP
showing 2.83 and cop_today `unknown`. The day value now stays.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS

CORPUS = Path(__file__).parent / "fixtures" / "diagnostics"
FILES = sorted(CORPUS.glob("epra08eav3_1_31_0_b63203fae1_*.json"))


@pytest.mark.parametrize("path", FILES, ids=[p.name for p in FILES])
def test_cop_today_shown_while_idle(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    assert d["coordinator"]["state"] == "idle"
    today = d["cop_analysis"]["cop_today"]
    assert today["samples_today"] == 50 and today["cop"] == 2.83
    # what the reporter saw: the day COP unknown, the combined COP 2.83
    assert d["entities"]["sensor:cop_chauffage_du_jour"]["state"] == "unknown"
    assert d["entities"]["sensor:cop_global_du_jour"]["state"] == "2.83"
    snap = SimpleNamespace(state="idle", cop_today=today)
    value = next(s["value_fn"] for s in SENSOR_DEFS if s["key"] == "cop_today")
    assert value(snap, None) == 2.83


def test_both_files_are_in_the_corpus():
    assert len(FILES) == 2
