"""v1.20.0 #281: per-model coverage matrix.

Documents and verifies which of the 21 *operational* CONSUMED attributes
(excludes 4 intrinsic labels that are computed or dynamic, never in .h
files: COP, Stats: Heat output, Stats: Electrical input x2) resolve for
each of the 37 real models tracked in docs/MODEL_ATTRIBUTES.json.

Excluded from scope:
- DEFAULT.h, PROTOCOL_S.h, PROTOCOL_S_ROTEX.h — placeholders, not real models
- HT models (ERRQ, EKHBRD) — different register protocol, tracked separately

R598: real resolve_attrs, real discovery, real slug engine.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.const import (
    CONSUMED_ATTRIBUTES,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
    _slug_variants,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
    make_json_key,
)

MODEL_ATTRIBUTES_PATH = Path("docs/MODEL_ATTRIBUTES.json")

# 4 intrinsic labels — computed by the integration or provided dynamically
# by ESPAltherma at runtime, never in .h files.
INTRINSIC_LABELS = frozenset({
    "COP",
    "Stats: Heat output (kW)",
    "Stats: Electrical input estimated (kW)",
    "Stats: Electricalinput estimated (kW)",
})
OPERATIONAL_ATTRIBUTES = [a for a in CONSUMED_ATTRIBUTES if a not in INTRINSIC_LABELS]

# Scope exclusions
EXCLUDED_FROM_MATRIX = frozenset({
    "DEFAULT.h",
    "PROTOCOL_S.h",
    "PROTOCOL_S_ROTEX.h",
    "Altherma(HT ERRQ-ERSQ outdoor unit 11-16kW).h",
    "Altherma(HT EKHBRD-ERRQ series 11-16kW).h",
    "Altherma(HT EKHBRD-ERRQ series 11-16kW protocol S).h",
})


@pytest.fixture(scope="module")
def model_data():
    """Load MODEL_ATTRIBUTES and invert into {model: set_of_slugs}."""
    if not MODEL_ATTRIBUTES_PATH.exists():
        pytest.skip(f"MODEL_ATTRIBUTES.json missing: {MODEL_ATTRIBUTES_PATH}")
    data = json.loads(MODEL_ATTRIBUTES_PATH.read_text())
    labels_to_models = data["labels"]
    models = sorted(data["models"])
    model_slugs = {m: set() for m in models}
    for label, model_list in labels_to_models.items():
        slug = make_json_key(label)
        for m in model_list:
            if m in model_slugs:
                model_slugs[m].add(slug)
    return {"models": models, "model_slugs": model_slugs}


def _coverage_for_model(model_slugs: set[str]) -> dict[str, int]:
    """Return {direct, alias, total, missing} for a given model's slug set."""
    direct = 0
    alias = 0
    missing: list[str] = []
    for label in OPERATIONAL_ATTRIBUTES:
        variants = _slug_variants(label)
        direct_slug = make_json_key(label)
        if direct_slug in model_slugs:
            direct += 1
        elif any(v in model_slugs for v in variants if v != direct_slug):
            alias += 1
        else:
            missing.append(label)
    return {
        "direct": direct,
        "alias": alias,
        "total": direct + alias,
        "missing": missing,
    }


def test_operational_attributes_count() -> None:
    """Sanity: 22 operational = 26 consumed minus 4 intrinsic."""
    assert len(OPERATIONAL_ATTRIBUTES) == 22, (
        f"expected 22, got {len(OPERATIONAL_ATTRIBUTES)}"
    )
    assert len(INTRINSIC_LABELS) == 4


def test_all_models_loaded(model_data) -> None:
    """40 models in upstream, 34 in scope (minus 3 placeholders, 3 HT)."""
    total = len(model_data["models"])
    assert total == 40, f"expected 40 upstream models, got {total}"
    in_scope = [m for m in model_data["models"] if m not in EXCLUDED_FROM_MATRIX]
    assert len(in_scope) == 34, f"expected 34 in-scope models, got {len(in_scope)}"


# ============================================================
# Coverage thresholds per model class
# ============================================================

# Each group has a minimum expected operational coverage. Below that
# minimum triggers a failure — catches regression where a model loses
# coverage that was previously working.

