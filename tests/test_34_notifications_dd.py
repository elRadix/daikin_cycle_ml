"""Batch 34 -- notifications data_description + version consistency."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
JSON_FILES = [
    "strings.json",
    "translations/en.json",
    "translations/nl.json",
]
NEW_VER = "0.7.1"


@pytest.mark.parametrize("rel", JSON_FILES)
def test_notifications_step_dd_keys_complete(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    step = d["config"]["step"]["notifications"]
    dd = step.get("data_description") or {}
    data = step.get("data") or {}
    miss = [k for k in data if k not in dd]
    assert miss == [], rel + " missing dd keys " + repr(miss)


def test_version_consistent_in_three_files():
    const = (ROOT / "const.py").read_text()
    m = re.search(r"VERSION" + chr(92) + "s*=" + chr(92) + "s*" + chr(34) + "([^" + chr(34) + "]+)" + chr(34), const)
    assert m is not None
    assert m.group(1) == NEW_VER
    mf = json.loads((ROOT / "manifest.json").read_text())
    assert mf.get("version") == NEW_VER
    pp = (ROOT / "pyproject.toml").read_text()
    assert NEW_VER in pp
