"""Notification engine v2 (12c): dynamic messages + emoji + status builder."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..const import (
    ALERT_GROUP_MAP,
    ALERT_DEDUP_OPTION_PREFIX,
    ALERT_DEDUP_OPTION_SUFFIX,
    ALERT_TYPE_EMOJI,
    NOTIF_ID_ML_ANOMALY,
    NOTIF_ID_COP_DEGRADATION,
    NOTIF_ID_DEFROST_EXCESSIVE,
    NOTIF_ID_BUH_EXCESSIVE,
    NOTIF_ID_SOURCE_STALE,
    NOTIF_ID_MISSING_ATTRIBUTES,
    NOTIF_ID_DHW_PENDULUM,
    NOTIF_ID_HIGH_CYCLE_RATE,
    NOTIF_ID_COP_VS_DATASHEET_LOW,
    NOTIF_ID_PENDULUM_DAILY,
    NOTIF_ID_PENDULUM_HOURLY,
    NOTIF_ID_SETPOINT_OSC,
    NOTIF_ID_SHORT_OFF,
    NOTIF_ID_SHORT_RUN,
    SEVERITY_EMOJI,
)
from .status_report import (
    ALERT_SCHEMA,
    build_cop_low_report,
    build_rich_alert,
    build_status_report,
    build_stooklijn_report,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_QUIET_START = "22:00"
DEFAULT_QUIET_END = "07:00"
DEFAULT_AGG_MIN = 30

SEV_WARNING = "warning"
SEV_CRITICAL = "critical"
SEV_INFO = "info"


@dataclass(frozen=True)
class AlertSpec:
    """A single alert to be emitted."""

    alert_type: str
    severity: str
    message: str
    notif_id: str
    dedupe_key: str
    persistent: bool = True
    context: dict[str, Any] | None = None


# trigger binary key -> (alert_type, severity, message template)
# --- Batch 22b: language-specific alert templates ---
ALERT_TEMPLATES_EN: dict[str, str] = {
    "pendulum_hourly": (
        "**Pendulum detected (hourly)**\n"
        "**{cph} cycles** in the last hour (target \u2264 {target_cph}).\n"
        "\U0001F4A1 Widen thermostat hysteresis, or lower the heat curve "
        "so cycles run longer.{advice}"
    ),
    "pendulum_daily": (
        "**Pendulum detected (daily)**\n"
        "**{cycles_today} cycles** today (target \u2264 {target_cpd}).\n"
        "\U0001F4A1 Check setpoint delta, hysteresis and heat curve \u2014 "
        "the pump is cycling too often.{advice}"
    ),
    "short_run": (
        "**Short run detected**\n"
        "Last cycle ran **{duration_min} min** (threshold {threshold_min} min).\n"
        "\U0001F4A1 Increase minimum runtime or smooth heat demand so the "
        "pump can stabilize.{advice}"
    ),
    "short_off": (
        "**Short off detected**\n"
        "Off time was only **{off_min} min** (threshold {threshold_min} min).\n"
        "\U0001F4A1 The pump restarts too quickly \u2014 check heat curve "
        "and hysteresis.{advice}"
    ),
    "ml_anomaly": (
        "**ML anomaly ({mode})**\n"
        "z-score **{z_max}** on **\"{top_dim}\"**.\n"
        "\U0001F4A1 Behavior deviates from learned baseline. Review recent "
        "setpoint / weather / DHW changes.{advice}"
    ),
    "setpoint_osc": (
        "**LWT setpoint oscillating**\n"
        "Changed **{osc_count}\u00D7** in the last **{window_min} min** "
        "(threshold {threshold}).\n"
        "\U0001F4A1 Lock the LWT setpoint, or increase thermostat hysteresis "
        "so the heat pump can settle.{advice}"
    ),
}

ALERT_TEMPLATES_NL: dict[str, str] = {
    "pendulum_hourly": (
        "**Pendelen gedetecteerd (per uur)**\n"
        "**{cph} cycli** in het laatste uur (doel \u2264 {target_cph}).\n"
        "\U0001F4A1 Verhoog de thermostaat-hysterese, of verlaag de stooklijn "
        "zodat cycli langer duren.{advice}"
    ),
    "pendulum_daily": (
        "**Pendelen gedetecteerd (dagelijks)**\n"
        "**{cycles_today} cycli** vandaag (doel \u2264 {target_cpd}).\n"
        "\U0001F4A1 Controleer setpoint-delta, hysterese en stooklijn \u2014 "
        "de pomp pendelt te vaak.{advice}"
    ),
    "short_run": (
        "**Korte run gedetecteerd**\n"
        "Laatste cyclus duurde **{duration_min} min** (drempel {threshold_min} min).\n"
        "\U0001F4A1 Verhoog de minimum looptijd of demp de warmtevraag.{advice}"
    ),
    "short_off": (
        "**Korte off-tijd gedetecteerd**\n"
        "Off-tijd was slechts **{off_min} min** (drempel {threshold_min} min).\n"
        "\U0001F4A1 De pomp herstart te snel \u2014 controleer stooklijn "
        "en hysterese.{advice}"
    ),
    "ml_anomaly": (
        "**ML-anomalie ({mode})**\n"
        "z-score **{z_max}** op **\"{top_dim}\"**.\n"
        "\U0001F4A1 Gedrag wijkt af van de geleerde baseline. Controleer "
        "recente setpoint / weer / SWW-wijzigingen.{advice}"
    ),
    "setpoint_osc": (
        "**LWT-setpoint oscilleert**\n"
        "Wijzigde **{osc_count}\u00D7** in de laatste **{window_min} min** "
        "(drempel {threshold}).\n"
        "\U0001F4A1 Vergrendel het LWT-setpoint, of verhoog de "
        "thermostaat-hysterese.{advice}"
    ),
}

ALERT_TEMPLATES: dict[str, dict[str, str]] = {
    "en": ALERT_TEMPLATES_EN,
    "nl": ALERT_TEMPLATES_NL,
}

BINARY_ALERT_MAP: dict[str, tuple[str, str, str]] = {
    "pendulum_hourly": (
        "pendulum_hourly",
        SEV_WARNING,
        "Pendulum hourly\n{cph} cycles/h (target \u2264 {target_cph}){advice}",
    ),
    "pendulum_daily": (
        "pendulum_daily",
        SEV_WARNING,
        "Pendulum daily\n{cycles_today} cycles today (target \u2264 {target_cpd}){advice}",
    ),
    "short_run": (
        "short_run",
        SEV_WARNING,
        "Short run detected\n{duration_min} min (threshold {threshold_min} min){advice}",
    ),
    "short_off": (
        "short_off",
        SEV_WARNING,
        "Short off detected\n{off_min} min (threshold {threshold_min} min){advice}",
    ),
    "ml_anomaly": (
        "ml_anomaly",
        SEV_WARNING,
        "ML anomaly ({mode})\nz={z_max} \u00b7 top: {top_dim}{advice}",
    ),
    "setpoint_osc": (
        "setpoint_osc",
        SEV_WARNING,
        "Setpoint oscillation\n{osc_count} changes in {window_min} min{advice}",
    ),
    "cop_degradation": (
        "cop_degradation",
        SEV_WARNING,
        "COP degradation\n{week_pct}% vs last week (threshold \u2264 {threshold_pct}%){advice}",
    ),
    "defrost_excessive": (
        "defrost_excessive",
        SEV_WARNING,
        "Defrost excessive\n{count_7d} defrosts in 7d (threshold \u2264 {threshold}){advice}",
    ),
    "buh_excessive": (
        "buh_excessive",
        SEV_WARNING,
        "Backup heater excessive\nBUH ratio {buh_ratio_7d} over 7d (threshold \u2264 {threshold_ratio}){advice}",
    ),
    "source_stale": (
        "source_stale",
        SEV_CRITICAL,
        "Source sensor stale\nNo update for {age_s} s (threshold {threshold_s} s){advice}",
    ),
    "missing_attributes": (
        "missing_attributes",
        SEV_WARNING,
        "Missing attributes\n{missing_count} required attributes absent{advice}",
    ),
    "dhw_pendulum": (
        "dhw_pendulum",
        SEV_WARNING,
        "DHW pendulum\n{dhw_cph} DHW cycles/h (target \u2264 {target_cph}){advice}",
    ),
    "high_cycle_rate": (
        "high_cycle_rate",
        SEV_WARNING,
        "High cycle rate\n{cph} cycles/h (\u2264 {target_cph} \u00d7 {multiplier}){advice}",
    ),
    "cop_vs_datasheet_low": (
        "cop_vs_datasheet_low",
        SEV_INFO,
        "COP below datasheet\n{pct_diff}% vs expected {cop_expected}{advice}",
    ),
}

NOTIF_ID_BY_TYPE = {
    "pendulum_hourly": NOTIF_ID_PENDULUM_HOURLY,
    "pendulum_daily": NOTIF_ID_PENDULUM_DAILY,
    "short_run": NOTIF_ID_SHORT_RUN,
    "short_off": NOTIF_ID_SHORT_OFF,
    "ml_anomaly": NOTIF_ID_ML_ANOMALY,
    "setpoint_osc": NOTIF_ID_SETPOINT_OSC,
    "cop_degradation": NOTIF_ID_COP_DEGRADATION,
    "defrost_excessive": NOTIF_ID_DEFROST_EXCESSIVE,
    "buh_excessive": NOTIF_ID_BUH_EXCESSIVE,
    "source_stale": NOTIF_ID_SOURCE_STALE,
    "missing_attributes": NOTIF_ID_MISSING_ATTRIBUTES,
    "dhw_pendulum": NOTIF_ID_DHW_PENDULUM,
    "high_cycle_rate": NOTIF_ID_HIGH_CYCLE_RATE,
    "cop_vs_datasheet_low": NOTIF_ID_COP_VS_DATASHEET_LOW,
}


class _SafeDict(dict[str, Any]):
    """Leave {unknown_key} intact instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _format_message(
    template: str, context: Mapping[str, Any] | None
) -> str:
    """Fill template placeholders from context; leave template if empty."""
    if not context:
        return template
    try:
        return template.format_map(_SafeDict(context))
    except Exception:
        return template


