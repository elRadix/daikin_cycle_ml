"""Tests for daily_summary_live_enabled toggle (v1.7.0, #42)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


BASE = Path("custom_components/daikin_cycle_ml")


def test_default_constant_true():
    from custom_components.daikin_cycle_ml.const import (
        DEFAULT_DAILY_SUMMARY_LIVE_ENABLED,
    )
    assert DEFAULT_DAILY_SUMMARY_LIVE_ENABLED is True


def test_option_key_literal():
    from custom_components.daikin_cycle_ml.const import (
        OPTION_DAILY_SUMMARY_LIVE_ENABLED,
    )
    assert OPTION_DAILY_SUMMARY_LIVE_ENABLED == "daily_summary_live_enabled"


def test_strings_parity_three_files():
    paths = [
        BASE / "strings.json",
        BASE / "translations" / "en.json",
        BASE / "translations" / "nl.json",
    ]
    for p in paths:
        text = p.read_text()
        n = text.count('"daily_summary_live_enabled"')
        assert n >= 2, f"only {n} occurrences in {p}"


def test_config_flow_source_contains_schema_key():
    src = (BASE / "config_flow.py").read_text()
    assert "daily_summary_live_enabled" in src
    assert "DEFAULT_DAILY_SUMMARY_LIVE_ENABLED" in src
