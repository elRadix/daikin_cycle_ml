"""Compressor cycle detection for Daikin Cycle ML."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ..const import (
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ATTR_FLOW_SENSOR,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_OPERATION_MODE,
    ATTR_OUTDOOR_AIR_R1T,
    ATTR_WATER_PUMP_OPERATION,
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


MAX_RESUME_GAP_S: float = 6 * 3600.0
"""Maximum gap (seconds) at which a RUNNING detector state may be resumed."""


PUMP_OFF_MAX_SAMPLES: int = 20
"""Consecutive pump-off samples in RUNNING before closing the cycle."""


def _float_list(value: Any) -> list[float]:
    """Return a list of floats, dropping non-numeric entries."""
    if not isinstance(value, list):
        return []
    out: list[float] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            out.append(float(item))
    return out


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
    return bool(power_w is not None and power_w > pwr_thr)


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
        self._thermal_kw_samples: list[float] = []
        self._pump_off_count: int = 0

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize RUNNING state. IDLE serializes to empty dict."""
        if self._state != STATE_RUNNING:
            return {}
        return {
            "state": self._state,
            "start_ts": self._start_ts,
            "mode": self._mode,
            "rps_samples": list(self._rps_samples),
            "dt_samples": list(self._dt_samples),
            "outdoor_samples": list(self._outdoor_samples),
            "buh_used": self._buh_used,
            "defrost_used": self._defrost_used,
            "thermal_kw_samples": list(self._thermal_kw_samples),
        }

    def restore_from_dict(self, payload: Any, now: float) -> None:
        """Restore RUNNING state. Silent no-op on invalid or stale payload."""
        if not isinstance(payload, dict) or not payload:
            return
        if payload.get("state") != STATE_RUNNING:
            return
        start_ts = payload.get("start_ts")
        if isinstance(start_ts, bool) or not isinstance(start_ts, (int, float)):
            return
        gap = now - float(start_ts)
        if gap > MAX_RESUME_GAP_S:
            _LOGGER.warning(
                "Detector resume gap %.0fs exceeds max %.0fs; abandoning cycle",
                gap, MAX_RESUME_GAP_S,
            )
            return
        self._state = STATE_RUNNING
        self._start_ts = float(start_ts)
        self._mode = str(payload.get("mode") or "unknown")
        self._rps_samples = _float_list(payload.get("rps_samples"))
        self._dt_samples = _float_list(payload.get("dt_samples"))
        self._outdoor_samples = _float_list(payload.get("outdoor_samples"))
        self._buh_used = bool(payload.get("buh_used", False))
        self._defrost_used = bool(payload.get("defrost_used", False))
        self._thermal_kw_samples = _float_list(payload.get("thermal_kw_samples"))

    def _reset_running(self) -> None:
        self._state = STATE_IDLE
        self._start_ts = None
        self._mode = "unknown"
        self._rps_samples = []
        self._dt_samples = []
        self._outdoor_samples = []
        self._buh_used = False
        self._defrost_used = False
        self._thermal_kw_samples = []
        self._pump_off_count = 0

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
        flow = _safe_float(attrs.get(ATTR_FLOW_SENSOR))
        if flow is not None and dt is not None and dt > 0:
            # P = m_dot * cp * dT ; m_dot = flow_lmin/60 kg/s ; cp = 4.18 kJ/kgK
            kw = (flow / 60.0) * 4.18 * dt
            self._thermal_kw_samples.append(kw)

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
            "thermal_kw_avg": (
                sum(self._thermal_kw_samples) / len(self._thermal_kw_samples)
                if self._thermal_kw_samples else None
            ),
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
        """Process one sample. Returns cycle record on close, else None.

        R307: pump=OFF in RUNNING state is a soft signal, not a hard stop,
        as long as the compressor is still running. Only after
        PUMP_OFF_MAX_SAMPLES consecutive pump-off samples is the cycle
        closed. In IDLE state pump=OFF is still an unconditional skip.
        """
        pump = attrs.get(ATTR_WATER_PUMP_OPERATION)

        # R307: IDLE + pump=OFF -> no active cycle to protect, skip entirely.
        if pump is False and self._state == STATE_IDLE:
            return None

        if self._start_ts is not None and now < self._start_ts:
            _LOGGER.debug("Clock skew detected (now < start_ts), ignoring sample")
            return None

        on = detect_compressor_on(attrs, self._options, power_w)

        # R307: RUNNING + pump=OFF -> tolerate pump-off while compressor runs.
        if pump is False and self._state == STATE_RUNNING:
            if on:
                self._accumulate(attrs)
                self._pump_off_count += 1
                if self._pump_off_count >= PUMP_OFF_MAX_SAMPLES:
                    return self._close(now)
                return None
            return self._close(now)

        # Any sample with pump != OFF resets the tolerance counter.
        self._pump_off_count = 0

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
