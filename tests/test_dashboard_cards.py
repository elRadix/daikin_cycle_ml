"""Dashboard card integrity: YAML parses, i18n complete."""
from __future__ import annotations

import pathlib
import re

import pytest


REPO_ROOT = pathlib.Path(__file__).parent.parent
CARDS_DIR = REPO_ROOT / "dashboard" / "cards"


def _all_yaml_files():
    if not CARDS_DIR.exists():
        return []
    return list(CARDS_DIR.rglob("*.yaml"))


def test_all_yaml_files_parse():
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")
    files = _all_yaml_files()
    if not files:
        pytest.skip("no dashboard YAML files")
    for f in files:
        try:
            with open(f) as fh:
                yaml.safe_load(fh)
        except yaml.YAMLError as e:
            pytest.fail(f"{f.name} is invalid YAML: {e}")


def test_daily_summary_card_exists():
    card = CARDS_DIR / "daily-summary-tabbed" / "daily-summary-tabbed.yaml"
    assert card.exists()


def test_card_has_i18n_dict():
    card = CARDS_DIR / "daily-summary-tabbed" / "daily-summary-tabbed.yaml"
    if not card.exists():
        pytest.skip("card not found")
    content = card.read_text()
    assert "var I18N = {" in content
    assert "r_maxdur" in content


def test_card_i18n_has_nl_and_en():
    card = CARDS_DIR / "daily-summary-tabbed" / "daily-summary-tabbed.yaml"
    if not card.exists():
        pytest.skip("card not found")
    content = card.read_text()
    pattern = r"\{\s*nl:\s*'[^']+'\s*,\s*en:\s*'[^']+'\s*\}"
    matches = re.findall(pattern, content)
    assert len(matches) > 20
    nl_only = re.findall(r"\{\s*nl:\s*'[^']+'\s*,\s*(?!en:)[a-z_]+:", content)
    assert not nl_only, f"I18N entries without en: {nl_only}"


def test_card_uses_ha_variables_for_colors():
    card = CARDS_DIR / "daily-summary-tabbed" / "daily-summary-tabbed.yaml"
    if not card.exists():
        pytest.skip("card not found")
    content = card.read_text()
    violations = []
    if re.search(r"\.pa-tab\s*\{[^}]*background:\s*#fff", content):
        violations.append("pa-tab hardcoded #fff")
    if re.search(r"\.pa-block\s*\{[^}]*background:\s*white", content):
        violations.append("pa-block hardcoded white")
    assert not violations, f"Dark-mode violations: {violations}"
