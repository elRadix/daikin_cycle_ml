"""Batch 44 -- one-click test-all-notifications menu item."""
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


def test_cf_has_test_all_methods():
    src = (ROOT / "config_flow.py").read_text()
    assert "async def async_step_test_all_notifications(" in src
    assert "async def async_step_test_all_notifications_result(" in src


def test_cf_init_menu_has_item():
    src = (ROOT / "config_flow.py").read_text()
    start = src.index("async def async_step_init(")
    end = src.index("def _save(", start)
    block = src[start:end]
    assert "\"test_all_notifications\"" in block


def test_cf_uses_async_emit_test_alert():
    src = (ROOT / "config_flow.py").read_text()
    start = src.index("async def async_step_test_all_notifications(")
    end = src.index("async def async_step_test_all_notifications_result(", start)
    block = src[start:end]
    assert "async_emit_test_alert" in block
    assert "\"all_alerts\"" in block
    assert "ignore_filters=True" in block


@pytest.mark.parametrize("rel", JSON_FILES)
def test_json_menu_label(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    mo = d["options"]["step"]["init"]["menu_options"]
    assert "test_all_notifications" in mo
    assert mo["test_all_notifications"]


@pytest.mark.parametrize("rel", JSON_FILES)
def test_json_menu_description(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    mod = d["options"]["step"]["init"]["menu_option_descriptions"]
    assert "test_all_notifications" in mod


@pytest.mark.parametrize("rel", JSON_FILES)
def test_json_step_titles(rel):
    d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    steps = d["options"]["step"]
    assert steps["test_all_notifications"].get("title")
    assert steps["test_all_notifications_result"].get("title")
    assert "{status}" in steps["test_all_notifications_result"]["description"]
    assert "{count}" in steps["test_all_notifications_result"]["description"]
