"""Advice generation from anomaly + cycle context (Batch 7c). Pure Python."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from ..ml.features import FEATURE_NAMES

_LOGGER = logging.getLogger(__name__)

PRIORITY_HIGH = 1
PRIORITY_MED = 2
PRIORITY_LOW = 3

CAT_ANOMALY = "anomaly"
CAT_PATTERN = "pattern"
CAT_EFFICIENCY = "efficiency"

# feature index lookup by name
_FEATURE_INDEX = {name: i for i, name in enumerate(FEATURE_NAMES)}

# top_dim feature name -> (priority, code, title, description)
_TOP_DIM_ADVICE: dict[str, tuple[int, str, str, str]] = {
    "duration_s": (
        PRIORITY_HIGH, "anomaly_duration",
        "Cycle duration outside normal range",
        "Compressor runtime deviates strongly from baseline. "
        "Check setpoint delta and hysteresis.",
    ),
    "dT_max": (
        PRIORITY_HIGH, "anomaly_dt",
        "dT outside normal range",
        "Water-side dT is unusual. Check flow rate, "
        "water filter and heat exchanger.",
    ),
    "dT_avg": (
        PRIORITY_MED, "anomaly_dt_avg",
        "Average dT unusual",
        "Average dT across the cycle deviates from baseline. "
        "Review flow and load balance.",
    ),
    "rps_max": (
        PRIORITY_MED, "anomaly_rps",
        "Compressor load unusual",
        "Compressor frequency peaked outside baseline. "
        "Check load conditions and refrigerant charge.",
    ),
    "rps_avg": (
        PRIORITY_MED, "anomaly_rps_avg",
        "Average compressor load unusual",
        "Average RPS across the cycle deviates from baseline.",
    ),
    "outdoor_temp": (
        PRIORITY_LOW, "anomaly_outdoor",
        "Outdoor temperature outlier",
        "Cycle ran under unusual outdoor conditions \u2014 "
        "may be environmental, not a fault.",
    ),
    "buh_used": (
        PRIORITY_HIGH, "anomaly_buh",
        "Backup heater activated unusually",
        "BUH usage is above baseline. Check heat pump capacity "
        "and setpoint strategy.",
    ),
    "defrost_used": (
        PRIORITY_MED, "anomaly_defrost",
        "Defrost behaviour unusual",
        "Defrost occurred at an atypical moment. "
        "Check outdoor unit and frosting conditions.",
    ),
}


@dataclass(frozen=True)
class ActionAdvice:
    priority: int
    category: str
    code: str
    title: str
    description: str
    context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority": self.priority,
            "category": self.category,
            "code": self.code,
            "title": self.title,
            "description": self.description,
            "context": self.context or {},
        }


def _add(out: list[ActionAdvice], adv: ActionAdvice) -> None:
    if not any(a.code == adv.code for a in out):
        out.append(adv)


def _mode_context(mode: str | None) -> str:
    if mode == "DHW":
        return " (DHW tank)"
    if mode == "Heating":
        return " (space heating)"
    if mode == "Cooling":
        return " (space cooling)"
    return ""


def generate_advice(
    anomaly: Any,
    record: Mapping[str, Any] | None,
    mode: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> list[ActionAdvice]:
    """Return ordered advice list (highest priority first). Never raises."""
    try:
        return _generate(anomaly, record or {}, mode, options or {})
    except Exception:  # noqa: BLE001
        _LOGGER.exception("generate_advice failed")
        return []


def _generate(
    anomaly: Any,
    record: Mapping[str, Any],
    mode: str | None,
    options: Mapping[str, Any],
) -> list[ActionAdvice]:
    out: list[ActionAdvice] = []
    ctx_suffix = _mode_context(mode)

    # 1. Anomaly-based advice
    sev = getattr(anomaly, "severity", None)
    is_anom = bool(getattr(anomaly, "is_anomaly", False))
    top_dim = getattr(anomaly, "top_dim", None)
    if is_anom and top_dim is not None and 0 <= top_dim < len(FEATURE_NAMES):
        feature = FEATURE_NAMES[top_dim]
        spec = _TOP_DIM_ADVICE.get(feature)
        if spec is not None:
            prio, code, title, desc = spec
            if sev == "critical":
                prio = PRIORITY_HIGH
                title = "Critical: " + title
            _add(out, ActionAdvice(
                priority=prio, category=CAT_ANOMALY, code=code,
                title=title + ctx_suffix,
                description=desc,
                context={"feature": feature,
                         "z": getattr(anomaly, "max_abs_z", 0.0)},
            ))

    # 2. BUH used flag
    if record.get("buh_used"):
        _add(out, ActionAdvice(
            priority=PRIORITY_MED, category=CAT_EFFICIENCY,
            code="buh_used",
            title="Backup heater used" + ctx_suffix,
            description="BUH was active during this cycle. Consider "
                        "raising outdoor temperature threshold for BUH.",
            context={"buh_used": True},
        ))

    # 3. Defrost flag
    if record.get("defrost_used"):
        _add(out, ActionAdvice(
            priority=PRIORITY_LOW, category=CAT_EFFICIENCY,
            code="defrost_used",
            title="Defrost during cycle" + ctx_suffix,
            description="A defrost cycle occurred. Frequent defrosts may "
                        "indicate outdoor unit airflow issues.",
            context={"defrost_used": True},
        ))

    # 4. Very short duration pattern
    dur = record.get("duration_s")
    short_th = int(options.get("short_run_threshold_min", 20)) * 60
    if isinstance(dur, (int, float)) and 0 < dur < short_th:
        _add(out, ActionAdvice(
            priority=PRIORITY_MED, category=CAT_PATTERN,
            code="short_cycle_pattern",
            title="Short cycle detected" + ctx_suffix,
            description="Cycle duration under threshold. Consider wider "
                        "setpoint delta or reduced minimum runtime.",
            context={"duration_s": float(dur), "threshold_s": short_th},
        ))

    # 5. Very low dT pattern (heat not delivered well)
    dt = record.get("dT_max")
    good_dt = float(options.get("good_dt_threshold_k", 5.0))
    if isinstance(dt, (int, float)) and 0 < dt < good_dt:
        _add(out, ActionAdvice(
            priority=PRIORITY_LOW, category=CAT_EFFICIENCY,
            code="low_dt",
            title="Low dT" + ctx_suffix,
            description="dT under target. Check flow rate and water-side "
                        "pressure.",
            context={"dT_max": float(dt), "target": good_dt},
        ))

    out.sort(key=lambda a: a.priority)
    return out
