"""v1.12.5 #133: _cop_confidence reformulation (4-tier, count-only)."""
from custom_components.daikin_cycle_ml.coordinator import _cop_confidence


def test_none_zero():
    assert _cop_confidence(0) == "none"


def test_none_one():
    assert _cop_confidence(1) == "none"


def test_none_two():
    assert _cop_confidence(2) == "none"


def test_low_three():
    assert _cop_confidence(3) == "low"


def test_low_four():
    assert _cop_confidence(4) == "low"


def test_low_five():
    assert _cop_confidence(5) == "low"


def test_medium_six():
    assert _cop_confidence(6) == "medium"


def test_medium_ten():
    assert _cop_confidence(10) == "medium"


def test_medium_eleven():
    assert _cop_confidence(11) == "medium"


def test_high_twelve():
    assert _cop_confidence(12) == "high"


def test_high_twenty():
    assert _cop_confidence(20) == "high"


def test_high_hundred():
    assert _cop_confidence(100) == "high"
