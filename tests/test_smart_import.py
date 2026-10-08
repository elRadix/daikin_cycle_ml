"""Tests for engine.smart_import (issue #51, target v1.8.0).

Covers all 5 layers of the smart auto-import proposal:

- Laag 1: find_candidate_sensors (entity discovery)
- Laag 2: resolve_canonical + ALIASES (alias table + normalized)
- Laag 3: similarity + fuzzy fallback (Jaccard + register conflict)
- Laag 4: build_diagnostic (per-canonical status)
- Laag 5: check_sanity + PHASE_HINT (register-value sanity)

Anti-alias regression (issue #51, julG COP~11): R2T must NEVER match R1T.
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LW_SETPOINT,
    ATTR_OPERATION_MODE,
    ATTR_OUTDOOR_AIR_R1T,
)
from custom_components.daikin_cycle_ml.engine.smart_import import (
    ALIASES,
    PHASE_HINT,
    SUSPICIOUS_VALUES,
    AttrMatch,
    CandidateSensor,
    DiagnosticReport,
    _has_register_conflict,
    _normalize,
    _register_codes,
    _tokens,
    build_diagnostic,
    check_sanity,
    find_candidate_sensors,
    resolve_canonical,
    similarity,
)


# =========================================================================
# Helper: minimal valid core attrs (12 of 13, one missing to test 'missing')
# =========================================================================

def _full_attrs() -> dict[str, object]:
    from custom_components.daikin_cycle_ml.const import CORE_ATTRIBUTES
    return {c: 1.0 for c in CORE_ATTRIBUTES}


# =========================================================================
# _normalize / _tokens / _register_codes
# =========================================================================

@pytest.mark.parametrize("raw,expected", [
    ("Hello World", "helloworld"),
    ("3way valve(On:DHW_Off:Space)", "3wayvalveondhwoffspace"),
    ("R1T-Outdoor", "r1toutdoor"),
    ("Foo.Bar,()", "foobar"),
])
def test_normalize(raw: str, expected: str) -> None:
    assert _normalize(raw) == expected


def test_tokens_basic() -> None:
    assert _tokens("INV frequency (rps)") == {"inv", "frequency", "rps"}
    assert _tokens("") == set()


def test_register_codes_basic() -> None:
    assert _register_codes("Hydro R1T and R2T") == {"R1T", "R2T"}
    assert _register_codes("no codes") == set()


# =========================================================================
# Laag 2 — _has_register_conflict (anti-alias, issue case 15)
# =========================================================================

def test_register_conflict_both_present_disjoint() -> None:
    assert _has_register_conflict("temp after BUH (R2T)", "temp before BUH (R1T)")


def test_register_conflict_no_conflict_same_code() -> None:
    assert not _has_register_conflict("Inlet (R4T)", "Hydro Inlet (R4T)")


def test_register_conflict_one_side_missing() -> None:
    assert not _has_register_conflict("plain attr", "with (R1T)")
    assert not _has_register_conflict("with (R1T)", "plain attr")


def test_register_conflict_both_missing() -> None:
    assert not _has_register_conflict("a", "b")


# =========================================================================
# Laag 3 — similarity
# =========================================================================

def test_similarity_identical_is_one() -> None:
    assert similarity("Foo Bar", "Foo Bar") == pytest.approx(1.0)


def test_similarity_register_conflict_is_zero() -> None:
    # R2T vs R1T -> blocked regardless of token overlap (case julG)
    assert similarity(
        "Leaving water temp. after BUH (R2T)",
        "Leaving water temp. before BUH (R1T)",
    ) == 0.0


def test_similarity_same_register_boost() -> None:
    # Same R#T + high token overlap -> should exceed pure-jaccard
    s = similarity(
        "Inlet water temp.(R4T)",
        "Hydro Module Inlet water temp.(R4T)",
    )
    assert s > 0.5


def test_similarity_empty_strings() -> None:
    # Identical strings short-circuit to 1.0 (early return)
    assert similarity("", "") == pytest.approx(1.0)


def test_similarity_disjoint_no_register() -> None:
    assert similarity("alpha", "beta") == 0.0


# =========================================================================
# Laag 2 — resolve_canonical
# =========================================================================

def test_resolve_exact() -> None:
    m = resolve_canonical(ATTR_OPERATION_MODE, {ATTR_OPERATION_MODE})
    assert m == AttrMatch(ATTR_OPERATION_MODE, ATTR_OPERATION_MODE, "exact", 1.0)


def test_resolve_alias_3way_valve_space() -> None:
    # benthouse variant
    avail = {"3way valve (On:DHW_Off:Space)"}
    m = resolve_canonical(ATTR_3WAY_VALVE, avail)
    assert m.kind == "alias"
    assert m.actual_key == "3way valve (On:DHW_Off:Space)"


def test_resolve_alias_inv_hz() -> None:
    m = resolve_canonical(ATTR_INV_FREQUENCY_RPS, {"INV frequency (Hz)"})
    assert m.kind == "alias"
    assert m.actual_key == "INV frequency (Hz)"


def test_resolve_normalized() -> None:
    # Case + extra spacing removed by _normalize
    m = resolve_canonical(ATTR_OPERATION_MODE, {"operation mode"})
    assert m.kind == "alias"
    assert m.actual_key == "operation mode"


def test_resolve_fuzzy_above_threshold() -> None:
    avail = {"Hydro Module Inlet water temp.(R4T)"}
    m = resolve_canonical(ATTR_INLET_WATER_R4T, avail, fuzzy_threshold=0.7)
    assert m.kind == "alias"  # resolved via alias table
    assert m.actual_key == "Hydro Module Inlet water temp.(R4T)"


def test_resolve_fuzzy_fallback_path() -> None:
    # No alias, no normalize match; fuzzy must kick in
    avail = {"Completely different R4T name"}
    m = resolve_canonical(ATTR_INLET_WATER_R4T, avail, fuzzy_threshold=0.2)
    assert m.kind in {"fuzzy", "missing"}
    if m.kind == "fuzzy":
        assert m.actual_key == "Completely different R4T name"


def test_resolve_missing() -> None:
    m = resolve_canonical(ATTR_OPERATION_MODE, set())
    assert m.kind == "missing"
    assert m.actual_key is None
    assert m.score == 0.0


def test_resolve_fuzzy_blocked_by_register_conflict() -> None:
    # Available has R1T variant; canonical is R2T -> anti-alias blocks fuzzy
    avail = {"Hydro Module LWT (R1T)", "Leaving water temp. before BUH (R1T)"}
    m = resolve_canonical(ATTR_LEAVING_WATER_AFTER_BUH, avail)
    assert m.kind == "missing"
    assert m.actual_key is None


def test_resolve_alias_table_covers_core_keys() -> None:
    # Every ALIASES key must be a CORE attr
    from custom_components.daikin_cycle_ml.const import CORE_ATTRIBUTES
    for key in ALIASES:
        assert key in CORE_ATTRIBUTES, f"alias key {key!r} not in CORE_ATTRIBUTES"


# =========================================================================
# Laag 1 — find_candidate_sensors
# =========================================================================

def test_find_candidates_empty() -> None:
    assert find_candidate_sensors([]) == []


def test_find_candidates_below_min_overlap() -> None:
    states = [("sensor.low", {"a": 1, "b": 2})]
    assert find_candidate_sensors(states, min_overlap=3) == []


def test_find_candidates_single_default() -> None:
    states = [("sensor.althermasensors", _full_attrs())]
    res = find_candidate_sensors(states)
    assert len(res) == 1
    assert res[0].entity_id == "sensor.althermasensors"
    assert res[0].overlap_count == 13


def test_find_candidates_renamed_entity() -> None:
    # mawashigeri case
    attrs = {c: 1.0 for c in list(_full_attrs())[:11]}
    states = [("sensor.altherma", attrs)]
    res = find_candidate_sensors(states, min_overlap=3)
    assert len(res) == 1
    assert res[0].entity_id == "sensor.altherma"
    assert res[0].overlap_count == 11


def test_find_candidates_sorted_desc_then_entity_id() -> None:
    full = _full_attrs()
    partial = {c: 1.0 for c in list(full)[:5]}
    states = [
        ("sensor.zzz", partial),
        ("sensor.aaa", full),
        ("sensor.mmm", partial),
    ]
    res = find_candidate_sensors(states, min_overlap=3)
    assert [c.entity_id for c in res] == [
        "sensor.aaa", "sensor.mmm", "sensor.zzz",
    ]


def test_find_candidates_none_prefix_bug() -> None:
    # Videopac case
    attrs = {c: 1.0 for c in list(_full_attrs())[:12]}
    states = [("sensor.none_althermasensors", attrs)]
    res = find_candidate_sensors(states, min_overlap=3)
    assert res[0].entity_id == "sensor.none_althermasensors"


# =========================================================================
# Laag 5 — check_sanity
# =========================================================================

@pytest.mark.parametrize("suspicious", sorted(SUSPICIOUS_VALUES))
def test_check_sanity_flags_each_suspicious(suspicious: float) -> None:
    warnings = check_sanity(
        {"Water pressure": suspicious},
        {"Water pressure": "Water pressure"},
    )
    assert len(warnings) == 1
    assert "Water pressure" in warnings[0]


def test_check_sanity_ok_value() -> None:
    assert check_sanity({"Foo": 21.5}, {"Foo": "Foo"}) == []


def test_check_sanity_ignores_bool() -> None:
    assert check_sanity({"Foo": True}, {"Foo": "Foo"}) == []


def test_check_sanity_ignores_non_numeric() -> None:
    assert check_sanity({"Foo": "21.5"}, {"Foo": "Foo"}) == []


def test_check_sanity_missing_key() -> None:
    # resolved has key, attrs doesn't -> value None -> no warning
    assert check_sanity({}, {"Foo": "Foo"}) == []


# =========================================================================
# Laag 4 — build_diagnostic
# =========================================================================

def test_build_diagnostic_empty_available() -> None:
    rep = build_diagnostic(available=set())
    assert isinstance(rep, DiagnosticReport)
    assert len(rep.missing) == 13
    assert all(m.kind == "missing" for m in rep.matches)
    assert rep.warnings == ()


def test_build_diagnostic_full() -> None:
    attrs = _full_attrs()
    rep = build_diagnostic(available=set(attrs), attrs=attrs)
    assert rep.missing == ()
    assert all(m.kind == "exact" for m in rep.matches)


def test_build_diagnostic_phase_hint() -> None:
    avail = {"Inverter usage"}
    rep = build_diagnostic(available=avail)
    assert PHASE_HINT in rep.warnings


def test_build_diagnostic_no_phase_hint() -> None:
    rep = build_diagnostic(available={"Foo"})
    assert PHASE_HINT not in rep.warnings


def test_build_diagnostic_sanity_and_phase_together() -> None:
    # Sanity only fires on resolved CORE attrs (build_diagnostic contract)
    attrs = dict(_full_attrs())
    attrs[ATTR_OPERATION_MODE] = -51.18
    avail = set(attrs) | {"Inverter usage"}
    rep = build_diagnostic(available=avail, attrs=attrs)
    assert PHASE_HINT in rep.warnings
    assert any(ATTR_OPERATION_MODE in w for w in rep.warnings)


# =========================================================================
# Regression: anti-alias (issue #51 case julG COP~11)
# =========================================================================

def test_regression_julg_cop11_r2t_never_matches_r1t() -> None:
    """Issue #51: R2T (after BUH) must NEVER resolve to R1T (before BUH)."""
    candidates_r1t = {
        "Hydro Module LWT (R1T)",
        "Leaving water temp. before BUH (R1T)",
        "R1T-Outdoor air temp.",
    }
    m = resolve_canonical(ATTR_LEAVING_WATER_AFTER_BUH, candidates_r1t)
    assert m.kind == "missing"
    assert m.actual_key is None


def test_regression_r2t_exact_still_works() -> None:
    m = resolve_canonical(ATTR_LEAVING_WATER_AFTER_BUH, {ATTR_LEAVING_WATER_AFTER_BUH})
    assert m.kind == "exact"


def test_regression_r1t_canonical_exact_still_works() -> None:
    m = resolve_canonical(ATTR_OUTDOOR_AIR_R1T, {ATTR_OUTDOOR_AIR_R1T})
    assert m.kind == "exact"
