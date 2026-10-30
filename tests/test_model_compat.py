"""Model-compatibility tests for docs/MODEL_ATTRIBUTES.json.

Enforces the contract between:
- Engine canonical labels (attribute_compat.ALIAS_GROUPS keys)
- ESPAltherma definitions index (docs/MODEL_ATTRIBUTES.json)

Fails if:
- A canonical label disappears from the JSON (regression on #150 class)
- A decoy attribute is promoted to canonical
- A model disappears from the JSON
- A label has no backing model (orphan)

Weekly drift detection lives in .github/workflows/model-compat.yml.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.const import REQUIRED_ATTRIBUTES
from custom_components.daikin_cycle_ml.engine.attribute_compat import (
    ALIAS_GROUPS,
)

_JSON_PATH = Path(__file__).resolve().parents[1] / "docs" / "MODEL_ATTRIBUTES.json"
_DATA = json.loads(_JSON_PATH.read_text(encoding="utf-8"))

# Canonical labels — single source of truth is the resolver itself (R426).
CANONICAL_LABELS: list[str] = sorted(ALIAS_GROUPS.keys())

# Known decoys: attributes that LOOK like canonical sensors but are not.
# Sourced from handoff v102.0 §6 (prod-1 decoy warnings).
DECOYS: list[str] = [
    "Heat exchanger mid-temp.(R5T)",   # refrigerant, NOT DHW tank (R5T)
    "O/U Heat Exch. Temp.(R4T)",       # refrigerant, NOT inlet water (R4T)
    "Indoor ambient temp. (R1T)",      # indoor ambient, NOT outdoor air (R1T)
]

# Models that legitimately do NOT support heating (cooling-only, DHW-only,
# alternative-protocol specs, or empty template skeletons). Skipped from the
# REQUIRED_ATTRIBUTES coverage check.
NON_HEATING_MODELS: frozenset[str] = frozenset({
    "Daikin Mini chiller(EWAA-EWYA D series 4-8kW).h",
    "Daikin Mini chiller(EWAA-EWYA D series 9-16kW).h",
    "Daikin Mini chiller(EWAQ-EWYQ B series 4-8kW).h",
    "CKHWS-BJV3(Multi DHW tank 2).h",
    "EKHWET-BAV3(Multi DHW tank).h",
    "PROTOCOL_S.h",
    "PROTOCOL_S_ROTEX.h",
    "DEFAULT.h",  # empty template skeleton, no labels
})

# Heating models that DO NOT have all REQUIRED_ATTRIBUTES by design.
# Any change here must be justified by a re-analysis of the upstream
# .h files; silently widening this dict hides regressions.
PARTIAL_MODELS: dict[str, list[str]] = {
    # Header of the file: "the indoor unit's inlet (R4T) is not on the wire".
    "Altherma 4(EPSK-EPSKS EPBX-EPSX-EPVX-EPVZ series 04-14kW).h": [
        "Inlet water temp.(R4T)",
    ],
    # ECH2O variants: water heat exchanger sits in the outdoor unit,
    # no BUH-only "after BUH (R2T)" sensor on the wire.
    "Altherma(EPRA D ETSH-X 16P30-50 D series 14-16kW-ECH2O).h": [
        "Leaving water temp. after BUH (R2T)",
    ],
    "Altherma(ERGA D EHSH-X P30-50 D series 04-08kW-ECH2O).h": [
        "Leaving water temp. after BUH (R2T)",
    ],
    # HT (high-temperature) EKHBRD series uses a distinct protocol; most
    # standard labels are not published. The integration reports
    # missing_attributes repair instead of failing.
    "Altherma(HT EKHBRD-ERRQ series 11-16kW protocol S).h": [
        "I/U operation mode",
        "3way valve(On:DHW_Off:Space)",
        "Defrost Operation",
        "Leaving water temp. after BUH (R2T)",
        "Inlet water temp.(R4T)",
        "Outdoor air temp.(R1T)",
        "Flow sensor (l/min)",
        "Water pump operation",
        "BUH Step1",
        "BUH Step2",
        "LW setpoint (main)",
    ],
    "Altherma(HT EKHBRD-ERRQ series 11-16kW).h": [
        "Operation Mode",
        "I/U operation mode",
        "3way valve(On:DHW_Off:Space)",
        "Defrost Operation",
        "Leaving water temp. after BUH (R2T)",
        "Inlet water temp.(R4T)",
        "Outdoor air temp.(R1T)",
        "Flow sensor (l/min)",
        "Water pump operation",
        "BUH Step1",
        "BUH Step2",
        "LW setpoint (main)",
    ],
    # HT ERRQ-ERSQ (v1.12.9, upstream beta 99ed8d19): outdoor unit only,
    # no water-side sensors on the wire (inlet/flow/BUH/3-way/water pump).
    # Hydrobox-side labels live in the EKHBRD-ERRQ variants above.
    "Altherma(HT ERRQ-ERSQ outdoor unit 11-16kW).h": [
        "3way valve(On:DHW_Off:Space)",
        "Leaving water temp. after BUH (R2T)",
        "Inlet water temp.(R4T)",
        "Flow sensor (l/min)",
        "Water pump operation",
        "BUH Step1",
        "BUH Step2",
        "LW setpoint (main)",
    ],
    # Hybrid: uses "Outlet Water BUH Temp. (R2T)" (covered by alias) but
    # still lacks the "Outdoor air temp.(R1T)" canonical spelling — upstream
    # only publishes "Outdoor air temp." without the "(R1T)" suffix.
    "Altherma(Hybrid).h": [
        "Outdoor air temp.(R1T)",
    ],
}

_HEATING_MODELS: list[str] = [
    m for m in _DATA["models"] if m not in NON_HEATING_MODELS
]

_FULL_COVERAGE_MODELS: list[str] = [
    m for m in _HEATING_MODELS if m not in PARTIAL_MODELS
]


# ── Structure invariants ────────────────────────────────────────────────────

EXPECTED_MODEL_COUNT = 40
EXPECTED_CANONICAL_COUNT = 11


def test_expected_model_count():
    assert len(_DATA["models"]) == EXPECTED_MODEL_COUNT
    assert _DATA["_meta"]["root_model_count"] == EXPECTED_MODEL_COUNT


def test_expected_canonical_count():
    assert len(CANONICAL_LABELS) == EXPECTED_CANONICAL_COUNT


def test_unique_labels_matches_meta():
    assert len(_DATA["labels"]) == _DATA["_meta"]["unique_labels"]


def test_meta_invariants():
    meta = _DATA["_meta"]
    assert meta["source"] == "https://github.com/raomin/ESPAltherma"
    assert meta["branch"] == "beta"
    assert len(meta["commit"]) == 40
    assert all(c in "0123456789abcdef" for c in meta["commit"])
    assert meta["generated_at"].endswith("+00:00")
    assert "T" in meta["generated_at"]


# ── Canonical label presence ────────────────────────────────────────────────

def _resolvable_labels(canonical: str) -> list[str]:
    """All spellings that the resolver accepts for one canonical label."""
    return [canonical, *ALIAS_GROUPS.get(canonical, ())]


@pytest.mark.parametrize("label", CANONICAL_LABELS)
def test_canonical_label_resolvable(label: str):
    """At least one spelling of each canonical label must exist upstream.

    The engine works with the canonical spelling; ESPAltherma upstream may
    rename (see #150: 'Outdoor air temp.(R1T)' -> 'R1T-Outdoor air temp.').
    The compat layer bridges both, so what matters is that SOME known
    spelling is present in the index.
    """
    variants = _resolvable_labels(label)
    present = [v for v in variants if v in _DATA["labels"]]
    assert present, (
        f"no spelling of canonical {label!r} in MODEL_ATTRIBUTES.json. "
        f"Tried: {variants}. Either upstream removed all spellings or "
        f"attribute_compat.ALIAS_GROUPS needs a new alias"
    )


# ── Decoy safety ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("decoy", DECOYS)
def test_decoy_not_canonical(decoy: str):
    assert decoy not in CANONICAL_LABELS, (
        f"decoy {decoy!r} must never be promoted to canonical; "
        f"see handoff v102.0 §6 decoy register"
    )


# ── Per-model matrix ────────────────────────────────────────────────────────

@pytest.mark.parametrize("model", _DATA["models"])
def test_model_is_string(model):
    assert isinstance(model, str)
    assert model.endswith(".h"), f"model {model!r} should end with .h"


@pytest.mark.parametrize("model", _DATA["models"])
def test_model_appears_in_some_label(model: str):
    """Every model must appear in at least one label's model list."""
    hits = sum(1 for models in _DATA["labels"].values() if model in models)
    assert hits > 0, f"model {model!r} appears in no label's model list"


_HEATING_MODELS = [
    m for m in _DATA["models"] if m not in NON_HEATING_MODELS
]


def _canonical_present_for_model(model: str, canonical: str) -> bool:
    """True if ANY known spelling of ``canonical`` is listed for ``model``."""
    variants = _resolvable_labels(canonical)
    return any(model in _DATA["labels"].get(v, []) for v in variants)


@pytest.mark.parametrize("model", _FULL_COVERAGE_MODELS)
def test_required_attrs_fully_covered(model: str):
    """Every fully-supported heating model exposes ALL REQUIRED_ATTRIBUTES.

    This is the hard compatibility guarantee: if any of these 12 attrs is
    removed for a model in the index, the integration setup would fail on
    that install (missing_attributes repair would fire). Catch it here.
    """
    missing = [
        attr for attr in REQUIRED_ATTRIBUTES
        if not _canonical_present_for_model(model, attr)
    ]
    assert not missing, (
        f"{model!r} missing required attrs: {missing}. "
        f"If upstream removed them, this is a regression on the class "
        f"that #150 belongs to — update ALIAS_GROUPS or investigate."
    )


@pytest.mark.parametrize("model,expected_missing", PARTIAL_MODELS.items())
def test_partial_models_match_expected(model: str, expected_missing: list[str]):
    """Partial models must miss EXACTLY the documented set of attrs.

    If upstream adds a missing label, the set shrinks -> move the model to
    _FULL_COVERAGE_MODELS. If upstream removes another label, the set grows
    -> regression, investigate. This test guards both directions.
    """
    actual = sorted(
        attr for attr in REQUIRED_ATTRIBUTES
        if not _canonical_present_for_model(model, attr)
    )
    expected = sorted(expected_missing)
    assert actual == expected, (
        f"{model!r} partial-set changed.\n"
        f"  Expected: {expected}\n"
        f"  Got:      {actual}\n"
        f"If upstream added a label, remove from PARTIAL_MODELS and it moves "
        f"to _FULL_COVERAGE_MODELS. If upstream removed one, this is a real "
        f"regression — update ALIAS_GROUPS or file a bug."
    )


def test_heating_partition_complete():
    """Every heating model is either fully covered or in PARTIAL_MODELS."""
    diff = set(_HEATING_MODELS) - set(PARTIAL_MODELS) - set(_FULL_COVERAGE_MODELS)
    assert not diff, f"unclassified heating models: {sorted(diff)}"
    overlap = set(PARTIAL_MODELS) & set(_FULL_COVERAGE_MODELS)
    assert not overlap, f"models classified as both full and partial: {sorted(overlap)}"


# ── Orphan / duplicate guards ───────────────────────────────────────────────

def test_no_orphan_labels():
    """Every label must map to at least one model."""
    orphans = [lbl for lbl, models in _DATA["labels"].items() if not models]
    assert not orphans, f"orphan labels (empty model list): {orphans[:10]}"


def test_no_duplicate_models_in_label():
    """Each label's model list must be free of duplicates."""
    bad = [lbl for lbl, models in _DATA["labels"].items() if len(models) != len(set(models))]
    assert not bad, f"labels with duplicate models: {bad[:10]}"
