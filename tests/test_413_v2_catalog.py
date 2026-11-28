"""#413: ESPAltherma v2 names follow data/catalog_names.txt.

v2 publishes a name that exists on both the outdoor and the indoor
registries with its side ("I/U Thermostat ON/OFF"), so the v2 source is
checked against the catalog snapshot docs/ESPALTHERMA_V2_CATALOG.json.
v1 keeps the definition names (docs/MODEL_ATTRIBUTES.json).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.const import (
    CONSUMED_ATTRIBUTES,
    REQUIRED_ATTRIBUTES,
)
from custom_components.daikin_cycle_ml.engine.attribute_compat import (
    build_compat_view,
    side_names,
    unsided_name,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector,
    classify_mode,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
    _slug_variants,
    resolve_attrs,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
    make_json_key,
)
from tools import parse_espaltherma_catalog as tool

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "docs" / "ESPALTHERMA_V2_CATALOG.json"
CATALOG = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
DEFS: dict[str, list[str]] = CATALOG["definitions"]
EXTRAS: list[str] = CATALOG["extras"]
ALL_KEYS = {make_json_key(n) for n in tool.all_names(CATALOG)}

# Definitions without the v2 water/compressor values (#189 HT aliases,
# #175 HT defaults, Protocol S placeholders).
KNOWN_GAPS = frozenset({
    "Altherma(HT EKHBRD-ERRQ series 11-16kW)",
    "Altherma(HT EKHBRD-ERRQ series 11-16kW protocol S)",
    "Altherma(HT EKHBRD-ERRQ series 11-16kW protocols I and S)",  # #511
    "Altherma(HT ERRQ-ERSQ outdoor unit 11-16kW)",
    "PROTOCOL_S",
    "PROTOCOL_S_ROTEX",
})
# Computed by the integration ("COP") or a firmware typo of a Stats value.
NOT_PUBLISHED = frozenset({"COP", "Stats: Electricalinput estimated (kW)"})


def _keys(names: list[str]) -> set[str]:
    return {make_json_key(n) for n in names}


# --- snapshot ---------------------------------------------------------------


def test_snapshot_meta_pins_a_commit():
    meta = CATALOG["_meta"]
    assert re.fullmatch(r"[0-9a-f]{40}", meta["commit"])
    assert meta["branch"] == "beta" and meta["file"] == "data/catalog_names.txt"
    assert len(DEFS) >= 30
    assert "Stats: Compressor run today (min)" in EXTRAS


def test_bracketed_value_names_are_not_sections():
    assert "[HPSU] Tv inflow Temp  (R1T)" not in DEFS
    assert any("[HPSU] Tv inflow Temp  (R1T)" in v for v in DEFS.values())


def test_catalog_has_the_side_renames():
    names = tool.all_names(CATALOG)
    assert "Thermostat ON/OFF" not in names
    assert set(side_names("Thermostat ON/OFF")) <= names


# --- contract: what the v2 resolver reads exists in the catalog ---------------


@pytest.mark.parametrize("definition", sorted(set(DEFS) - KNOWN_GAPS))
def test_required_values_resolve_per_definition(definition):
    keys = _keys(DEFS[definition])
    missing = [
        label for label in REQUIRED_ATTRIBUTES
        if not any(s in keys for s in _slug_variants(label))
    ]
    assert not missing, f"{definition}: {missing}"


def test_known_gaps_still_exist():
    # drop an entry here once upstream publishes the values
    for definition in KNOWN_GAPS:
        keys = _keys(DEFS[definition])
        assert not all(
            any(s in keys for s in _slug_variants(label)) for label in REQUIRED_ATTRIBUTES
        ), definition


@pytest.mark.parametrize("label", [c for c in CONSUMED_ATTRIBUTES if c not in NOT_PUBLISHED])
def test_every_consumed_value_is_published_somewhere(label):
    assert any(s in ALL_KEYS for s in _slug_variants(label)), label


def _referenced_ids() -> dict[str, set[str]]:
    out = subprocess.run(
        ["git", "grep", "-noE", r"(binary_)?sensor\.espaltherma_[a-z0-9_]+", "--",
         "custom_components", "dashboard", "docs", "README.md"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout
    refs: dict[str, set[str]] = {}
    for line in out.splitlines():
        path, _, match = line.split(":", 2)
        refs.setdefault(match.split(".", 1)[1][len("espaltherma_"):], set()).add(path)
    return refs


def test_card_and_doc_entity_ids_exist_in_v2():
    refs = _referenced_ids()
    assert refs, "git grep found no espaltherma ids"
    # a trailing "_" is a prefix match (const: sensor.espaltherma_stats_)
    unknown = {
        slug: sorted(paths) for slug, paths in refs.items()
        if slug not in ALL_KEYS
        and not (slug.endswith("_") and any(k.startswith(slug) for k in ALL_KEYS))
    }
    assert not unknown, unknown


# --- side-name fallback -------------------------------------------------------


def test_side_names_order_and_guards():
    assert side_names("Defrost Operation") == ("I/U Defrost Operation", "O/U Defrost Operation")
    assert side_names("I/U operation mode") == ()
    # "I/U Operation Mode" would be the id of the distinct "I/U operation mode"
    assert side_names("Operation Mode") == ("O/U Operation Mode",)


def test_slug_variants_put_side_names_last():
    v = _slug_variants("Defrost Operation")
    assert v[0] == "defrost_operation" and v[1] == "abtauung"
    assert v[-4:] == ["iu_defrost_operation", "ou_defrost_operation",
                      "iu_abtauung", "ou_abtauung"]
    assert "iu_operation_mode" not in _slug_variants("Operation Mode")


def test_unsided_name():
    assert unsided_name("I/U Thermostat ON/OFF") == "Thermostat ON/OFF"
    assert unsided_name("O/U Error type") == "Error type"
    assert unsided_name("I/U operation mode") is None
    assert unsided_name("Thermostat ON/OFF") is None


def test_compat_view_maps_side_names_indoor_first():
    view = build_compat_view({
        "O/U Defrost Operation": 0, "I/U Defrost Operation": 1,
        "I/U Thermostat ON/OFF": "ON",
    })
    assert view["Defrost Operation"] == 1
    assert view["Abtauung"] == 1                      # alias group follows
    assert view["Thermostat ON/OFF"] == "ON"
    assert view["Thermostat EIN/AUS"] == "ON"


def test_compat_view_plain_name_wins_and_real_names_untouched():
    view = build_compat_view({"Error Code": 0, "I/U Error Code": 89,
                              "I/U operation mode": "Heating"})
    assert view["Error Code"] == 0
    assert "Operation Mode" not in view and "operation mode" not in view


def test_resolver_reads_side_renamed_entity(hass):
    hass.states.async_set("sensor.espaltherma_iu_defrost_operation", "1")
    hass.states.async_set("sensor.espaltherma_ou_defrost_operation", "0")
    hass.states.async_set("sensor.espaltherma_iu_operation_mode", "Heating")
    result = resolve_attrs(hass)
    assert result.attrs["Defrost Operation"] == 1
    assert result.attrs["I/U operation mode"] == "Heating"
    assert "Operation Mode" not in result.attrs


# --- cooling (v1 and v2) -------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Cooling", "cooling"), ("Auto Cool", "cooling"), ("Cooling Storage", "cooling"),
        ("Heating", "heating"), ("Auto Heat", "heating"), ("Heating Storage", "heating"),
        ("Cooling + DHW", "dhw"), ("Heating + DHW", "dhw"), ("DHW", "dhw"),
        ("Stop", "unknown"), ("Fan Only", "unknown"), ("??", "unknown"),
    ],
)
def test_operation_mode_values(value, expected):
    assert classify_mode({"Operation Mode": value}) == expected


def test_iu_stop_falls_back_to_operation_mode():
    assert classify_mode({"I/U operation mode": "Stop", "Operation Mode": "Auto Cool"}) == "cooling"


@pytest.mark.parametrize(
    "attrs,expected",
    [
        ({"Operation Mode": "Cooling"}, "cooling"),
        ({"Operation Mode": "Auto Cool"}, "cooling"),
        ({"Operation Mode": "Heating"}, "heating"),
        ({"I/U operation mode": "Heating + DHW"}, "heating"),   # no tank: never DHW
        ({}, "heating"),
    ],
)
def test_no_dhw_install_keeps_cooling(attrs, expected):
    assert CycleDetector({}, dhw_present=False)._classify_mode(attrs) == expected


# --- tool ---------------------------------------------------------------------


def test_parse_catalog_text():
    text = "# header\n\n[Model A]\nB\n[HPSU] x\nA\n[Model B]\nA\n"
    assert tool.parse_catalog_text(text) == {"Model A": ["A", "B", "[HPSU] x"], "Model B": ["A"]}
    with pytest.raises(ValueError):
        tool.parse_catalog_text("orphan\n")


def _fake_source(tmp_path: Path, catalog: str) -> Path:
    src = tmp_path / "esp"
    (src / "data").mkdir(parents=True)
    (src / "src").mkdir()
    (src / "data" / "catalog_names.txt").write_text(catalog, encoding="utf-8")
    (src / "src" / "main.cpp").write_text(
        'const HaSensor x[] = {{"Stats: Defrosts today", ESP_SENSOR_COUNT}};\n', encoding="utf-8")
    return src


def test_build_and_main(tmp_path, capsys):
    src = _fake_source(tmp_path, "[M]\nDefrost Operation\n")
    out = tmp_path / "cat.json"
    assert tool.main(["--source", str(src), "--branch", "beta", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["definitions"] == {"M": ["Defrost Operation"]}
    assert data["extras"] == ["Stats: Defrosts today"]
    assert data["_meta"]["commit"] == "unknown"       # not a git checkout
    assert "1 definitions" in capsys.readouterr().out


def test_build_needs_catalog(tmp_path):
    with pytest.raises(SystemExit):
        tool.build(tmp_path, "beta")


def test_main_requires_arguments():
    with pytest.raises(SystemExit):
        tool.main([])


def test_diff_flags_removed_consumed(tmp_path, capsys):
    old = {"definitions": {"M": ["Defrost Operation", "Pump"], "Gone": ["X"]}, "extras": []}
    new = {"definitions": {"M": ["I/U Defrost Operation", "Pump"], "New": ["Y"]}, "extras": []}
    d = tool.diff(old, new, tool.consumed_names(ROOT))
    assert d["removed_consumed"] == ["Defrost Operation"]
    assert d["added"] == ["I/U Defrost Operation", "Y"]
    assert d["removed_per_definition"] == {"M": ["Defrost Operation"]}
    assert d["definitions_removed"] == ["Gone"] and d["definitions_added"] == ["New"]
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(old), encoding="utf-8")
    b.write_text(json.dumps(new), encoding="utf-8")
    assert tool.main(["--diff", str(a), str(b)]) == 0
    md = capsys.readouterr().out
    assert "action needed" in md and "- `Defrost Operation`" in md


def test_diff_markdown_empty():
    md = tool.diff_markdown(tool.diff(CATALOG, CATALOG, set()))
    assert md.count("- none") == 5


def test_consumed_names_include_side_names():
    names = tool.consumed_names(ROOT)
    assert {"Defrost Operation", "I/U Defrost Operation", "R1T-Outdoor air temp."} <= names
