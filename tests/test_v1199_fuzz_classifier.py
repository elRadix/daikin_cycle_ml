"""v1.19.9 #123 R640: hypothesis fuzz tests for classify_cop_sample.

Invarianten:
- Nooit raise voor (mode, lwt, outdoor, cop) in realistische range
- Mode ∉ {heating,dhw} -> always not_applicable
- lwt of outdoor is None -> not_applicable
- lwt <= outdoor -> not_applicable
- Deterministic (same input, same output)
- Monotonie: vaste (mode, lwt, outdoor), hogere cop -> accept -> flag -> reject
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from custom_components.daikin_cycle_ml.engine.physics import (
    ACCEPT_MARGIN,
    CARNOT_EFFICIENCY_FACTOR,
    REJECT_MULTIPLIER,
    classify_cop_sample,
)


VALID_MODES = st.sampled_from(["heating", "dhw"])
ALL_MODES = st.sampled_from(["heating", "dhw", "cooling", "defrost",
                              "unknown", "", "HEATING"])


@settings(max_examples=200)
@given(
    mode=ALL_MODES,
    lwt=st.one_of(st.none(), st.floats(min_value=-45, max_value=100)),
    outdoor=st.one_of(st.none(), st.floats(min_value=-45, max_value=100)),
    cop=st.one_of(st.none(), st.floats(min_value=-10, max_value=100)),
)
def test_fuzz_classifier_never_raises(mode, lwt, outdoor, cop):
    """R640: nooit raise voor welke input dan ook."""
    try:
        r = classify_cop_sample(mode, lwt, outdoor, cop)
    except Exception as e:
        pytest.fail(
            f"classify({mode!r}, {lwt!r}, {outdoor!r}, {cop!r}) "
            f"raised {type(e).__name__}: {e}"
        )
    assert r in ("accept", "flag", "reject", "not_applicable")


@settings(max_examples=200)
@given(
    lwt=st.floats(min_value=-45, max_value=100),
    outdoor=st.floats(min_value=-45, max_value=100),
    cop=st.floats(min_value=-10, max_value=100),
)
def test_fuzz_classifier_cooling_always_not_applicable(lwt, outdoor, cop):
    """R640: cooling mode nooit classifier -> altijd not_applicable."""
    assert classify_cop_sample("cooling", lwt, outdoor, cop) == "not_applicable"


@settings(max_examples=200)
@given(
    mode=VALID_MODES,
    lwt=st.floats(min_value=-45, max_value=100),
    outdoor=st.floats(min_value=-45, max_value=100),
    cop=st.floats(min_value=-10, max_value=100),
)
def test_fuzz_classifier_none_inputs(mode, lwt, outdoor, cop):
    """R640: None input -> always not_applicable."""
    assert classify_cop_sample(mode, None, outdoor, cop) == "not_applicable"
    assert classify_cop_sample(mode, lwt, None, cop) == "not_applicable"
    assert classify_cop_sample(mode, lwt, outdoor, None) == "not_applicable"


@settings(max_examples=200)
@given(
    mode=VALID_MODES,
    lwt=st.floats(min_value=-45, max_value=100),
    delta=st.floats(min_value=0, max_value=20),
    cop=st.floats(min_value=-10, max_value=100),
)
def test_fuzz_classifier_lwt_le_outdoor_not_applicable(mode, lwt, delta, cop):
    """R640: lwt <= outdoor -> nooit bruikbaar -> not_applicable."""
    outdoor = lwt + delta  # outdoor >= lwt
    assert classify_cop_sample(mode, lwt, outdoor, cop) == "not_applicable"


@settings(max_examples=200)
@given(
    mode=VALID_MODES,
    lwt=st.floats(min_value=-30, max_value=90),
    outdoor=st.floats(min_value=-40, max_value=45),
    cop=st.floats(min_value=-5, max_value=50),
)
def test_fuzz_classifier_deterministic(mode, lwt, outdoor, cop):
    """R640: zelfde input -> zelfde output (pure functie)."""
    r1 = classify_cop_sample(mode, lwt, outdoor, cop)
    r2 = classify_cop_sample(mode, lwt, outdoor, cop)
    assert r1 == r2


@settings(max_examples=200)
@given(
    mode=VALID_MODES,
    lwt=st.floats(min_value=-30, max_value=90),
    outdoor=st.floats(min_value=-40, max_value=45),
    cop_low=st.floats(min_value=0.1, max_value=20),
    scale=st.floats(min_value=2, max_value=20),
)
def test_fuzz_classifier_monotonic(mode, lwt, outdoor, cop_low, scale):
    """R640: hogere cop -> 'hoger' class (accept < flag < reject).

    Voor vaste (mode, lwt, outdoor): als cop_low 'accept' is,
    dan is cop_high >= cop_low nog steeds 'accept' of 'flag' of 'reject'
    (nooit terug naar accept als de lagere al flag was).
    """
    if lwt <= outdoor:
        return  # not_applicable, geen monotonic om te testen
    # R640: hypothesis can generate lwt/outdoor extremely close together
    # (e.g. 30.0 and 29.999999999999996). Adding 273.15 loses precision,
    # making th == tc -> classifier legitimately returns not_applicable.
    # Conservative behavior; real sensors have 0.1 C resolution, never
    # hits this. Documented in physics.py docstring.
    th = lwt + 273.15
    tc = outdoor + 273.15
    if th <= tc:
        return  # float-precision edge -> classifier returns not_applicable
    cop_high = cop_low * scale
    r_low = classify_cop_sample(mode, lwt, outdoor, cop_low)
    r_high = classify_cop_sample(mode, lwt, outdoor, cop_high)
    order = {"accept": 0, "flag": 1, "reject": 2, "not_applicable": -1}
    assert order[r_high] >= order[r_low], (
        f"monotonicity broken: cop={cop_low} -> {r_low}, "
        f"cop={cop_high} -> {r_high}"
    )


# ============================================================
# Boundary precisie — de definities van de 3 klassen
# ============================================================

def test_classifier_boundary_accept_upper():
    """cop == accept_thr -> accept (boundary is <=)."""
    lwt, outdoor = 30.0, 10.0
    th = lwt + 273.15
    tc = outdoor + 273.15
    carnot = th / (th - tc)
    accept_thr = carnot * CARNOT_EFFICIENCY_FACTOR * ACCEPT_MARGIN
    assert classify_cop_sample("heating", lwt, outdoor, accept_thr) == "accept"
    assert classify_cop_sample("heating", lwt, outdoor,
                                accept_thr + 0.001) == "flag"


def test_classifier_boundary_reject_lower():
    """cop == reject_thr -> flag (reject is strictly >)."""
    lwt, outdoor = 30.0, 5.0
    th = lwt + 273.15
    tc = outdoor + 273.15
    carnot = th / (th - tc)
    reject_thr = carnot * REJECT_MULTIPLIER
    assert classify_cop_sample("heating", lwt, outdoor, reject_thr) == "flag"
    assert classify_cop_sample("heating", lwt, outdoor,
                                reject_thr + 0.001) == "reject"
