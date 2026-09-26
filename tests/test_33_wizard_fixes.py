"""Batch 33 -- wizard consistency regression tests."""
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


def _walk(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                yield v
            elif isinstance(v, (dict, list)):
                yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            if isinstance(v, str):
                yield v
            elif isinstance(v, (dict, list)):
                yield from _walk(v)


@pytest.mark.parametrize('rel', JSON_FILES)
def test_no_literal_backslash_n_anywhere(rel: str) -> None:
    data = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    for s in _walk(data):
        assert "\\n" not in s, f"{rel}: literal backslash-n found"


@pytest.mark.parametrize('rel', JSON_FILES)
def test_attributes_description_has_real_newlines(rel: str) -> None:
    data = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    desc = data["config"]["step"]["attributes"]["description"]
    assert "\n" in desc


@pytest.mark.parametrize('rel', JSON_FILES)
def test_cycle_step_has_indoor_temp_sensor_keys(rel: str) -> None:
    data = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    step = data["config"]["step"]["cycle"]
    assert "indoor_temp_sensor" in step.get("data", {})
    assert "indoor_temp_sensor" in step.get("data_description", {})


def test_config_flow_cycle_uses_entity_selector_for_indoor_temp() -> None:
    src = (ROOT / "config_flow.py").read_text()
    start = src.index("async def async_step_cycle")
    end = src.index("async def async_step_pendulum", start)
    block = src[start:end]
    assert 'indoor_temp_sensor' in block
    assert "selector.EntitySelector" in block
    assert "): str," not in block