def _prefix_emoji(
    message: str,
    alert_type: str,
    severity: str,
    emoji_enabled: bool,
) -> str:
    if not emoji_enabled:
        return message
    emoji = ALERT_TYPE_EMOJI.get(alert_type) or SEVERITY_EMOJI.get(severity, "")
    if not emoji:
        return message
    return f"{emoji} {message}"


def _parse_hhmm(value: str | None, fallback: str) -> tuple[int, int]:
    src = (value or fallback).strip()
    try:
        hh, mm = src.split(":", 1)
        return int(hh) % 24, int(mm) % 60
    except (ValueError, AttributeError):
        fh, fm = fallback.split(":", 1)
        return int(fh), int(fm)


def _in_quiet_hours(
    now: float, start: tuple[int, int], end: tuple[int, int]
) -> bool:
    import time as _t
    tm = _t.localtime(now)
    cur = tm.tm_hour * 60 + tm.tm_min
    s = start[0] * 60 + start[1]
    e = end[0] * 60 + end[1]
    if s == e:
        return False
    if s < e:
        return s <= cur < e
    return cur >= s or cur < e


def _opt_float(
    options: Mapping[str, Any] | None, key: str, default: float
) -> float:
    if not options:
        return default
    try:
        return float(options.get(key, default))
    except (TypeError, ValueError):
        return default


