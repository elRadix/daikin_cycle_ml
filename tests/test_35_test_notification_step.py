"""Batch 35 -- OptionsFlow test_notification step."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
JSON_FILES = [
    "strings.json",
    "translations/en.json",
    "translations/nl.json",
]


def test_cf_has_test_notification_step():
    src = (ROOT / "config_flow.py").read_text()
    assert "async def async_step_test_notification(" in src
    assert "_get_coordinator_handle" in src


def test_cf_init_menu_includes_test_notification():
    src = (ROOT / "config_flow.py").read_text()
    start = src.index("async def async_step_init(")
    end = src.index("def _save(", start)
    block = src[start:end]
    assert "test_notification" in block


def test_cf_test_step_uses_emit_status_update():
    src = (ROOT / "config_flow.py").read_text()
    start = src.index("async def async_step_test_notification(")
    end = src.index("async def async_step_ml(", start)
    block = src[start:end]
    assert "async_emit_status_update" in block
    assert "description_placeholders" in block


@pytest.mark.parametrize("rel", JSON_FILES)
def test_json_has_test_notification_step(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    step = d["options"]["step"]
    assert "test_notification" in step
    assert "title" in step["test_notification"]
    assert "description" in step["test_notification"]


@pytest.mark.parametrize("rel", JSON_FILES)
def test_json_init_menu_has_test_notification_label(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    mo = d["options"]["step"]["init"]["menu_options"]
    assert "test_notification" in mo
    assert mo["test_notification"]
