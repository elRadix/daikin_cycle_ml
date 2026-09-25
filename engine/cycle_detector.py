"""Compressor cycle detection for Daikin Cycle ML."""
from __future__ import annotations

import logging
from typing import Any, Mapping

from ..const import (
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_OPERATION_MODE,
    ATTR_OUTDOOR_AIR_R1T,
    DEFAULT_COMPRESSOR_RPS_THRESHOLD,
    DEFAULT_FALLBACK_POWER_THRESHOLD_W,
    OP_MODE_COOLING,
    OP_MODE_DHW,
    OP_MODE_HEATING,
    STATE_IDLE,
    STATE_RUNNING,
)

_LOGGER = logging.getLogger(__name__)

_MODE_MAP = {
    "heating": OP_MODE_HEATING.lower(),
    "cooling": OP_MODE_COOLING.lower(),
    "dhw": OP_MODE_DHW.lower(),
}


def _safe_float(value: Any) -> float | None:
    """Return value as float if it is a real number, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def detect_compressor_on(
    attrs: Mapping[str, Any],
    options: Mapping[str, Any] | None = None,
    power_w: float | None = None,
) -> bool:
    """True if RPS above threshold OR fallback power above threshold."""
    opts = options or {}
    rps_thr = float(
        opts.get("compressor_rps_threshold", DEFAULT_COMPRESSOR_RPS_THRESHOLD)
    )
    pwr_thr = float(
        opts.get("fallback_power_threshold_w", DEFAULT_FALLBACK_POWER_THRESHOLD_W)
    )
    rps = _safe_float(attrs.get(ATTR_INV_FREQUENCY_RPS))
    if rps is not None and rps > rps_thr:
        return True
    if power_w is not None and power_w > pwr_thr:
        return True
    return False


def classify_mode(attrs: Mapping[str, Any]) -> str:
    """Return 'heating' | 'cooling' | 'dhw' | 'unknown'.

    Primary source is I/U operation mode (Operation Mode reports
    Fan Only as fallback when the compressor is off).
    """
    iu = attrs.get(ATTR_IU_OPERATION_MODE)
    if isinstance(iu, str):
        low = iu.strip().lower()
        for key, val in _MODE_MAP.items():
            if low == val:
                return key
    op = attrs.get(ATTR_OPERATION_MODE)
    if isinstance(op, str):
        low = op.strip().lower()
        for key, val in _MODE_MAP.items():
            if low == val:
                return key
    return "unknown"


def _compute_dt(attrs: Mapping[str, Any]) -> float | None:
    """Magnitude of leaving-minus-inlet water temperature, abs."""
    leaving = _safe_float(attrs.get(ATTR_LEAVING_WATER_AFTER_BUH))
    inlet = _safe_float(attrs.get(ATTR_INLET_WATER_R4T))
    if leaving is None or inlet is None:
        return None
    return abs(leaving - inlet)


def _is_on(attrs: Mapping[str, Any], key: str) -> bool:
    return attrs.get(key) is True


class CycleDetector:
    """Stateful detector: idle <-> running, emits cycle record on close."""

    def __init__(self, options: Mapping[str, Any] | None = None) -> None:
        self._options = dict(options or {})
        self._state = STATE_IDLE
        self._start_ts: float | None = None
        self._mode: str = "unknown"
        self._rps_samples: list[float] = []
        self._dt_samples: list[float] = []
        self._outdoor_samples: list[float] = []
        self._buh_used = False
        self._defrost_used = False

    @property
    def state(self) -> str:
        return self._state

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "start_ts": self._start_ts,
            "mode": self._mode,
            "rps_samples": len(self._rps_samples),
            "dt_samples": len(self._dt_samples),
            "buh_used": self._buh_used,
            "defrost_used": self._defrost_used,
        }

    def _reset_running(self) -> None:
        self._state = STATE_IDLE
        self._start_ts = None
        self._mode = "unknown"
        self._rps_samples = []
        self._dt_samples = []
        self._outdoor_samples = []
        self._buh_used = False
        self._defrost_used = False

    def _accumulate(self, attrs: Mapping[str, Any]) -> None:
        rps = _safe_float(attrs.get(ATTR_INV_FREQUENCY_RPS))
        if rps is not None:
            self._rps_samples.append(rps)
        dt = _compute_dt(attrs)
        if dt is not None:
            self._dt_samples.append(dt)
        out = _safe_float(attrs.get(ATTR_OUTDOOR_AIR_R1T))
        if out is not None:
            self._outdoor_samples.append(out)
        if _is_on(attrs, ATTR_BUH_STEP1) or _is_on(attrs, ATTR_BUH_STEP2):
            self._buh_used = True
        if _is_on(attrs, ATTR_DEFROST_OPERATION):
            self._defrost_used = True

    def _close(self, now: float) -> dict[str, Any]:
        start = self._start_ts or now
        duration = max(0, int(now - start))
        rps_avg = (
            sum(self._rps_samples) / len(self._rps_samples)
            if self._rps_samples else None
        )
        dt_avg = (
            sum(self._dt_samples) / len(self._dt_samples)
            if self._dt_samples else None
        )
        outdoor = (
            self._outdoor_samples[-1] if self._outdoor_samples else None
        )
        record = {
            "start_ts": start,
            "end_ts": now,
            "duration_s": duration,
            "mode": self._mode,
            "rps_max": max(self._rps_samples) if self._rps_samples else None,
            "rps_avg": rps_avg,
            "dT_max": max(self._dt_samples) if self._dt_samples else None,
            "dT_avg": dt_avg,
            "outdoor_temp": outdoor,
            "buh_used": self._buh_used,
            "defrost_used": self._defrost_used,
        }
        self._reset_running()
        return record

    def update(
        self,
        attrs: Mapping[str, Any],
        now: float,
        power_w: float | None = None,
    ) -> dict[str, Any] | None:
        """Process one sample. Returns cycle record on close, else None."""
        if self._start_ts is not None and now < self._start_ts:
            _LOGGER.debug("Clock skew detected (now < start_ts), ignoring sample")
            return None

        on = detect_compressor_on(attrs, self._options, power_w)

        if self._state == STATE_IDLE:
            if on:
                self._state = STATE_RUNNING
                self._start_ts = now
                self._mode = classify_mode(attrs)
                self._accumulate(attrs)
            return None

        if on:
            self._accumulate(attrs)
            return None

        return self._close(now)
