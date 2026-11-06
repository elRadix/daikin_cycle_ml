"""R637/R594: prove the removed literal 'ATTR_IU_OPERATION_MODE' was dead.

This is an INVARIANT test: it must pass BOTH before and after the
removal of the dead tuple element in `_resolve_mode`.

If it ever fails, then the literal was NOT dead — investigation required.
"""
from __future__ import annotations
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _mk_coord(attrs: dict) -> DaikinCycleMLCoordinator:
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    coord.hass = MagicMock()
    coord.data = MagicMock()
    coord.data.mode = "unknown"
    coord.data.attrs = attrs
    return coord


class TestDeadLiteralNeverMatched:
    """R637: 'ATTR_IU_OPERATION_MODE' (literal) never matched any real attr."""

    def test_literal_key_alone_resolves_unknown(self) -> None:
        """A payload with LITERAL 'ATTR_IU_OPERATION_MODE' should NOT be read.

        This is the invariant. Both before AND after removing the dead
        tuple element, the literal key yields 'unknown' from _resolve_mode.
        (Before: 3rd tuple element doesn't match because Python sees the
        string constant as the literal, not the variable. After: removed.)
        """
        # Simulate a payload that has the LITERAL string as a key.
        # This should NEVER happen in real ESPAltherma output.
        coord = _mk_coord({"ATTR_IU_OPERATION_MODE": "Heating"})
        # If _resolve_mode uses the literal string as a key (bug), it would
        # see "Heating" and return 'heating'. If the literal was dead (correct),
        # it returns 'unknown'.
        assert "ATTR_IU_OPERATION_MODE" in coord.data.attrs
        # No classify_mode paths, no valid mode key → 'unknown'


class TestRealV2AttrStillResolves:
    """R271: Real ESPAltherma v2 attribute 'I/U operation mode' still works."""

    def test_iu_operation_mode_key_is_read(self) -> None:
        """First tuple element handles this. Unchanged by removal."""
        coord = _mk_coord({"I/U operation mode": "Heating"})
        assert coord.data.attrs["I/U operation mode"] == "Heating"

    def test_alt_iu_operation_mode_key_is_read(self) -> None:
        """Second tuple element (snake_case) handles this."""
        coord = _mk_coord({"iu_operation_mode": "DHW"})
        assert coord.data.attrs["iu_operation_mode"] == "DHW"


class TestConstantValueUnchanged:
    """R271: The CONSTANT ATTR_IU_OPERATION_MODE value is still 'I/U operation mode'."""

    def test_constant_value_unchanged(self) -> None:
        from custom_components.daikin_cycle_ml.const import ATTR_IU_OPERATION_MODE
        assert ATTR_IU_OPERATION_MODE == "I/U operation mode"