def passes_filters(
    alert_type: str,
    severity: str,
    options: Mapping[str, Any] | None,
    now: float,
) -> bool:
    """Shared alert gate: group gating + quiet hours.

    Extracted from evaluate_alerts so standalone emitters
    (cop_low, stooklijn_advies) apply the same filtering rules.
    Critical severity bypasses quiet hours; group gating applies to all.
    """
    options = options or {}
    group = ALERT_GROUP_MAP.get(alert_type)
    if group and options.get(f"alert_group_{group}", True) is False:
        _LOGGER.debug("group disabled: %s (%s)", alert_type, group)
        return False
    if severity != SEV_CRITICAL and bool(options.get("quiet_hours_enabled", False)):
        start = _parse_hhmm(options.get("quiet_hours_start"), DEFAULT_QUIET_START)
        end = _parse_hhmm(options.get("quiet_hours_end"), DEFAULT_QUIET_END)
        if _in_quiet_hours(now, start, end):
            _LOGGER.debug("quiet hours: suppressing %s", alert_type)
            return False
    return True


def evaluate_alerts(
    binary_states: Mapping[str, bool],
    options: Mapping[str, Any] | None,
    now: float,
    last_sent: Mapping[str, float] | None = None,
    *,
    context: Mapping[str, Mapping[str, Any]] | None = None,
    emoji_enabled: bool | None = None,
    language: str | None = None,
) -> list[AlertSpec]:
    """Return alerts to dispatch now.

    Rules:
      - Only alerts whose triggering binary is True.
      - Same alert_type suppressed within alert_aggregation_minutes.
      - In quiet hours, non-critical alerts are dropped.
      - Per-alert_type context dict fills message templates.
      - Emoji prefix per severity/alert_type unless disabled.
    """
    options = options or {}
    last_sent = last_sent or {}
    context = context or {}
    if emoji_enabled is None:
        emoji_enabled = bool(options.get("notify_emoji_enabled", True))

    _lang = language or (options.get("notification_language") if options else None) or "en"
    if _lang not in ALERT_TEMPLATES:
        _lang = "en"
    _lang_templates = ALERT_TEMPLATES[_lang]

    agg_min = _opt_float(options, "alert_aggregation_minutes", DEFAULT_AGG_MIN)
    persistent_enabled = bool(options.get("persistent_enabled", True))

    emitted: dict[str, AlertSpec] = {}
    for bkey, spec in BINARY_ALERT_MAP.items():
        if not binary_states.get(bkey, False):
            continue
        alert_type, severity, default_tmpl = spec
        tmpl = _lang_templates.get(bkey, default_tmpl)
        # Defensive: guards future alert_type collisions. PR B made all
        # BINARY_ALERT_MAP alert_types unique, so this is currently dead.
        if alert_type in emitted:  # pragma: no cover
            continue
        if not passes_filters(alert_type, severity, options, now):
            continue
        _per_key = f"{ALERT_DEDUP_OPTION_PREFIX}{alert_type}{ALERT_DEDUP_OPTION_SUFFIX}"
        _per_min = _opt_float(options, _per_key, agg_min)
        prev = last_sent.get(alert_type)
        if isinstance(prev, (int, float)) and (now - float(prev)) < _per_min * 60.0:
            _LOGGER.debug(
                "aggregation window (%s, %s min): suppressing %s",
                _per_key, _per_min, alert_type,
            )
            continue
        notif_id = NOTIF_ID_BY_TYPE.get(alert_type, f"daikin_cycle_ml_{alert_type}")
        ctx = context.get(alert_type) if context else None
        if bkey in ALERT_SCHEMA:  # pragma: no branch
            msg = build_rich_alert(
                bkey, severity, ctx or {},
                language=_lang, emoji_enabled=emoji_enabled,
            )
        else:  # pragma: no cover
            msg = _format_message(tmpl, ctx)
            msg = _prefix_emoji(msg, alert_type, severity, emoji_enabled)
        emitted[alert_type] = AlertSpec(
            alert_type=alert_type,
            severity=severity,
            message=msg,
            notif_id=notif_id,
            dedupe_key=alert_type,
            persistent=persistent_enabled,
        )

    return list(emitted.values())


