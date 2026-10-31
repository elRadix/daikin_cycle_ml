"""Marketplace + Gold-tier compliance tests."""
from __future__ import annotations

import json
import pathlib
import re

import pytest


REPO_ROOT = pathlib.Path(__file__).parent.parent
COMPONENT_DIR = REPO_ROOT / "custom_components" / "daikin_cycle_ml"


def test_manifest_has_all_marketplace_fields():
    data = json.loads((COMPONENT_DIR / "manifest.json").read_text())
    required = ["domain", "name", "version", "documentation",
                "issue_tracker", "codeowners", "categories",
                "quality_scale", "iot_class", "integration_type"]
    for field in required:
        assert field in data, f"manifest.json missing {field!r}"
    assert data["issue_tracker"].startswith("https://")
    assert isinstance(data["codeowners"], list)
    assert len(data["codeowners"]) >= 1
    assert all(c.startswith("@") for c in data["codeowners"])
    assert data["quality_scale"] in ("bronze", "silver", "gold", "platinum")


def test_hacs_json_exists_and_valid():
    hacs = REPO_ROOT / "hacs.json"
    assert hacs.exists()
    data = json.loads(hacs.read_text())
    assert "name" in data


def test_quality_scale_yaml_present():
    qs = COMPONENT_DIR / "quality_scale.yaml"
    assert qs.exists()
    content = qs.read_text()
    assert "rules:" in content
    assert "config-flow:" in content
    assert "diagnostics:" in content


def test_translation_keys_match():
    import json as _json
    en = _json.loads((COMPONENT_DIR / "translations" / "en.json").read_text())
    nl = _json.loads((COMPONENT_DIR / "translations" / "nl.json").read_text())
    def _keys(d, prefix=""):
        out = set()
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out |= _keys(v, key)
            else:
                out.add(key)
        return out
    en_keys = _keys(en)
    nl_keys = _keys(nl)
    assert not (en_keys - nl_keys), f"Missing in nl: {en_keys - nl_keys}"
    assert not (nl_keys - en_keys), f"Missing in en: {nl_keys - en_keys}"


def test_strings_json_and_translations_en_match():
    import json as _json
    strings = _json.loads((COMPONENT_DIR / "strings.json").read_text())
    en = _json.loads((COMPONENT_DIR / "translations" / "en.json").read_text())
    def _keys(d, prefix=""):
        out = set()
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out |= _keys(v, key)
            else:
                out.add(key)
        return out
    s_keys = _keys(strings)
    e_keys = _keys(en)
    assert not (s_keys - e_keys), f"In strings not en: {s_keys - e_keys}"
    assert not (e_keys - s_keys), f"In en not strings: {e_keys - s_keys}"


def test_version_consistency_across_three_files():
    import json as _json
    manifest = _json.loads((COMPONENT_DIR / "manifest.json").read_text())
    v_manifest = manifest["version"]
    const_text = (COMPONENT_DIR / "const.py").read_text()
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', const_text, re.MULTILINE)
    assert m
    v_const = m.group(1)
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text()
    m2 = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
    assert m2
    v_pyproject = m2.group(1)
    assert v_manifest == v_const
    assert v_manifest == v_pyproject


def test_brand_assets_present():
    brand = COMPONENT_DIR / "brand"
    assert brand.exists()
    assert (brand / "icon.png").exists() or (brand / "icon.svg").exists()
    assert (brand / "logo.png").exists() or (brand / "logo.svg").exists()


def test_icons_json_present_and_parses():
    import json as _json
    icons = COMPONENT_DIR / "translations" / "icons.json"
    assert icons.exists()
    data = _json.loads(icons.read_text())
    assert "entity" in data