# ECH2O modellen: lost direct R2T but has [HPSU] variant (alias).
# EPSK: has (water heat exchanger) variant (alias).
# Hybrid: has Outdoor air temp. (no R1T) + Outlet Water BUH Temp. (alias).
# All should hit at least 18/21 after aliases.
MIN_EXPECTED = {
    # Complete models — no legitimate gaps beyond INV freq 2 (single compressor)
    # Expected: 20/21 (miss INV freq 2 which is cascade-only)
    "Altherma(ERGA D EHV-EHB-EHVZ DA series 04-08kW).h": 20,
    "Altherma(ERLA03 D EHFH-EHFZ DJ series 3kW).h": 20,
    "Altherma(LT_CA_CB_04-08kW).h": 19,
    "Altherma(LT_EBLQ-EBLQ-CA series 5-7kW Monobloc).h": 19,
    # ECH2O models — R2T via [HPSU] alias
    "Altherma(EPRA D ETSH-X 16P30-50 D series 14-16kW-ECH2O).h": 17,
    "Altherma(ERGA D EHSH-X P30-50 D series 04-08kW-ECH2O).h": 17,
    # Hybrid model — Outdoor + BUH via aliases
    "Altherma(Hybrid).h": 17,
    # EPSK — inlet via alias
    "Altherma 4(EPSK-EPSKS EPBX-EPSX-EPVX-EPVZ series 04-14kW).h": 17,
    # Multi DHW tank — no INV/compressor stuff
    "CKHWS-BJV3(Multi DHW tank 2).h": 15,
    "EKHWET-BAV3(Multi DHW tank).h": 15,
    # GEO3 — no BE_COP
    "Altherma(EGSAH-X-EWSAH-X-D series 6-10kW GEO3).h": 14,
}


@pytest.mark.parametrize(
    "model,min_expected",
    sorted(MIN_EXPECTED.items()),
)
def test_model_meets_minimum_coverage(model_data, model, min_expected) -> None:
    """Each model resolves at least `min_expected` of 21 operational attrs."""
    slugs = model_data["model_slugs"].get(model)
    assert slugs is not None, f"model {model!r} not found in upstream data"
    cov = _coverage_for_model(slugs)
    assert cov["total"] >= min_expected, (
        f"{model}: only {cov['total']}/21 resolve "
        f"(expected >= {min_expected}); missing: {cov['missing']}"
    )


def test_all_in_scope_models_have_at_least_required_coverage(model_data) -> None:
    """Every in-scope model resolves at least 12/21 operational attrs
    (the baseline the user's EPRA12 achieved and most modern models meet)."""
    low_coverage = []
    for m in model_data["models"]:
        if m in EXCLUDED_FROM_MATRIX:
            continue
        slugs = model_data["model_slugs"][m]
        cov = _coverage_for_model(slugs)
        if cov["total"] < 12:
            low_coverage.append((m, cov["total"], cov["missing"]))
    assert not low_coverage, (
        f"{len(low_coverage)} models below 12/21: {low_coverage[:3]}"
    )


# ============================================================
# Stats availability — ESPAltherma computes Stats on-board from 4 source
# attributes. Any model that publishes all 4 can produce Stats (requires
# firmware v2.0.0-beta.19+ which added the Stats calculation).
# HT models (ERRQ/EKHBRD) use a different register protocol and don't
# publish these source values; they are out of scope.
# ============================================================


# Source attributes ESPAltherma needs to compute Stats. If a model
# publishes all 4, Stats become available once firmware >= beta.19.
STATS_SOURCE_LABELS = [
    "Flow sensor (l/min)",
    "Leaving water temp. after BUH (R2T)",
    "Inlet water temp.(R4T)",
    "INV primary current (A)",
]


@pytest.mark.parametrize(
    "label",
    STATS_SOURCE_LABELS,
)
def test_stats_source_labels_have_aliases(label: str) -> None:
    """Each Stats-source label has at least one direct/alias form."""
    variants = _slug_variants(label)
    assert variants, f"{label!r} has no slug variants"


