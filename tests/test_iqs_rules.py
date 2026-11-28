"""IQS Platinum: every rule claimed in quality_scale.yaml is checked in the code.

Home Assistant awards IQS levels only to core integrations; this custom
integration declares Platinum itself, so these tests keep the claim true:
an icon set in code, an entity or service without an icon, a raised error
without a translation, an undeclared library or an entity disabled by
default that a card needs makes them fail.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

from unittest.mock import MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.daikin_cycle_ml.binary_sensor import BINARY_SENSOR_DEFS, DaikinCycleMLBinarySensor
from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS

ROOT = Path(__file__).resolve().parent.parent
COMP = ROOT / "custom_components/daikin_cycle_ml"
MANIFEST = json.loads((COMP / "manifest.json").read_text())
ICONS = json.loads((COMP / "icons.json").read_text())
STRINGS = json.loads((COMP / "strings.json").read_text())
# libraries Home Assistant core itself requires
CORE_LIBS = {"homeassistant", "voluptuous", "aiohttp"}


def _rules() -> dict[str, dict[str, str]]:
    rules: dict[str, dict[str, str]] = {}
    current = None
    for line in (COMP / "quality_scale.yaml").read_text().splitlines():
        m = re.match(r"^  ([a-z-]+):\s*$", line)
        if m:
            current = m.group(1)
            rules[current] = {}
            continue
        m = re.match(r"^    (status|comment):\s*(.*)$", line)
        if m and current:
            rules[current][m.group(1)] = m.group(2).split(" #")[0].strip()
    return rules


def _py_files():
    return sorted(p for p in COMP.rglob("*.py") if "__pycache__" not in p.parts)


def test_platinum_declared_and_every_rule_done_or_exempt():
    assert MANIFEST["quality_scale"] == "platinum"
    rules = _rules()
    assert len(rules) >= 50
    for name, r in rules.items():
        assert r.get("status") in ("done", "exempt"), name
        if r["status"] == "exempt":
            assert r.get("comment"), f"{name}: an exempt rule says why"


def test_dependency_transparency_every_library_declared():
    mods = set()
    for f in _py_files():
        for n in ast.walk(ast.parse(f.read_text())):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                mods.add(n.module.split(".")[0])
    third = {m for m in mods if m not in sys.stdlib_module_names} - CORE_LIBS
    declared = {re.split(r"[<>=!~\[]", r)[0].lower() for r in MANIFEST["requirements"]}
    assert third == {"aiosqlite"} and third <= declared


def test_icon_translations_every_entity_and_service_no_icon_in_code():
    assert not (COMP / "translations/icons.json").exists()     # Home Assistant never reads it there
    for plat, defs in (("sensor", SENSOR_DEFS), ("binary_sensor", BINARY_SENSOR_DEFS)):
        keys = {d["key"] for d in defs}
        assert set(ICONS["entity"][plat]) <= keys, plat
        for d in defs:
            assert "icon" not in d, d["key"]
            # an icon in icons.json, or the device class default icon
            assert d["key"] in ICONS["entity"][plat] or d.get("device_class"), d["key"]
        for k, v in ICONS["entity"][plat].items():
            assert v["default"].startswith("mdi:"), k
    for f in ("sensor.py", "binary_sensor.py", "entity.py"):
        assert "_attr_icon" not in (COMP / f).read_text(), f
    services = re.findall(r"^([a-z_]+):\s*$", (COMP / "services.yaml").read_text(), re.M)
    assert len(services) == 17 and set(services) == set(ICONS["services"])


def test_exception_translations_every_raised_error():
    used: dict[str, set[str]] = {}
    for f in _py_files():
        for n in ast.walk(ast.parse(f.read_text())):
            if not (isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)):
                continue
            name = getattr(n.exc.func, "id", getattr(n.exc.func, "attr", ""))
            if name not in ("HomeAssistantError", "ServiceValidationError"):
                continue
            kw = {k.arg: k.value for k in n.exc.keywords}
            assert not n.exc.args and "translation_key" in kw and "translation_domain" in kw, f"{f.name}:{n.lineno}"
            ph = kw.get("translation_placeholders")
            used[kw["translation_key"].value] = {k.value for k in ph.keys} if isinstance(ph, ast.Dict) else set()
    assert len(used) == 7  # #508 reports_build_failed
    for lang in ("en", "nl", "fr"):
        tr = json.loads((COMP / f"translations/{lang}.json").read_text())["exceptions"]
        for key, ph in used.items():
            msg = tr[key]["message"]
            assert set(re.findall(r"\{(\w+)\}", msg)) == ph, (lang, key)
    assert set(STRINGS["exceptions"]) == set(used)


def test_entities_disabled_by_default_are_not_used_by_any_card():
    off = [d["key"] for d in [*SENSOR_DEFS, *BINARY_SENSOR_DEFS] if d.get("enabled_default") is False]
    assert sorted(off) == ["boiler_dhw_demand", "boiler_operation_demand", "dhw_installed"]
    cards = [*(COMP / "frontend").glob("*.js"), *(ROOT / "dashboard").rglob("*.yaml")]
    for key in off:
        for c in cards:
            assert not re.search(rf"\b{key}\b", c.read_text(encoding="utf-8", errors="ignore")), (key, c.name)


@pytest.mark.parametrize("plat", ["sensor", "binary_sensor"])
def test_platforms_typed_entry_and_parallel_updates(plat):
    src = (COMP / f"{plat}.py").read_text()
    assert "PARALLEL_UPDATES = 0" in src
    assert "entry: DaikinCycleMLConfigEntry" in src and "AddConfigEntryEntitiesCallback" in src
    assert "type DaikinCycleMLConfigEntry = ConfigEntry[DaikinCycleMLCoordinator]" in (COMP / "coordinator.py").read_text()


def test_binary_sensor_category_and_disabled_default_reach_the_entity():
    coord = MagicMock()
    coord.entry.entry_id = "e"
    coord.entry.data = {}
    s = DaikinCycleMLBinarySensor(coord, "boiler_dhw_demand", "x", lambda snap, c: True,
                                  entity_category=EntityCategory.DIAGNOSTIC, enabled_default=False)
    assert s.entity_category == EntityCategory.DIAGNOSTIC and s.entity_registry_enabled_default is False
    plain = DaikinCycleMLBinarySensor(coord, "short_run", "x", lambda snap, c: True)
    assert plain.entity_category is None and plain.entity_registry_enabled_default is True