def build_status_message(
    snapshot: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
    emoji_enabled: bool = True,
    language: str | None = None,
) -> str:
    """Rich sectioned status report (Batch 37)."""
    lang = language or (context.get('language') if context else None) or 'en'
    return build_status_report(
        snapshot, language=lang, emoji_enabled=bool(emoji_enabled)
    )


def build_stooklijn_message(
    cache: Mapping[str, Any],
    language: str | None = None,
    emoji_enabled: bool = True,
) -> str:
    """Bilingual stooklijn report (Batch 37)."""
    return build_stooklijn_report(
        cache, language=(language or 'en'), emoji_enabled=bool(emoji_enabled)
    )


def build_cop_low_message(
    cop: float,
    samples: int,
    language: str | None = None,
    emoji_enabled: bool = True,
) -> str:
    """Bilingual low-COP report (Batch 37)."""
    return build_cop_low_report(
        cop, samples, language=(language or 'en'), emoji_enabled=bool(emoji_enabled)
    )

async def async_send_notification(
    hass: Any, target: str, message: str
) -> bool:
    """Send to a notify target. Entity first, legacy fallback."""
    if not isinstance(target, str) or "." not in target:
        return False
    _domain, _name = target.split(".", 1)
    if not _name:
        return False
    try:
        _state = hass.states.get(target)
    except Exception:
        _state = None
    if _state is not None:
        try:
            await hass.services.async_call(
                "notify", "send_message",
                {"message": message},
                target={"entity_id": target},
                blocking=False,
            )
            return True
        except Exception:
            return False
    try:
        _svcs = hass.services.async_services()
        if isinstance(_svcs, dict):
            _notify_svcs = _svcs.get("notify") or {}
            if _name in _notify_svcs:
                await hass.services.async_call(
                    "notify", _name, {"message": message},
                    blocking=False,
                )
                return True
    except Exception:
        _LOGGER.debug("notify entity path failed", exc_info=True)
    if _domain != "notify":
        try:
            await hass.services.async_call(
                _domain, _name, {"message": message},
                blocking=False,
            )
            return True
        except Exception:
            return False
    return False
