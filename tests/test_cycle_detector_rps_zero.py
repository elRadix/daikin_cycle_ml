"""R634, R636: rps=0 must not trigger cycle via power fallback alone.

Real-world reproduction from prod-1 DB 2026-11-06:
  - id=182 (10-26 12:47:09) 29s heating rps=0 dT=0.2, no cop_samples
  - id=279 (11-04 13:10:47) 29s heating rps=0 dT=2.6, no cop_samples

Both opened on `power_w>200W` alone, despite rps explicitly reporting 0
(= compressor not running per ESPAltherma firmware). This is a phantom
cycle: pump/electronics spike >200W momentarily, cycle opens, closes 30s
later. Correct behavior: rps=0 is authoritative "compressor OFF".
"""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    detect_compressor_on,
)


class TestRpsZeroIsAuthoritative:
    """rps explicitly present and 0 must NOT open cycle via power alone."""

    def test_rps_zero_with_power_spike_does_not_open(self) -> None:
        """R634 repro of prod-1 ids 182/279."""
        attrs = {
            "INV frequency (rps)": 0,      # Explicit zero
            "Flow sensor (l/min)": 20.0,   # Pump running
            # no COP, no heat production evidence
        }
        result = detect_compressor_on(attrs, power_w=250)
        assert not result, (
            "rps=0 with power=250W must NOT open cycle: "
            "power spike alone is pump/electronics, not compressor. "
            "Real prod-1: ids 182/279 spurious cycles."
        )

    def test_rps_zero_low_power_does_not_open(self) -> None:
        """Baseline: rps=0 + low power must not open either."""
        attrs = {"INV frequency (rps)": 0}
        assert not detect_compressor_on(attrs, power_w=100)

    def test_rps_zero_with_active_cop_still_opens(self) -> None:
        """rps=0 but flow>5 AND cop>1.5 is a real (modulating) run."""
        attrs = {
            "INV frequency (rps)": 0,
            "Flow sensor (l/min)": 22.0,
            "COP": 3.5,  # Real heat production
        }
        # This is the v1.19.7 #261 fallback — real activity evidence
        assert detect_compressor_on(attrs, power_w=250)


class TestRpsMissingUsesPowerFallback:
    """When rps is missing/None, power fallback (v1.19.7 #261) still works."""

    def test_rps_missing_power_high_opens(self) -> None:
        """rps sensor unavailable → power fallback opens cycle."""
        attrs = {"Flow sensor (l/min)": 20.0}  # no rps key
        assert detect_compressor_on(attrs, power_w=800)

    def test_rps_missing_power_low_does_not_open(self) -> None:
        """rps missing + power low → no cycle."""
        attrs = {"Flow sensor (l/min)": 20.0}
        assert not detect_compressor_on(attrs, power_w=150)

    def test_rps_none_power_high_opens(self) -> None:
        """rps=None (explicit) behaves same as missing → power fallback."""
        attrs = {"INV frequency (rps)": None}
        assert detect_compressor_on(attrs, power_w=800)

    def test_rps_invalid_string_power_high_opens(self) -> None:
        """rps='Invalid' (ESPAltherma quirk) → power fallback."""
        attrs = {"INV frequency (rps)": "Invalid"}
        assert detect_compressor_on(attrs, power_w=800)


class TestNormalRpsBehaviorUnchanged:
    """Above-threshold rps always opens."""

    def test_rps_above_threshold_opens(self) -> None:
        attrs = {"INV frequency (rps)": 30}
        assert detect_compressor_on(attrs, power_w=None)

    def test_rps_at_threshold_does_not_open(self) -> None:
        """rps=3 is exactly threshold, not above → closed."""
        attrs = {"INV frequency (rps)": 3}
        # threshold is 3, so >3 required
        assert not detect_compressor_on(attrs, power_w=None)
