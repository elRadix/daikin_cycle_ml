"""Notification engine v2 (12c): dynamic messages + emoji + status builder."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from ..const import (
    ALERT_TYPE_EMOJI,
    NOTIF_ID_ML_ANOMALY,
    NOTIF_ID_PENDULUM,
    NOTIF_ID_SETPOINT_OSC,
    NOTIF_ID_SHORT_OFF,
    NOTIF_ID_SHORT_RUN,
    SEVERITY_EMOJI,
    ALERT_GROUP_MAP,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_QUIET_START = "22:00"
DEFAULT_QUIET_END = "07:00"
DEFAULT_AGG_MIN = 30

SEV_WARNING = "warning"
SEV_CRITICAL = "critical"


@dataclass(frozen=True)
class AlertSpec:
    """A single alert to be emitted."""

    alert_type: str
    severity: str
    message: str
    notif_id: str
    dedupe_key: str
    persistent: bool = True


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
        "pendulum",
        SEV_WARNING,
        "Pendulum hourly\n{cph} cycles/h (target \u2264 {target_cph}){advice}",
    ),
    "pendulum_daily": (
        "pendulum",
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
}

NOTIF_ID_BY_TYPE = {
    "pendulum": NOTIF_ID_PENDULUM,
    "short_run": NOTIF_ID_SHORT_RUN,
    "short_off": NOTIF_ID_SHORT_OFF,
    "ml_anomaly": NOTIF_ID_ML_ANOMALY,
    "setpoint_osc": NOTIF_ID_SETPOINT_OSC,
}


class _SafeDict(dict):
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
    except Exception:  # noqa: BLE001
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

    quiet_enabled = bool(options.get("quiet_hours_enabled", False))
    agg_min = _opt_float(options, "alert_aggregation_minutes", DEFAULT_AGG_MIN)
    persistent_enabled = bool(options.get("persistent_enabled", True))

    if quiet_enabled:
        start = _parse_hhmm(options.get("quiet_hours_start"), DEFAULT_QUIET_START)
        end = _parse_hhmm(options.get("quiet_hours_end"), DEFAULT_QUIET_END)
        quiet = _in_quiet_hours(now, start, end)
    else:
        quiet = False

    emitted: dict[str, AlertSpec] = {}
    for bkey, spec in BINARY_ALERT_MAP.items():
        if not binary_states.get(bkey, False):
            continue
        alert_type, severity, default_tmpl = spec
        tmpl = _lang_templates.get(bkey, default_tmpl)
        if alert_type in emitted:
            continue
        _grp = ALERT_GROUP_MAP.get(alert_type)
        if _grp and options.get(f"alert_group_{_grp}", True) is False:
            _LOGGER.debug("group disabled: %s (%s)", alert_type, _grp)
            continue
            continue
        if severity != SEV_CRITICAL and quiet:
            _LOGGER.debug("quiet hours: suppressing %s", alert_type)
            continue
        prev = last_sent.get(alert_type)
        if isinstance(prev, (int, float)) and (now - float(prev)) < agg_min * 60.0:
            _LOGGER.debug("aggregation window: suppressing %s", alert_type)
            continue
        notif_id = NOTIF_ID_BY_TYPE.get(alert_type, f"daikin_cycle_ml_{alert_type}")
        ctx = context.get(alert_type) if context else None
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
) -> str:
    """Build a periodic status summary with optional emoji prefix."""
    ctx = dict(context or {})
    prefix = (SEVERITY_EMOJI['status'] + ' ') if emoji_enabled else ''
    title = str(ctx.get('title', 'Daikin Cycle ML status'))
    lines = [prefix + title]

    mode = snapshot.get('mode') or 'unknown'
    state = snapshot.get('state') or 'idle'
    lines.append(f'Mode: {mode} ({state})')

    cyc = snapshot.get('cycles_today')
    tgt = snapshot.get('target_cpd')
    if cyc is not None and tgt is not None:
        lines.append(f'Cycles today: {cyc} / target {tgt}')
    elif cyc is not None:
        lines.append(f'Cycles today: {cyc}')

    q = snapshot.get('quality_last')
    ago = snapshot.get('last_cycle_ago_min')
    if ago is not None and q is not None:
        lines.append(f'Last cycle: {ago} min ago (quality {q})')
    elif ago is not None:
        lines.append(f'Last cycle: {ago} min ago')

    sev = snapshot.get('anomaly_severity')
    if sev:
        s_emoji = SEVERITY_EMOJI.get(sev, '') if emoji_enabled else ''
        lead = (s_emoji + ' ') if s_emoji else ''
        lines.append(f'{lead}Anomaly: {sev}')

    samples = snapshot.get('baseline_samples')
    modes = snapshot.get('baseline_modes')
    if samples is not None:
        modes_str = (' (' + ', '.join(modes) + ')') if modes else ''
        lines.append(f'Baseline: {samples} samples{modes_str}')

    advice = snapshot.get('top_advice')
    if advice:
        lines.append(f'Advice: {advice}')

    return chr(10).join(lines)


NOTIFY_DOMAIN = "notify"
NOTIFY_SEND_MESSAGE = "send_message"


async def async_send_notification(
    hass: Any, target: str, message: str
) -> bool:
    """Route a message to a notify entity or legacy notify service.

    Returns True on successful dispatch, False otherwise.
    """
    if not isinstance(target, str):
        return False
    tgt = target.strip()
    if not tgt or "." not in tgt:
        return False
    if hass.states.get(tgt) is not None:
        try:
            await hass.services.async_call(
                NOTIFY_DOMAIN,
                NOTIFY_SEND_MESSAGE,
                {"message": message},
                target={"entity_id": tgt},
                blocking=False,
            )
            return True
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "notify.send_message failed for %s", tgt
            )
            return False
    domain, _, service = tgt.partition(".")
    if not domain or not service:
        return False
    services = hass.services.async_services().get(domain, {})
    if service not in services:
        _LOGGER.warning("notify target not registered: %s", tgt)
        return False
    try:
        await hass.services.async_call(
            domain, service, {"message": message}, blocking=False
        )
        return True
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Legacy notify %s failed", tgt)
        return False


STOOKLIJN_STATE_LABEL = {
    "verlaag_lwt_2c": "Lower LWT by 2C",
    "verhoog_lwt_2c": "Raise LWT by 2C",
    "behoud": "Keep current LWT",
    "unknown": "Insufficient data",
}


def build_stooklijn_message(cache: Mapping[str, Any]) -> str:
    """Uniform stooklijn advice message."""
    if not isinstance(cache, Mapping):
        return "\U0001F4C9 Stooklijn advies\nNo data"
    state = str(cache.get("state") or "unknown")
    label = STOOKLIJN_STATE_LABEL.get(state, state)
    try:
        besparing = float(cache.get("besparing_cop_pct") or 0.0)
    except (TypeError, ValueError):
        besparing = 0.0
    try:
        comfort = float(cache.get("comfort_impact") or 0.0)
    except (TypeError, ValueError):
        comfort = 0.0
    try:
        betrouw = float(cache.get("betrouwbaarheid") or 0.0)
    except (TypeError, ValueError):
        betrouw = 0.0
    try:
        samples = int(cache.get("samples") or 0)
    except (TypeError, ValueError):
        samples = 0
    lines = [
        "\U0001F4C9 Stooklijn advies",
        label,
        "+%.0f%% COP \u00b7 comfort %+.1fC \u00b7 %d%% confidence \u00b7 %d samples"
        % (besparing, comfort, int(betrouw * 100.0), samples),
    ]
    return "\n".join(lines)


def build_cop_low_message(cop: float, samples: int) -> str:
    """Uniform low-COP message."""
    return (
        "\U0001F4C9 Day COP low\n"
        "%.2f (threshold 2.5) \u00b7 %d samples" % (float(cop), int(samples))
    )

