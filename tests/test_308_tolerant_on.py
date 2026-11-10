"""#308: tolerant on-detection across v1 (bool) and v2 (str/int) payloads."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.const import tolerant_on


@pytest.mark.parametrize("raw,expected",[
    (None,False),(True,True),(False,False),
    (1,True),(0,False),(2,True),(-1,True),
    (1.0,True),(0.0,False),
    ("on",True),("On",True),("ON",True),(" on ",True),
    ("true",True),("TRUE",True),
    ("1",True),("yes",True),("open",True),("active",True),
    ("off",False),("false",False),("0",False),("",False),
    ("  ",False),("maybe",False),
    ([],False),({},False),
])
def test_tolerant_on_matrix(raw,expected):
    assert tolerant_on(raw) is expected


def test_cycle_detector_is_on_string():
    from custom_components.daikin_cycle_ml.engine.cycle_detector import _is_on
    assert _is_on({"x":"on"},"x") is True
    assert _is_on({"x":1},"x") is True
    assert _is_on({"x":"1"},"x") is True
    assert _is_on({"x":"off"},"x") is False
    assert _is_on({},"x") is False


def test_binary_sensor_attr_on_string():
    from custom_components.daikin_cycle_ml.binary_sensor import _attr_on
    assert _attr_on({"x":"on"},"x") is True
    assert _attr_on({"x":1},"x") is True
    assert _attr_on({"x":"1"},"x") is True
    assert _attr_on({"x":"off"},"x") is False
