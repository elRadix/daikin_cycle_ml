"""Compressor cycle detection for Daikin Cycle ML."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ..const import (
    MAX_THERMAL_KW,
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
    ATTR_3WAY_VALVE,
    DEFAULT_COMPRESSOR_RPS_THRESHOLD,
    DEFAULT_FALLBACK_POWER_THRESHOLD_W,
    MAX_CYCLE_DURATION_S,
    OP_MODE_COOLING,
    OP_MODE_DHW,
    OP_MODE_HEATING,
    STATE_IDLE,
    STATE_RUNNING,
)
from .attribute_compat import build_compat_view

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


VALVE_DEBOUNCE_S: float = 30.0
"""Debounce for valve-corroborated mode transitions."""


MODE_DEBOUNCE_S: float = 60.0
"""Debounce for mode-string transitions without valve corroboration."""


def _mode_tokens(raw: str) -> set[str]:
    """Split "Heating + DHW" / "Cooling/DHW" into lowercase tokens."""
    s = raw.strip().lower().replace("/", "+")
    return {t.strip() for t in s.split("+") if t.strip()}


def _parse_valve(attrs: Mapping[str, Any]) -> str | None:
    """Return ON/OFF from 3-way valve attr, or None if absent/invalid."""
    if not isinstance(attrs, Mapping):
        return None
    raw = attrs.get(ATTR_3WAY_VALVE)
    if not isinstance(raw, str):
        return None
    v = raw.strip().upper()
    return v if v in ("ON", "OFF") else None


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


def _pump_is_off(value: Any) -> bool:
    """True if pump is *explicitly* reported off.

    Recognised off-forms: ``False``, ``'OFF'``, ``'FALSE'``, ``'NO'``,
    or an empty string. Missing (``None``) and any numeric value return
    ``False`` — a missing attribute is not the same as a reported off,
    and the ESPAltherma source reports pump as str/bool, never as int.

    R307 originally used ``pump is False``, an identity check. The
    source attribute passes through attribute_reader._normalize()
    which may return ``bool``, ``str`` (``'OFF'``/``'ON'``),
    ``float``, or ``None``. When the value is not the ``False``
    singleton, the R307 close-path was skipped and the detector
    could remain RUNNING for hours (issue #49).
    """
    if value is False:
        return True
    if value is None:
        return False  # missing attr != reported off; fall-through handles it
    if isinstance(value, str):
        return value.strip().upper() in ("OFF", "FALSE", "NO", "")
    # Numerics (0, 0.0) and any other type are treated as unknown, not off:
    # the ESPAltherma source reports pump as str ("ON"/"OFF"), never as int.
    return False


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
    """Return "heating"|"cooling"|"dhw"|"unknown".

    Token-based matching handles compound I/U modes like
    "Heating + DHW" and "Cooling/DHW". DHW wins because the 3-way
    valve is diverted to the tank and heating is paused (not
    concurrent). Reference: issue #116, handoff v91.0 R441/R442.
    """
    iu = attrs.get(ATTR_IU_OPERATION_MODE)
    if isinstance(iu, str):
        tokens = _mode_tokens(iu)
        if OP_MODE_DHW.lower() in tokens:
            return "dhw"
        for key, val in _MODE_MAP.items():
            if val in tokens:
                return key
    op = attrs.get(ATTR_OPERATION_MODE)
    if isinstance(op, str):
        tokens = _mode_tokens(op)
        if OP_MODE_DHW.lower() in tokens:
            return "dhw"
        for key, val in _MODE_MAP.items():
            if val in tokens:
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




def _apply_thermal_sanity_gate(thermal_kw_avg: float | None) -> float | None:
    """v1.13.0 #129: NULL thermal_kw_avg on physical impossibilities.

    Magnitude gate only -- a single steady-state sample is a valid
    measurement; 0-sample artifacts land in the extreme (>MAX) bucket.
    """
    if thermal_kw_avg is not None and thermal_kw_avg > MAX_THERMAL_KW:
        _LOGGER.info(
            "thermal_kw_avg %.2f > MAX_THERMAL_KW %.2f, nulling",
            thermal_kw_avg, MAX_THERMAL_KW,
        )
        return None
    return thermal_kw_avg
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
        self._pending_mode: str | None = None
        self._pending_mode_since: float = 0.0

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
            "pending_mode": self._pending_mode,
            "pending_mode_since": self._pending_mode_since,
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
        _pm = payload.get("pending_mode")
        self._pending_mode = _pm if isinstance(_pm, str) else None
        _pms = payload.get("pending_mode_since")
        self._pending_mode_since = (
            float(_pms)
            if isinstance(_pms, (int, float)) and not isinstance(_pms, bool)
            else 0.0
        )

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
        self._pending_mode = None
        self._pending_mode_since = 0.0

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
            "thermal_kw_avg": _apply_thermal_sanity_gate(
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

    def _should_split(self, attrs: Mapping[str, Any], now: float) -> bool:
        """Return True if RUNNING cycle should split to DHW here.

        Only splits on I/U mode token transition to DHW. Valve ON
        corroborates and shortens debounce (30s vs 60s). Valve alone
        never splits -- Daikin 3-way valve rests ON on power-loss
        fail-safe (tests/test_52a_dhw_dtk.py, test_31cd_coverage.py).
        """
        # R466 (v1.12.5 #144): reverse split -- DHW cycle but source
        # reports heating/cooling. Handles stuck-mode-on-restore (#144)
        # and legit DHW->heat transitions. Bounded by MAX_CYCLE_DURATION_S
        # hard-cap which fires earlier in update().
        current = classify_mode(attrs)
        if self._mode == "dhw" and current in ("heating", "cooling"):
            if self._pending_mode != current:
                self._pending_mode = current
                self._pending_mode_since = now
                return False
            return (now - self._pending_mode_since) >= MODE_DEBOUNCE_S
        if self._mode == "dhw":
            self._pending_mode = None
            self._pending_mode_since = 0.0
            return False
        if classify_mode(attrs) != "dhw":
            self._pending_mode = None
            self._pending_mode_since = 0.0
            return False
        debounce = (
            VALVE_DEBOUNCE_S if _parse_valve(attrs) == "ON"
            else MODE_DEBOUNCE_S
        )
        if self._pending_mode != "dhw":
            self._pending_mode = "dhw"
            self._pending_mode_since = now
            return False
        return (now - self._pending_mode_since) >= debounce

    def update(
        self,
        attrs: Mapping[str, Any],
        now: float,
        power_w: float | None = None,
    ) -> dict[str, Any] | None:
        attrs = build_compat_view(attrs)
        """Process one sample. Returns cycle record on close, else None.

        R307: pump=OFF in RUNNING state is a soft signal, not a hard stop,
        as long as the compressor is still running. Only after
        PUMP_OFF_MAX_SAMPLES consecutive pump-off samples is the cycle
        closed. In IDLE state pump=OFF is still an unconditional skip.

        R315: any RUNNING cycle exceeding MAX_CYCLE_DURATION_S is force-
        closed on the next tick, regardless of pump/compressor state.
        """
        # R315: hard cap -- force close any cycle exceeding MAX_CYCLE_DURATION_S.
        if self._state == STATE_RUNNING and self._start_ts is not None:
            if (now - self._start_ts) > MAX_CYCLE_DURATION_S:
                _LOGGER.warning(
                    "Cycle exceeded hard cap %.0fs (start=%s mode=%s); forcing close",
                    MAX_CYCLE_DURATION_S, self._start_ts, self._mode,
                )
                return self._close(now)

        pump = attrs.get(ATTR_WATER_PUMP_OPERATION)

        # R307: IDLE + pump=OFF -> no active cycle to protect, skip entirely.
        if _pump_is_off(pump) and self._state == STATE_IDLE:
            return None

        if self._start_ts is not None and now < self._start_ts:
            _LOGGER.debug("Clock skew detected (now < start_ts), ignoring sample")
            return None

        on = detect_compressor_on(attrs, self._options, power_w)

        # R307: RUNNING + pump=OFF -> tolerate pump-off while compressor runs.
        if _pump_is_off(pump) and self._state == STATE_RUNNING:
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
            if self._should_split(attrs, now):
                record = self._close(now)
                self._state = STATE_RUNNING
                self._start_ts = now
                self._mode = classify_mode(attrs)
                self._accumulate(attrs)
                return record
            self._accumulate(attrs)
            return None

        return self._close(now)
