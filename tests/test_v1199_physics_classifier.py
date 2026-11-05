"""v1.19.9 #123: 3-tier COP classifier (accept / flag / reject).

Covers all Model 2 scenarios from the #123 analysis:
- accept: normal operation + borderline samples within noise margin
- flag: suspicious but stored (is_transition_artifact=1)
- reject: physically impossible (>1.5x Carnot), not stored
- not_applicable: cooling, unknown mode, missing data, lwt<=outdoor
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine.physics import (
    ACCEPT_MARGIN,
    CARNOT_EFFICIENCY_FACTOR,
    REJECT_MULTIPLIER,
    classify_cop_sample,
    get_physical_cop_ceiling,
)


# --- Constants sanity ---

def test_factor_matches_rfi_127_answer():
    """#127 Q1 answer: 0.65 practical derating."""
    assert CARNOT_EFFICIENCY_FACTOR == 0.65


def test_margin_absorbs_sensor_noise():
    """+/-0.3K sensor tolerance -> ~5% ceiling variation."""
    assert ACCEPT_MARGIN == 1.05


def test_reject_at_150pct_carnot():
    """Anything > 150% theoretical maximum is unphysical."""
    assert REJECT_MULTIPLIER == 1.50


# --- "accept" class: normal operation ---

def test_typical_heating_accept():
    # Heating lwt=30 outdoor=10 -> Carnot=15.16, ceiling=9.85, accept<=10.34
    assert classify_cop_sample("heating", 30.0, 10.0, 5.0) == "accept"


def test_typical_dhw_accept():
    # DHW lwt=55 outdoor=10 -> Carnot=6.51, ceiling=4.23, accept<=4.44
    assert classify_cop_sample("dhw", 55.0, 10.0, 3.5) == "accept"


def test_borderline_within_margin_accept():
    """Real prod-1 2026-11-05: cop=8.48, lwt=31.4, out=8.0.

    Carnot=13.01, ceiling=8.46, accept<=8.88. Sample 8.48 < 8.88 -> accept.
    Pre-fix factor 0.55 would give ceiling=7.16 and flag this sample.
    The 1.05 margin exists precisely to absorb such borderline noise.
    """
    assert classify_cop_sample("heating", 31.4, 8.0, 8.48) == "accept"


# --- "flag" class: suspicious, stored with marker ---

def test_moderate_artifact_flags():
    """Real prod-1: cop=7.99, lwt=32.3, out=4.7.

    Carnot=11.07, ceiling=7.19, accept<=7.55, reject>16.60.
    7.99 falls in (7.55, 16.60] -> flag.
    """
    assert classify_cop_sample("heating", 32.3, 4.7, 7.99) == "flag"


def test_high_cop_artifact_flags():
    """Real prod-1: cop=10.05, lwt=38.5, out=14.7.

    Carnot=13.09, ceiling=8.51, accept<=8.94, reject>19.64.
    10.05 falls in (8.94, 19.64] -> flag.
    """
    assert classify_cop_sample("heating", 38.5, 14.7, 10.05) == "flag"


def test_dhw_transition_artifact_flags():
    """Real prod-1: cop=8.01, lwt=62.2, out=12.5 (post heating->DHW).

    Carnot=6.75, ceiling=4.39, accept<=4.61, reject>10.12.
    8.01 falls in (4.61, 10.12] -> flag.
    """
    assert classify_cop_sample("dhw", 62.2, 12.5, 8.01) == "flag"


def test_cop_19_5_legacy_artifact_flags():
    """Sample id=148 from RFI #127 Q4: cop=19.5 at heating transition.

    lwt=27, out=9.7 -> Carnot=15.93, ceiling=10.35, accept<=10.87, reject>23.90.
    19.5 falls in (10.87, 23.90] -> flag.
    """
    assert classify_cop_sample("heating", 27.0, 9.7, 19.5) == "flag"


# --- "reject" class: physically impossible ---

def test_extreme_cop_rejects():
    """cop=100 at lwt=30/out=5: Carnot=12.13, reject>18.19 -> reject."""
    assert classify_cop_sample("heating", 30.0, 5.0, 100.0) == "reject"


def test_just_beyond_carnot_150pct_rejects():
    """Carnot=12.13 -> reject_thr=18.19. cop=19 -> reject."""
    assert classify_cop_sample("heating", 30.0, 5.0, 19.0) == "reject"


# --- "not_applicable" class ---

def test_cooling_mode_not_applicable():
    assert classify_cop_sample("cooling", 12.0, 35.0, 4.0) == "not_applicable"


def test_unknown_mode_not_applicable():
    assert classify_cop_sample("defrost", 35.0, 5.0, 3.0) == "not_applicable"


def test_missing_lwt_not_applicable():
    assert classify_cop_sample("heating", None, 5.0, 3.0) == "not_applicable"


def test_missing_outdoor_not_applicable():
    assert classify_cop_sample("heating", 30.0, None, 3.0) == "not_applicable"


def test_missing_cop_not_applicable():
    assert classify_cop_sample("heating", 30.0, 5.0, None) == "not_applicable"


def test_lwt_equals_outdoor_not_applicable():
    """No thermal lift -> division guard -> not_applicable."""
    assert classify_cop_sample("heating", 5.0, 5.0, 3.0) == "not_applicable"


def test_lwt_below_outdoor_not_applicable():
    assert classify_cop_sample("heating", 0.0, 5.0, 3.0) == "not_applicable"


# --- Integration with get_physical_cop_ceiling ---

def test_classifier_uses_same_factor_as_ceiling():
    """Ceiling from get_physical_cop_ceiling and classify must be consistent.

    For any (mode, lwt, outdoor), the accept_thr used inside classify
    must equal get_physical_cop_ceiling * ACCEPT_MARGIN.
    """
    ceiling = get_physical_cop_ceiling("heating", 30.0, 5.0)
    assert ceiling is not None
    # cop just below accept_thr -> accept
    assert classify_cop_sample("heating", 30.0, 5.0, ceiling * ACCEPT_MARGIN) == "accept"
    # cop just above accept_thr -> flag
    assert classify_cop_sample(
        "heating", 30.0, 5.0, ceiling * ACCEPT_MARGIN + 0.01
    ) == "flag"
