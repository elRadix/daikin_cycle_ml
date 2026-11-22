"""Alert severity follows the action level of its text (#463 review).

Replay of a diagnostics file (EPRA08EAV3, v1.29.0, corpus): a 11 min DHW
run raised "short_run" with severity "warning" while the text said
"Geen actie nodig" (no action needed), so the Daily summary card showed a
warning for a normal event. Severity now comes from the same level as the
text: no action needed = info, keep an eye on it = warning, action needed =
critical (the only level that passes quiet hours).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.coordinator import _ALERT_MESSAGE_MAX, _clip_message
from custom_components.daikin_cycle_ml.engine.alert_texts import LEVEL, LEVEL_ACT, LEVEL_INFO, LEVEL_WATCH
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
    SEV_CRITICAL,
    SEV_INFO,
    SEV_WARNING,
)

SEV_OF = {LEVEL_INFO: SEV_INFO, LEVEL_WATCH: SEV_WARNING, LEVEL_ACT: SEV_CRITICAL}
CORPUS = Path(__file__).parent / "fixtures/diagnostics/epra08eav3_1_29_0_95d43f8546_202611220929.json"


@pytest.mark.parametrize("key", sorted(BINARY_ALERT_MAP))
def test_severity_matches_the_level_of_the_text(key):
    alert_type, severity, _ = BINARY_ALERT_MAP[key]
    assert severity == SEV_OF[LEVEL[alert_type]], (key, severity, LEVEL[alert_type])


def test_reported_short_run_is_info():
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    ent = data["entities"]["sensor:alerts_today"]
    stored = next(a for a in ent["attributes"]["alerts"] if a["type"] == "short_run")
    assert stored["severity"] == "warning"                    # what v1.29.0 stored
    assert "Geen actie nodig" in stored["message"]            # what its text said
    assert BINARY_ALERT_MAP["short_run"][1] == SEV_INFO        # now the same level


def test_alerts_today_message_is_whole_or_cut_at_a_word():
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    ent = data["entities"]["sensor:alerts_today"]
    cut_400 = next(a for a in ent["attributes"]["alerts"] if a["type"] == "cop_vs_datasheet_low")["message"]
    assert cut_400.endswith("installateur de")                 # v1.29.0 cut it at 400 characters
    assert _clip_message(cut_400) == cut_400                   # a whole message stays whole
    long = ("woord " * 400).strip()
    out = _clip_message(long)
    assert len(out) <= _ALERT_MESSAGE_MAX + 1 and out.endswith("woord…")
    assert _clip_message("x" * 1300).endswith("…")       # one long word: hard cut
