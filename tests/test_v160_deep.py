"""Deep tests for v1.6.0 (C1a + C1b + C2).

Runtime import strategy:
  - custom_components.* imports are at MODULE level so they resolve at
    pytest collect-time, BEFORE PHACC's fixtures install a mock
    `custom_components` in sys.modules.
  - `test_all_modules_import_cleanly_in_subprocess` spawns a fresh Python
    process (no PHACC state) to verify real import cleanliness.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# === Module-level imports (must resolve before PHACC mocks) ===
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.sensor import (
    SENSOR_DEFS,
    _attrs_cop_hourly_mode,
    _cop_hourly_mode_mean,
)

REPO = Path(__file__).parent.parent
CC = REPO / "custom_components" / "daikin_cycle_ml"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _load_json(fn: str):
    return json.loads((CC / fn).read_text())


# ================================================================
# 1. SENSOR_DEFS contract
# ================================================================

def test_contract_all_have_key_name_value_fn():
    for sd in SENSOR_DEFS:
        assert isinstance(sd.get("key"), str) and sd["key"], sd
        assert isinstance(sd.get("name"), str) and sd["name"], sd
        assert callable(sd.get("value_fn")), sd["key"]


def test_contract_attr_fn_callable_when_present():
    for sd in SENSOR_DEFS:
        if "attr_fn" in sd:
            assert callable(sd["attr_fn"]), sd["key"]


def test_contract_keys_unique():
    keys = [sd["key"] for sd in SENSOR_DEFS]
    assert len(keys) == len(set(keys))


def test_contract_keys_english_only():
    # Dutch-only words (unambiguous, cannot appear in an English slug).
    # Note: 'week' is intentionally EXCLUDED — identical spelling EN/NL.
    dutch_only = ("vandaag", "stooklijn", "advies", "koeling", "verwarming",
                  "seizoen", "maand", "dag", "buiten", "warmte")
    for sd in SENSOR_DEFS:
        for w in dutch_only:
            assert w not in sd["key"], f"Dutch {w!r} in key {sd['key']!r}"


def test_contract_unit_implies_state_class():
    for sd in SENSOR_DEFS:
        if sd.get("unit"):
            assert sd.get("state_class"), f"{sd['key']} unit but no state_class"


def test_contract_count_27():
    assert len(SENSOR_DEFS) == 30


# ================================================================
# 2. Slug parity
# ================================================================

LEGACY_SLUG_ALLOWLIST = {
    "cop_mean_day", "cop_mean_week", "cop_mean_month", "cop_curve_recent",
}


def test_slug_parity_all_keys():
    mismatches = []
    for sd in SENSOR_DEFS:
        got = _slug(sd["name"])
        if got != sd["key"] and sd["key"] not in LEGACY_SLUG_ALLOWLIST:
            mismatches.append((sd["key"], sd["name"], got))
    assert not mismatches, f"slug mismatches: {mismatches}"


# ================================================================
# 3. Translations parity
# ================================================================

@pytest.mark.parametrize("fn", [
    "strings.json", "translations/en.json", "translations/nl.json",
])
def test_all_sensor_defs_in_translations(fn):
    d = _load_json(fn)
    trans = d.get("entity", {}).get("sensor", {})
    missing = [sd["key"] for sd in SENSOR_DEFS if sd["key"] not in trans]
    assert not missing, f"missing in {fn}: {missing}"


@pytest.mark.parametrize("fn", [
    "strings.json", "translations/en.json", "translations/nl.json",
])
def test_translation_sensor_entries_have_name(fn):
    d = _load_json(fn)
    for key, val in d.get("entity", {}).get("sensor", {}).items():
        assert isinstance(val.get("name"), str) and val["name"], f"{key} in {fn}"


def test_nl_and_en_have_same_sensor_keys():
    en = _load_json("translations/en.json")
    nl = _load_json("translations/nl.json")
    en_k = set(en.get("entity", {}).get("sensor", {}).keys())
    nl_k = set(nl.get("entity", {}).get("sensor", {}).keys())
    assert en_k == nl_k, f"EN-NL mismatch: {en_k ^ nl_k}"


def test_strings_matches_en():
    s = _load_json("strings.json")
    en = _load_json("translations/en.json")
    s_k = set(s.get("entity", {}).get("sensor", {}).keys())
    en_k = set(en.get("entity", {}).get("sensor", {}).keys())
    assert s_k == en_k, f"strings-en mismatch: {s_k ^ en_k}"


def test_options_maintenance_has_season_in_all_3():
    for fn in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = _load_json(fn)
        step = d.get("options", {}).get("step", {}).get("maintenance", {})
        assert "season_start_month" in step.get("data", {}), f"data missing in {fn}"
        assert "season_start_month" in step.get("data_description", {}), f"desc missing in {fn}"


# ================================================================
# 4. Runtime imports — fresh subprocess (no PHACC)
# ================================================================

ALL_MODULES = [
    "custom_components.daikin_cycle_ml",
    "custom_components.daikin_cycle_ml.api",
    "custom_components.daikin_cycle_ml.binary_sensor",
    "custom_components.daikin_cycle_ml.config_flow",
    "custom_components.daikin_cycle_ml.const",
    "custom_components.daikin_cycle_ml.coordinator",
    "custom_components.daikin_cycle_ml.diagnostics",
    "custom_components.daikin_cycle_ml.entity",
    "custom_components.daikin_cycle_ml.repairs",
    "custom_components.daikin_cycle_ml.sensor",
    "custom_components.daikin_cycle_ml.services",
    "custom_components.daikin_cycle_ml.engine.action_engine",
    "custom_components.daikin_cycle_ml.engine.anomaly_engine",
    "custom_components.daikin_cycle_ml.engine.attribute_reader",
    "custom_components.daikin_cycle_ml.engine.cop_analyzer",
    "custom_components.daikin_cycle_ml.engine.cycle_detector",
    "custom_components.daikin_cycle_ml.engine.model_profiles",
    "custom_components.daikin_cycle_ml.engine.notification_engine",
    "custom_components.daikin_cycle_ml.engine.quality_scorer",
    "custom_components.daikin_cycle_ml.engine.status_report",
    "custom_components.daikin_cycle_ml.engine.thermal",
    "custom_components.daikin_cycle_ml.engine.timer_health",
    "custom_components.daikin_cycle_ml.ml.adaptive_thresholds",
    "custom_components.daikin_cycle_ml.ml.baseline",
    "custom_components.daikin_cycle_ml.ml.clustering",
    "custom_components.daikin_cycle_ml.ml.features",
    "custom_components.daikin_cycle_ml.ml.multi_baseline",
    "custom_components.daikin_cycle_ml.storage.db",
    "custom_components.daikin_cycle_ml.storage.store",
]


def test_all_modules_import_cleanly_in_subprocess():
    """Fresh Python process imports all 29 modules — no PHACC, no test state."""
    code = "\n".join(f"import {m}" for m in ALL_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (
        f"subprocess import failed (rc={result.returncode})\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


# ================================================================
# 5. Hypothesis fuzz — pure factories (uses module-level imports)
# ================================================================

@given(
    mode=st.sampled_from(["heating", "dhw", "cooling", "unknown", ""]),
    period=st.sampled_from(["day", "week", "month"]),
    val=st.one_of(
        st.none(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=10),
        st.integers(-100, 100),
    ),
)
@settings(max_examples=50, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_fuzz_cop_hourly_mode_mean(mode, period, val):
    snap = SimpleNamespace(**{
        f"cop_hourly_{period}": {"by_mode": {mode: {"cop_mean": val}}},
    })
    fn = _cop_hourly_mode_mean(mode, period)
    fn(snap, MagicMock())  # must not raise


@given(
    mode=st.sampled_from(["heating", "dhw", "cooling", "unknown"]),
    period=st.sampled_from(["day", "week", "month"]),
)
@settings(max_examples=30, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_fuzz_attrs_cop_hourly_mode(mode, period):
    snap = SimpleNamespace(**{f"cop_hourly_{period}": {}})
    fn = _attrs_cop_hourly_mode(mode, period)
    result = fn(snap, MagicMock())
    assert isinstance(result, dict)
    assert result["mode"] == mode
    assert result["period"] == period


# ================================================================
# 6. SPF season boundary (uses module-level DaikinCycleMLCoordinator)
# ================================================================

def _mk_spf_coord(opts):
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_fetch_cop_samples_between = AsyncMock(return_value=[])
    c.db.async_set_model_state = AsyncMock()
    c.options = opts
    c._spf_state_cache = {}
    return c


@pytest.mark.asyncio
async def test_spf_season_year_rolls_back_when_start_after_now():
    c = _mk_spf_coord({"season_start_month": 10})
    now = time.mktime((2026, 3, 15, 12, 0, 0, 0, 0, -1))
    await c._refresh_spf_state(now)
    calls = c.db.async_fetch_cop_samples_between.await_args_list
    assert len(calls) >= 1
    lt = time.localtime(calls[0].args[0])
    assert lt.tm_year == 2025
    assert lt.tm_mon == 10
    assert lt.tm_mday == 1


@pytest.mark.asyncio
async def test_spf_season_same_year_when_start_before_now():
    c = _mk_spf_coord({"season_start_month": 1})
    now = time.mktime((2026, 3, 15, 12, 0, 0, 0, 0, -1))
    await c._refresh_spf_state(now)
    calls = c.db.async_fetch_cop_samples_between.await_args_list
    lt = time.localtime(calls[0].args[0])
    assert lt.tm_year == 2026
    assert lt.tm_mon == 1


@pytest.mark.asyncio
async def test_spf_season_december_rolls_back_from_january():
    c = _mk_spf_coord({"season_start_month": 12})
    now = time.mktime((2026, 1, 5, 12, 0, 0, 0, 0, -1))
    await c._refresh_spf_state(now)
    calls = c.db.async_fetch_cop_samples_between.await_args_list
    lt = time.localtime(calls[0].args[0])
    assert lt.tm_year == 2025
    assert lt.tm_mon == 12


@pytest.mark.asyncio
async def test_spf_ytd_always_current_year():
    c = _mk_spf_coord({"season_start_month": 10})
    now = time.mktime((2026, 3, 15, 12, 0, 0, 0, 0, -1))
    await c._refresh_spf_state(now)
    calls = c.db.async_fetch_cop_samples_between.await_args_list
    lt = time.localtime(calls[1].args[0])
    assert lt.tm_year == 2026
    assert lt.tm_mon == 1
    assert lt.tm_mday == 1


# ================================================================
# 7. C1b combined — edge filters
# ================================================================

def _mk_combined_coord(rows_today, rows_week=None):
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_fetch_cop_samples = AsyncMock(
        side_effect=lambda days: rows_today if days == 1 else (rows_week or rows_today)
    )
    c._cop_today_cache = {}
    c._cop_today_heating_cache = {}
    return c


def _today_start():
    lt = time.localtime()
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


@pytest.mark.asyncio
async def test_combined_filter_cooling_kept_in_blended_only():
    ts = _today_start() + 3600
    rows = [
        {"ts": ts, "cop": 4.0, "mode": "cooling"},
        {"ts": ts, "cop": 6.0, "mode": "cooling"},
    ]
    c = _mk_combined_coord(rows)
    await c._refresh_cop_today(ts + 1)
    assert c._cop_today_heating_cache == {}
    assert c._cop_today_cache["cop"] == 5.0
    assert c._cop_today_cache["samples_today"] == 2


@pytest.mark.asyncio
async def test_combined_unknown_mode_only_in_blended():
    ts = _today_start() + 3600
    rows = [
        {"ts": ts, "cop": 3.0, "mode": "unknown"},
        {"ts": ts, "cop": 5.0, "mode": "unknown"},
    ]
    c = _mk_combined_coord(rows)
    await c._refresh_cop_today(ts + 1)
    assert c._cop_today_heating_cache == {}
    assert c._cop_today_cache["cop"] == 4.0


@pytest.mark.asyncio
async def test_combined_rows_before_today_are_excluded():
    today_start = _today_start()
    rows = [
        {"ts": today_start - 86400, "cop": 99.0, "mode": "heating"},
        {"ts": today_start + 3600, "cop": 4.0, "mode": "heating"},
    ]
    c = _mk_combined_coord(rows)
    await c._refresh_cop_today(today_start + 7200)
    assert c._cop_today_heating_cache["cop"] == 4.0
    assert c._cop_today_heating_cache["samples_today"] == 1
    assert c._cop_today_cache["cop"] == 4.0


@pytest.mark.asyncio
async def test_combined_week_fetch_fallback_to_today_rows():
    ts = _today_start() + 3600
    today_rows = [{"ts": ts, "cop": 4.0, "mode": "heating"}]
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()

    async def _fetch(days):
        if days == 1:
            return today_rows
        raise RuntimeError("week fetch fail")

    c.db.async_fetch_cop_samples = AsyncMock(side_effect=_fetch)
    c._cop_today_cache = {}
    c._cop_today_heating_cache = {}
    await c._refresh_cop_today(ts + 1)
    assert c._cop_today_heating_cache["cop"] == 4.0
    assert c._cop_today_heating_cache["baseline_cop_verlies_pct"] == 0.0


@pytest.mark.asyncio
async def test_combined_string_cop_filtered():
    ts = _today_start() + 3600
    rows = [
        {"ts": ts, "cop": "nan", "mode": "heating"},
        {"ts": ts, "cop": 5.0, "mode": "heating"},
    ]
    c = _mk_combined_coord(rows)
    await c._refresh_cop_today(ts + 1)
    assert c._cop_today_heating_cache["cop"] == 5.0
    assert c._cop_today_heating_cache["samples_today"] == 1


@pytest.mark.asyncio
async def test_combined_negative_cop_filtered():
    ts = _today_start() + 3600
    rows = [
        {"ts": ts, "cop": -1.0, "mode": "heating"},
        {"ts": ts, "cop": 0.0, "mode": "heating"},
        {"ts": ts, "cop": 4.0, "mode": "heating"},
    ]
    c = _mk_combined_coord(rows)
    await c._refresh_cop_today(ts + 1)
    assert c._cop_today_heating_cache["cop"] == 4.0
    assert c._cop_today_heating_cache["samples_today"] == 1
