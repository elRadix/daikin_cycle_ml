import json
from pathlib import Path
from types import SimpleNamespace

from custom_components.daikin_cycle_ml.engine.attribute_compat import (
    build_compat_view,
    detect_schema,
    normalize_key,
)
from custom_components.daikin_cycle_ml.engine.attribute_reader import read

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components" / "daikin_cycle_ml" / "manifest.json"


def test_categories_present_and_bounded():
    cats = json.loads(MANIFEST.read_text())["categories"]
    assert cats == ["climate.heat_pumps_air_conditioning", "energy"]
    assert 1 <= len(cats) <= 3


def test_v2_input_keeps_legacy_keys():
    v2 = {
        "Leaving water temp. before BUH (R1T)": 28,
        "Inlet water temp.(R4T)": 25.5,
        "Flow sensor (l/min)": 12.4,
    }
    view = build_compat_view(v2)
    assert view["Inlet water temp.(R4T)"] == 25.5
    assert view["Inlet water temp. (R4T)"] == 25.5
    assert view["Leaving water temp. before BUH (R1T)"] == 28
    assert view["Leaving water temp.(R1T)"] == 28


def test_v1_input_adds_v2_keys():
    v1 = {"Inlet water temp. (R4T)": 25.5}
    view = build_compat_view(v1)
    assert view["Inlet water temp. (R4T)"] == 25.5
    assert view["Inlet water temp.(R4T)"] == 25.5


def test_translated_legacy_alias():
    view = build_compat_view({"Vorlauf vor BUH (R1T)": 28.0})
    assert view["Leaving water temp. before BUH (R1T)"] == 28.0
    assert view["Vorlauf vor BUH (R1T)"] == 28.0


def test_both_present_each_keeps_own_value():
    view = build_compat_view({
        "Inlet water temp. (R4T)": 25.0,
        "Inlet water temp.(R4T)": 26.0,
    })
    assert view["Inlet water temp. (R4T)"] == 25.0
    assert view["Inlet water temp.(R4T)"] == 26.0


def test_fallback_normalized_match():
    view = build_compat_view({"Inlet water temp.  (R4T)": 25.0})
    assert view["Inlet water temp.(R4T)"] == 25.0


def test_empty_input_returns_empty():
    assert build_compat_view({}) == {}


def test_unrelated_keys_unchanged():
    view = build_compat_view({"Foo": 1, "Bar": 2})
    assert view == {"Foo": 1, "Bar": 2}


def test_detect_schema():
    assert detect_schema({
        "Leaving water temp. before BUH (R1T)": 1,
        "Leaving water temp. after BUH (R2T)": 2,
        "Inlet water temp.(R4T)": 3,
    }) == "espaltherma_v2"
    assert detect_schema({"Inlet water temp. (R4T)": 3}) == "espaltherma_v1"
    assert detect_schema({"Foo": 1}) == "unknown"


def test_normalize_equivalence():
    assert normalize_key("Inlet water temp. (R4T)") == normalize_key(
        "Inlet water temp.(R4T)"
    )
    assert normalize_key("3-Way Valve") == normalize_key("3way valve")


def test_read_accepts_v2_state():
    state = SimpleNamespace(attributes={
        "Inlet water temp.(R4T)": "25.5",
        "Flow sensor (l/min)": "12.4",
        "INV frequency (rps)": "42",
    })
    out = read(state)
    assert out["Inlet water temp.(R4T)"] == 25.5
    assert out["Inlet water temp. (R4T)"] == 25.5
    assert out["Flow sensor (l/min)"] == 12.4


def test_read_still_honors_custom_map():
    state = SimpleNamespace(attributes={
        "Inlet water temp. (R4T)": "25.5",
        "Custom Inlet": "25.5",
    })
    out = read(state, custom_map={"Inlet water temp.(R4T)": "Custom Inlet"})
    assert out["Inlet water temp.(R4T)"] == 25.5
    assert "Custom Inlet" not in out
