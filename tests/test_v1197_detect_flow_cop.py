"""v1.19.7 #261: regression — 69 Nov-2 gap samples must all be detected."""
from __future__ import annotations

import pathlib
import sqlite3
from datetime import datetime, timezone

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_COP,
    ATTR_FLOW_SENSOR,
    ATTR_INV_FREQUENCY_RPS,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    detect_compressor_on,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "_prod1_20261104.db"


@pytest.mark.skipif(not FIXTURE.exists(), reason="prod fixture missing")
def test_replay_nov_2_gap_detects_all_samples():
    """Real prod-1 Nov 2 16:55-22:57 gap: 69 COP samples, ~68 with cop>1.5.

    Pre-fix: detect_compressor_on returned False for all (RPS invalid).
    Post-fix: flow>5 AND cop>1.5 catches 68/69.
    """
    c = sqlite3.connect(f"file:{FIXTURE}?mode=ro", uri=True)
    try:
        start = int(datetime(2026, 11, 2, 16, 55, tzinfo=timezone.utc).timestamp())
        end = int(datetime(2026, 11, 2, 22, 57, tzinfo=timezone.utc).timestamp())
        rows = c.execute(
            "SELECT cop, flow_lmin FROM cop_samples "
            "WHERE ts >= ? AND ts < ? ORDER BY ts",
            (start, end),
        ).fetchall()
    finally:
        c.close()

    assert len(rows) >= 60, f"expected ~69 samples, got {len(rows)}"

    detected = 0
    for cop, flow in rows:
        attrs = {
            ATTR_INV_FREQUENCY_RPS: "Invalid",
            ATTR_FLOW_SENSOR: flow,
            ATTR_COP: cop,
        }
        if detect_compressor_on(attrs):
            detected += 1

    assert detected >= 66, (
        f"expected >=66/{len(rows)} detected, got {detected}"
    )
