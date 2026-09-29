"""Ensure all SENSOR_DEFS keys have translation entries."""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS

ROOT = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml"


def test_translations_all_keys_present() -> None:
    keys = {spec["key"] for spec in SENSOR_DEFS}
    for fname in ("strings.json", "translations/en.json", "translations/nl.json"):
        with open(ROOT / fname) as f:
            data = json.load(f)
        present = set(data.get("entity", {}).get("sensor", {}).keys())
        missing = keys - present
        assert not missing, "%s missing keys: %s" % (fname, sorted(missing))