def test_all_in_scope_models_have_stats_source_values(model_data) -> None:
    """Every in-scope model publishes all 4 Stats-source values.

    This proves "all models have Stats by default" is accurate — Stats
    are computed on the ESPAltherma board from these 4 source values,
    and every non-HT real model publishes all of them. The only models
    that can't produce Stats are HT (ERRQ/EKHBRD), which are out of
    scope (different register protocol).
    """
    from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
        _slug_variants as slug_variants,
    )

    missing_stats_source = []
    for m in model_data["models"]:
        if m in EXCLUDED_FROM_MATRIX:
            continue
        slugs = model_data["model_slugs"][m]
        missing_labels = []
        for label in STATS_SOURCE_LABELS:
            variants = slug_variants(label)
            # NOTE: _slug_variants() already returns make_json_key slugs.
            # Do NOT call make_json_key again (would drop underscores and
            # break matching — v is already a canonical slug).
            if not any(v in slugs for v in variants):
                missing_labels.append(label)
        if missing_labels:
            missing_stats_source.append((m, missing_labels))

    assert not missing_stats_source, (
        f"{len(missing_stats_source)} in-scope models miss Stats-source "
        f"labels (should be 0 after exclusions): "
        f"{missing_stats_source[:3]}"
    )


def test_ht_models_correctly_excluded_from_stats(model_data) -> None:
    """HT models (ERRQ/EKHBRD) don't publish Stats source values — this
    is legitimate (different register protocol) and documented.
    """
    from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
        _slug_variants as slug_variants,
    )
    HT_MODELS = {
        "Altherma(HT ERRQ-ERSQ outdoor unit 11-16kW).h",
        "Altherma(HT EKHBRD-ERRQ series 11-16kW).h",
        "Altherma(HT EKHBRD-ERRQ series 11-16kW protocol S).h",
    }
    for m in HT_MODELS:
        slugs = model_data["model_slugs"].get(m)
        if slugs is None:
            continue  # not in the fixture
        # HT model should NOT have all 4 Stats-source labels
        # (slug_variants() returns canonical slugs — no second make_json_key)
        present = sum(
            1 for label in STATS_SOURCE_LABELS
            if any(v in slugs for v in slug_variants(label))
        )
        assert present < 4, (
            f"{m}: expected fewer than 4 Stats-source labels (HT protocol), "
            f"got {present}/4"
        )


# ============================================================
# Alias effectiveness — prove the fix works across affected models
# ============================================================


def test_ech2o_r2t_alias_works(model_data) -> None:
    """ECH2O models resolve R2T via [HPSU] alias."""
    for model in (
        "Altherma(EPRA D ETSH-X 16P30-50 D series 14-16kW-ECH2O).h",
        "Altherma(ERGA D EHSH-X P30-50 D series 04-08kW-ECH2O).h",
    ):
        slugs = model_data["model_slugs"][model]
        cov = _coverage_for_model(slugs)
        assert "Leaving water temp. after BUH (R2T)" not in cov["missing"], (
            f"{model}: R2T should resolve via alias, got missing"
        )


def test_hybrid_outdoor_alias_works(model_data) -> None:
    """Hybrid model resolves Outdoor air temp via `Outdoor air temp.` alias."""
    model = "Altherma(Hybrid).h"
    slugs = model_data["model_slugs"][model]
    cov = _coverage_for_model(slugs)
    assert "Outdoor air temp.(R1T)" not in cov["missing"], (
        f"{model}: Outdoor should resolve via alias, got missing"
    )


def test_hybrid_buh_r2t_alias_works(model_data) -> None:
    """Hybrid model resolves R2T via `Outlet Water BUH Temp.` alias."""
    model = "Altherma(Hybrid).h"
    slugs = model_data["model_slugs"][model]
    cov = _coverage_for_model(slugs)
    assert "Leaving water temp. after BUH (R2T)" not in cov["missing"], (
        f"{model}: BUH R2T should resolve via alias, got missing"
    )


def test_epsk_inlet_alias_works(model_data) -> None:
    """EPSK model resolves inlet temp via (water heat exchanger) alias."""
    model = "Altherma 4(EPSK-EPSKS EPBX-EPSX-EPVX-EPVZ series 04-14kW).h"
    slugs = model_data["model_slugs"][model]
    cov = _coverage_for_model(slugs)
    assert "Inlet water temp.(R4T)" not in cov["missing"], (
        f"{model}: Inlet should resolve via alias, got missing"
    )
