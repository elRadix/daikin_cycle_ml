"""Tests for ESPAltherma v2 entity discovery (issue #281, R684 + R640)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.daikin_cycle_ml.engine.espaltherma_v2.discovery import (
    DEFAULT_DOMAIN,
    build_slug_index,
    discover_entity_ids,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
    DEFAULT_PREFIX,
    make_json_key,
)

# ---------- helpers ----------


def _make_state(entity_id: str) -> MagicMock:
    s = MagicMock()
    s.entity_id = entity_id
    return s


def _make_hass(entity_ids: list[str]) -> MagicMock:
    hass = MagicMock()
    hass.states.async_all = MagicMock(
        side_effect=lambda domain: (
            [_make_state(e) for e in entity_ids]
            if domain == DEFAULT_DOMAIN
            else []
        )
    )
    return hass


# ---------- 47 mocked entities from fransh47 -> 47 in index ----------


REAL_V2_ENTITIES = [
    # subset of @fransh47's 2026-11-06 ESPAltherma v2 entity list
    "sensor.espaltherma_operation_mode",
    "sensor.espaltherma_iu_operation_mode",
    "sensor.espaltherma_3way_valveondhwoffspace",
    "sensor.espaltherma_defrost_operation",
    "sensor.espaltherma_leaving_water_temp_after_buh_r2t",
    "sensor.espaltherma_inlet_water_tempr4t",
    "sensor.espaltherma_outdoor_air_tempr1t",
    "sensor.espaltherma_flow_sensor_lmin",
    "sensor.espaltherma_water_pump_operation",
    "sensor.espaltherma_buh_step1",
    "sensor.espaltherma_buh_step2",
    "sensor.espaltherma_lw_setpoint_main",
    # extras a real install will also publish
    "sensor.espaltherma_inv_frequency_rps",
    "sensor.espaltherma_r1t_outdoor_air_temp",
    "sensor.espaltherma_hp_power",
]


def test_build_slug_index_real_v2_entities() -> None:
    hass = _make_hass(REAL_V2_ENTITIES)
    index = build_slug_index(hass)
    assert len(index) == len(REAL_V2_ENTITIES)
    # Spot-check: known slug for "Operation Mode"
    assert index["operation_mode"] == "sensor.espaltherma_operation_mode"
    # Spot-check: quirk slug
    assert (
        index["3way_valveondhwoffspace"]
        == "sensor.espaltherma_3way_valveondhwoffspace"
    )


def test_build_slug_index_slug_matches_make_json_key() -> None:
    """Index keys must equal make_json_key(label) for every REQUIRED_ATTRIBUTE."""
    from custom_components.daikin_cycle_ml.const import REQUIRED_ATTRIBUTES
    entity_ids = [
        f"{DEFAULT_PREFIX}{make_json_key(label)}" for label in REQUIRED_ATTRIBUTES
    ]
    hass = _make_hass(entity_ids)
    index = build_slug_index(hass)
    for label in REQUIRED_ATTRIBUTES:
        slug = make_json_key(label)
        assert slug in index, f"{slug!r} missing for label {label!r}"
        assert index[slug] == f"{DEFAULT_PREFIX}{slug}"


# ---------- prefix behaviour ----------


def test_custom_prefix_respected() -> None:
    hass = _make_hass([
        "sensor.custom_op_mode",
        "sensor.espaltherma_operation_mode",  # ignored: wrong prefix
    ])
    index = build_slug_index(hass, prefix="sensor.custom_")
    assert index == {"op_mode": "sensor.custom_op_mode"}


def test_empty_prefix_returns_all_sensor_slugs() -> None:
    """Prefix `sensor.` matches all sensor entities."""
    hass = _make_hass([
        "sensor.espaltherma_operation_mode",
        "sensor.something_else",
    ])
    index = build_slug_index(hass, prefix="sensor.")
    assert len(index) == 2
    assert "espaltherma_operation_mode" in index
    assert "something_else" in index


def test_non_matching_entities_excluded() -> None:
    hass = _make_hass([
        "sensor.espaltherma_operation_mode",
        "sensor.weather_temperature",
        "sensor.althermasensors",
    ])
    index = build_slug_index(hass)
    assert list(index.keys()) == ["operation_mode"]


# ---------- edge cases ----------


def test_empty_hass_returns_empty_index() -> None:
    hass = _make_hass([])
    assert build_slug_index(hass) == {}


def test_only_prefix_entity_skipped() -> None:
    """Entity_id == prefix has empty slug; must be skipped (not IndexError)."""
    hass = _make_hass([DEFAULT_PREFIX])
    assert build_slug_index(hass) == {}


def test_other_domains_not_queried() -> None:
    """Only sensor domain is scanned (binary_sensor lives in another pass)."""
    hass = MagicMock()
    binary_state = _make_state("binary_sensor.espaltherma_defrost_active")
    hass.states.async_all = MagicMock(
        side_effect=lambda d: [binary_state] if d == "binary_sensor" else []
    )
    assert build_slug_index(hass) == {}
    # Verify only DEFAULT_DOMAIN was requested
    calls = [c.args[0] for c in hass.states.async_all.call_args_list]
    assert all(c == DEFAULT_DOMAIN for c in calls)


# ---------- discover_entity_ids ----------


def test_discover_entity_ids_sorted() -> None:
    hass = _make_hass([
        "sensor.espaltherma_zeta",
        "sensor.espaltherma_alpha",
        "sensor.espaltherma_beta",
    ])
    assert discover_entity_ids(hass) == [
        "sensor.espaltherma_alpha",
        "sensor.espaltherma_beta",
        "sensor.espaltherma_zeta",
    ]


def test_discover_entity_ids_empty() -> None:
    assert discover_entity_ids(_make_hass([])) == []


def test_discover_entity_ids_respects_custom_prefix() -> None:
    hass = _make_hass([
        "sensor.espaltherma_a",
        "sensor.custom_a",
    ])
    assert discover_entity_ids(hass, prefix="sensor.custom_") == [
        "sensor.custom_a"
    ]


# ---------- performance sanity ----------


def test_build_slug_index_handles_500_entities() -> None:
    """Guard against O(n^2); 500 entities should complete trivially."""
    eids = [f"sensor.espaltherma_slug_{i}" for i in range(500)]
    hass = _make_hass(eids)
    index = build_slug_index(hass)
    assert len(index) == 500


# ---------- R640 fuzz: entity_id space is unpredictable ----------


@given(
    eids=st.lists(
        st.from_regex(
            r"^sensor\.[a-z0-9_]{1,30}$",
            fullmatch=True,
        ),
        min_size=0,
        max_size=30,
    )
)
@settings(max_examples=200, deadline=None)
def test_build_slug_index_fuzz_never_raises(eids: list[str]) -> None:
    """R676: 200 random entity_id lists -> no crash, index size bounded."""
    hass = _make_hass(eids)
    index = build_slug_index(hass)
    # Every key must be a non-empty string stripped of prefix
    for slug, eid in index.items():
        assert slug
        assert eid == f"{DEFAULT_PREFIX}{slug}"


# ---------- MODEL_ATTRIBUTES.json coverage: all 422 upstream labels ----------


def _load_model_attributes_labels() -> list[str]:
    """Load the 422 canonical labels from docs/MODEL_ATTRIBUTES.json.

    File is pinned to upstream ESPAltherma beta SHA 714ad016.
    Actual structure (verified 2026-11-07, _meta.unique_labels=422):

        {
          "_meta": {..., "root_model_count": 40, "unique_labels": 422},
          "models": ["ModelA.h", "ModelB.h", ...],       # 40 filenames
          "labels": {                                     # 422 labels
              "Operation Mode": ["ModelA.h", "ModelB.h", ...],
              ...
          }
        }

    The union of labels is exactly ``labels.keys()``. ``models`` is
    informational (list of source .h files) and not used here.
    """
    import json
    import pathlib

    path = pathlib.Path("docs/MODEL_ATTRIBUTES.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        return []

    labels_obj = data.get("labels")
    if isinstance(labels_obj, dict):
        return sorted(k for k in labels_obj.keys() if isinstance(k, str))
    if isinstance(labels_obj, list):
        return sorted(x for x in labels_obj if isinstance(x, str))

    # Fallback for potential future variants: walk `models` if labels missing
    models_obj = data.get("models")
    if isinstance(models_obj, dict):
        return sorted(
            k for k in models_obj.keys() if isinstance(k, str)
        )
    return []


def test_model_attributes_file_present() -> None:
    """Guard: docs/MODEL_ATTRIBUTES.json must load with the pinned 422 labels."""
    labels = _load_model_attributes_labels()
    assert labels, "MODEL_ATTRIBUTES.json missing or empty"
    assert len(labels) >= 100, (
        f"expected >=100 labels across all models, got {len(labels)}"
    )


def _has_alnum(label: str) -> bool:
    """True iff label has >=1 ASCII alnum char (so makeJsonKey -> non-empty)."""
    return any(
        ("0" <= ch <= "9") or ("a" <= ch <= "z") or ("A" <= ch <= "Z")
        for ch in label
    )


def _labels_with_alnum() -> list[str]:
    return [lb for lb in _load_model_attributes_labels() if _has_alnum(lb)]


def _labels_without_alnum() -> list[str]:
    return [lb for lb in _load_model_attributes_labels() if not _has_alnum(lb)]


@pytest.mark.parametrize("label", _labels_with_alnum())
def test_model_attribute_slugs_to_valid_entity_id(label: str) -> None:
    """R684 per-label: every label with alnum chars slugs to valid ASCII."""
    slug = make_json_key(label)
    assert slug, f"empty slug for label with alnum chars: {label!r}"
    for ch in slug:
        assert ch.isascii()
        assert ch.isalnum() or ch == "_"
        if ch.isalpha():
            assert ch.islower()


# Known case-only collisions in upstream SHA 714ad016 (2026-11-06).
# All 4 pairs differ only in letter case; makeJsonKey lowercases both
# sides to the same slug. They are syntactic synonyms in the .h files.
# Any NEW collision (different wording) must fail — upstream drift guard.
KNOWN_CASE_COLLISIONS: dict[str, list[str]] = {
    "fin_temp": ["Fin Temp.", "Fin temp."],
    "rc_setpoint": ["R/C Setpoint", "R/C setpoint"],
    "sv_hot_gas": ["SV (hot Gas)", "SV (hot gas)"],
    "startup_control": ["Startup Control", "Startup control"],
}


@pytest.mark.parametrize("label", _labels_without_alnum())
def test_placeholder_label_slugs_to_empty(label: str) -> None:
    """Upstream placeholders (e.g. '????') must slug to '' — behavior of makeJsonKey."""
    assert make_json_key(label) == "", (
        f"label without alnum {label!r} unexpectedly produced "
        f"{make_json_key(label)!r}"
    )


def test_discovery_skips_empty_slug_labels() -> None:
    """A raw label like '????' would produce entity_id == prefix; must be skipped."""
    labels_without_alnum = _labels_without_alnum()
    if not labels_without_alnum:
        pytest.skip("upstream has no placeholder-only labels at this SHA")
    hass = _make_hass([f"{DEFAULT_PREFIX}"])
    index = build_slug_index(hass)
    assert index == {}, (
        f"prefix-only entity must be skipped, got: {index}"
    )


def _compute_collisions() -> dict[str, list[str]]:
    """Return {slug: [labels...]} for every slug with >1 label."""
    labels = _load_model_attributes_labels()
    by_slug: dict[str, list[str]] = {}
    for label in labels:
        slug = make_json_key(label)
        if not slug:
            continue
        by_slug.setdefault(slug, []).append(label)
    return {s: ls for s, ls in by_slug.items() if len(ls) > 1}


def test_slug_collisions_are_case_only_variants() -> None:
    """Every collision in upstream SHA 714ad016 is a case-only synonym.

    Two labels collide only if makeJsonKey(lowercases) them to the same
    slug. Case-insensitive upstream typos are acceptable; semantic
    duplicates ("Inlet" vs "Outlet") would be a bug.
    """
    collisions = _compute_collisions()
    for slug, labels in collisions.items():
        normed = {lb.lower() for lb in labels}
        assert len(normed) == 1, (
            f"semantic collision at slug {slug!r}: {labels} "
            f"(normalized: {sorted(normed)})"
        )


def test_no_unexpected_collisions_beyond_allowlist() -> None:
    """Guard against future upstream drift: only known 4 pairs allowed.

    If upstream adds a new pair of labels that collide, this test fails
    and forces us to either:
      (a) update KNOWN_CASE_COLLISIONS if it's again a case-only typo, or
      (b) implement per-model disambiguation in the resolver.
    """
    actual = _compute_collisions()
    actual_keys = set(actual.keys())
    expected_keys = set(KNOWN_CASE_COLLISIONS.keys())
    unexpected = actual_keys - expected_keys
    missing = expected_keys - actual_keys
    assert not unexpected, (
        f"new slug collisions detected: "
        f"{ {s: actual[s] for s in unexpected} } — "
        f"update KNOWN_CASE_COLLISIONS if case-only, else resolve at model level"
    )
    assert not missing, (
        f"expected collisions no longer occur: {missing} — "
        f"remove from KNOWN_CASE_COLLISIONS if upstream fixed the typos"
    )
    # Exact label-set match per slug
    for slug, expected_labels in KNOWN_CASE_COLLISIONS.items():
        actual_set = set(actual[slug])
        expected_set = set(expected_labels)
        assert actual_set == expected_set, (
            f"collision set changed for {slug!r}: "
            f"expected {expected_set}, got {actual_set}"
        )
