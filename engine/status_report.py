"""Rich sectioned status report (Batch 37)."""
from __future__ import annotations

import datetime as _dt
from typing import Any, Mapping
try:
    from ..const import (
        STOOKLIJN_STATE_LABEL_EN,
        STOOKLIJN_STATE_LABEL_NL,
    )
except Exception:  # pragma: no cover
    STOOKLIJN_STATE_LABEL_EN = {}
    STOOKLIJN_STATE_LABEL_NL = {}

DIV = "\u2501" * 22

GREETINGS = {
    "en": {
        "morning":   ("\U0001F305", "MORNING REPORT",   "\u2615 Good morning \u2014 have a great day!"),
        "afternoon": ("\u2600\uFE0F", "AFTERNOON REPORT", "\u2615 Good afternoon \u2014 keep going!"),
        "evening":   ("\U0001F307", "EVENING REPORT",   "\U0001F319 Good evening \u2014 sleep well!"),
        "night":     ("\U0001F319", "NIGHT REPORT",     "\U0001F634 Quiet night \u2014 all good."),
    },
    "nl": {
        "morning":   ("\U0001F305", "OCHTENDRAPPORT",   "\u2615 Goedemorgen \u2014 fijne dag!"),
        "afternoon": ("\u2600\uFE0F", "MIDDAGRAPPORT",    "\u2615 Goedemiddag \u2014 zet 'm op!"),
        "evening":   ("\U0001F307", "AVONDRAPPORT",     "\U0001F319 Goedenavond \u2014 slaap lekker!"),
        "night":     ("\U0001F319", "NACHTRAPPORT",     "\U0001F634 Rustige nacht \u2014 alles ok."),
    },
}

LABELS = {
    "en": {
        "status": "Status", "mode": "Mode", "last": "Last cycle",
        "quality": "Quality", "lwt": "LWT", "indoor": "Indoor",
        "outdoor": "Outdoor", "flow": "Flow", "thermal": "Thermal",
        "cycles_today": "Cycles today", "short": "Short runs",
        "good": "Good runs", "per_hour": "Per hour",
        "baseline": "Baseline", "anomaly": "Anomaly", "cop_today": "COP today",
        "stats": "Statistics", "total": "Total", "today": "Today",
        "d7": "7d", "d30": "30d", "avg_dur": "Avg duration",
    },
    "nl": {
        "status": "Status", "mode": "Modus", "last": "Laatste",
        "quality": "Kwaliteit", "lwt": "LWT", "indoor": "Binnen",
        "outdoor": "Buiten", "flow": "Flow", "thermal": "Thermal",
        "cycles_today": "Cycli vandaag", "short": "Kort",
        "good": "Goed", "per_hour": "Per uur",
        "baseline": "Baseline", "anomaly": "Anomalie", "cop_today": "COP vandaag",
        "stats": "Statistieken", "total": "Totaal", "today": "Vandaag",
        "d7": "7d", "d30": "30d", "avg_dur": "Gem. duur",
    },
}

MODE_LABELS = {
    "en": {"heating": "heating", "cooling": "cooling", "dhw": "DHW", "unknown": "unknown"},
    "nl": {"heating": "verwarmen", "cooling": "koelen", "dhw": "SWW", "unknown": "onbekend"},
}

SEVERITY_EMOJI = {
    "normal": "\u2705", "watch": "\U0001F7E1", "warn": "\U0001F7E0",
    "warning": "\U0001F7E0", "critical": "\U0001F534",
    "ok": "\u2705", "info": "\U0001F535",
}


def hour_bucket(hour: int) -> str:
    """Map hour 0-23 to a greeting bucket."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def _row(emoji, label, value, width=15, emojis=True):
    pre = (emoji + " ") if (emoji and emojis) else ""
    pad = " " * max(1, width - len(label))
    return pre + label + pad + str(value)


def _fmt_float(v, digits=1, suffix=""):
    if v is None:
        return "\u2014"
    try:
        return ("%." + str(digits) + "f") % float(v) + suffix
    except (TypeError, ValueError):
        return "\u2014"


def _fmt_int(v):
    if v is None:
        return "\u2014"
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return "\u2014"


def build_status_report(snapshot, *, language="en", emoji_enabled=True):
    """Assemble the rich multi-section status report."""
    if language not in LABELS:
        language = "en"
    L = LABELS[language]
    ML = MODE_LABELS.get(language, MODE_LABELS["en"])
    now = _dt.datetime.now()
    bucket = hour_bucket(now.hour)
    head_e, header_text, signoff = GREETINGS[language][bucket]
    ts = now.strftime("%Y-%m-%d %H:%M")

    lines = []
    if emoji_enabled:
        lines.append(head_e + " Daikin Cycle ML \u2014 " + header_text)
        lines.append("\U0001F550 " + ts)
    else:
        lines.append("Daikin Cycle ML \u2014 " + header_text)
        lines.append(ts)
    lines.append(DIV)

    state = snapshot.get("state") or "idle"
    mode = snapshot.get("mode") or "unknown"
    mode_str = ML.get(mode, mode)
    lines.append(_row("\U0001F4A4" if state == "idle" else "\U0001F504",
                      L["status"], state, emojis=emoji_enabled))
    lines.append(_row("\U0001F501", L["mode"], mode_str, emojis=emoji_enabled))
    ago = snapshot.get("last_cycle_ago_min")
    v = ("%d min" % int(ago)) if ago is not None else "\u2014"
    lines.append(_row("\u23F1\uFE0F", L["last"], v, emojis=emoji_enabled))
    q = snapshot.get("quality_last")
    v = ("%d / 100" % int(q)) if q is not None else "\u2014"
    lines.append(_row("\U0001F4CA", L["quality"], v, emojis=emoji_enabled))
    lines.append(DIV)

    lwt = snapshot.get("lwt")
    indoor = snapshot.get("indoor")
    outdoor = snapshot.get("outdoor")
    flow = snapshot.get("flow_lmin")
    thermal = snapshot.get("thermal_kw")
    if any(v is not None for v in (lwt, indoor, outdoor, flow, thermal)):
        lines.append(_row("\U0001F321\uFE0F", L["lwt"], _fmt_float(lwt, 1, " \u00b0C"), emojis=emoji_enabled))
        lines.append(_row("\U0001F321\uFE0F", L["indoor"], _fmt_float(indoor, 1, " \u00b0C"), emojis=emoji_enabled))
        lines.append(_row("\U0001F321\uFE0F", L["outdoor"], _fmt_float(outdoor, 1, " \u00b0C"), emojis=emoji_enabled))
        lines.append(_row("\U0001F4A7", L["flow"], _fmt_float(flow, 1, " l/min"), emojis=emoji_enabled))
        lines.append(_row("\U0001F525", L["thermal"], _fmt_float(thermal, 2, " kW"), emojis=emoji_enabled))
        lines.append(DIV)

    cyc_today = snapshot.get("cycles_today")
    tgt = snapshot.get("target_cpd")
    if cyc_today is not None:
        v = ("%d / %d" % (int(cyc_today), int(tgt))) if tgt else str(int(cyc_today))
    else:
        v = "\u2014"
    lines.append(_row("\U0001F4C8", L["cycles_today"], v, emojis=emoji_enabled))
    sr = snapshot.get("short_runs_today")
    if sr is not None:
        lines.append(_row("\U0001F4C9", L["short"], _fmt_int(sr), emojis=emoji_enabled))
    gc = snapshot.get("good_cycles_today")
    if gc is not None:
        lines.append(_row("\u2705", L["good"], _fmt_int(gc), emojis=emoji_enabled))
    cph = snapshot.get("cycles_per_hour")
    tgt_cph = snapshot.get("target_cph")
    if cph is not None:
        v = ("%d / \u2264%d" % (int(cph), int(tgt_cph))) if tgt_cph else str(int(cph))
        lines.append(_row("\U0001F501", L["per_hour"], v, emojis=emoji_enabled))
    lines.append(DIV)

    samples = snapshot.get("baseline_samples")
    modes = snapshot.get("baseline_modes") or []
    if samples is not None:
        modes_str = (" \u00b7 " + ", ".join(modes)) if modes else ""
        lines.append(_row("\U0001F393", L["baseline"],
                          "%d samples%s" % (int(samples), modes_str),
                          emojis=emoji_enabled))
    sev = snapshot.get("anomaly_severity") or "normal"
    sev_e = SEVERITY_EMOJI.get(sev, "") if emoji_enabled else ""
    lines.append(_row("\U0001F9E0", L["anomaly"],
                      (sev_e + " " + sev).strip() if sev_e else sev,
                      emojis=emoji_enabled))
    cop = snapshot.get("cop_today")
    cop_n = snapshot.get("cop_today_samples")
    if cop is not None:
        v = ("%.2f (%d samples)" % (float(cop), int(cop_n))) if cop_n else ("%.2f" % float(cop))
        lines.append(_row("\U0001F4C9", L["cop_today"], v, emojis=emoji_enabled))
    lines.append(DIV)

    stats_total = snapshot.get("db_total")
    stats_d7 = snapshot.get("db_7d")
    stats_d30 = snapshot.get("db_30d")
    stats_avg = snapshot.get("db_avg_duration_min")
    if any(v is not None for v in (stats_total, stats_d7, stats_d30, stats_avg)):
        lines.append("\U0001F4CA " + L["stats"])
        lines.append("   " + L["total"] + ": " + _fmt_int(stats_total)
                     + "  \u00b7  " + L["today"] + ": " + _fmt_int(cyc_today))
        lines.append("   " + L["d7"] + ": " + _fmt_int(stats_d7)
                     + "  \u00b7  " + L["d30"] + ": " + _fmt_int(stats_d30))
        if stats_avg is not None:
            lines.append("   " + L["avg_dur"] + ": "
                         + _fmt_float(stats_avg, 1, " min"))
        lines.append(DIV)

    lines.append(signoff)
    return "\n".join(lines)


def build_stooklijn_report(cache, *, language="en", emoji_enabled=True):
    """Bilingual stooklijn advice report."""
    if not isinstance(cache, Mapping):
        cache = {}
    is_nl = (language == "nl")
    title = "\U0001F4C9 Stooklijn advies" if is_nl else "\U0001F4C9 Stooklijn advice"
    state_raw = str(cache.get("state") or "unknown")
    _labels = (STOOKLIJN_STATE_LABEL_NL if is_nl
               else STOOKLIJN_STATE_LABEL_EN)
    state = _labels.get(state_raw, state_raw)
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
    lines = [title, DIV]
    lbl_state = "Status"
    lbl_besp = "COP-winst" if is_nl else "COP gain"
    lbl_cmf = "Comfort"
    lbl_conf = "Vertrouwen" if is_nl else "Confidence"
    lbl_smp = "Samples"
    lines.append(_row("\U0001F3AF", lbl_state, state, emojis=emoji_enabled))
    lines.append(_row("\U0001F4C8", lbl_besp, ("+%.0f%%" % besparing), emojis=emoji_enabled))
    lines.append(_row("\U0001F321\uFE0F", lbl_cmf, ("%+.1fC" % comfort), emojis=emoji_enabled))
    lines.append(_row("\U0001F3AF", lbl_conf, ("%d%%" % int(betrouw * 100)), emojis=emoji_enabled))
    lines.append(_row("\U0001F4E6", lbl_smp, str(samples), emojis=emoji_enabled))
    lines.append(DIV)
    return "\n".join(lines)


def build_cop_low_report(cop, samples, *, language="en", emoji_enabled=True):
    """Bilingual low-COP report."""
    is_nl = (language == "nl")
    title = "\U0001F4C9 Dag-COP laag" if is_nl else "\U0001F4C9 Day COP low"
    lbl_cop = "COP"
    lbl_th = "Drempel" if is_nl else "Threshold"
    lbl_smp = "Samples"
    lines = [title, DIV]
    lines.append(_row("\U0001F4C9", lbl_cop, ("%.2f" % float(cop)), emojis=emoji_enabled))
    lines.append(_row("\U0001F3AF", lbl_th, "2.50", emojis=emoji_enabled))
    lines.append(_row("\U0001F4E6", lbl_smp, str(int(samples)), emojis=emoji_enabled))
    lines.append(DIV)
    return "\n".join(lines)


ALERT_TITLES = {
    "en": {
        "pendulum_hourly": "Pendulum detected (hourly)",
        "pendulum_daily":  "Pendulum detected (daily)",
        "short_run":      "Short run detected",
        "short_off":      "Short off-time detected",
        "ml_anomaly":     "ML anomaly detected",
        "setpoint_osc":   "LWT-setpoint oscillating",
        "cop_low":        "Day COP low",
        "stooklijn_advies": "Stooklijn advice",
    },
    "nl": {
        "pendulum_hourly": "Pendelen gedetecteerd (per uur)",
        "pendulum_daily":  "Pendelen gedetecteerd (dagelijks)",
        "short_run":      "Korte run gedetecteerd",
        "short_off":      "Korte off-tijd gedetecteerd",
        "ml_anomaly":     "ML-anomalie gedetecteerd",
        "setpoint_osc":   "LWT-setpoint oscilleert",
        "cop_low":        "Dag-COP laag",
        "stooklijn_advies": "Stooklijn advies",
    },
}

ALERT_LABELS = {
    "en": {
        "cycles_hour":   "Cycles / hour",
        "target_hour":   "Target",
        "cycles_today":  "Cycles today",
        "target_day":    "Target",
        "duration":      "Duration",
        "threshold":     "Threshold",
        "off_time":      "Off-time",
        "mode":          "Mode",
        "zscore":        "Z-score",
        "top_dim":       "Top dim",
        "changes":       "Changes",
        "window":        "Window",
    },
    "nl": {
        "cycles_hour":   "Cycli / uur",
        "target_hour":   "Doel",
        "cycles_today":  "Cycli vandaag",
        "target_day":    "Doel",
        "duration":      "Duur",
        "threshold":     "Drempel",
        "off_time":      "Off-tijd",
        "mode":          "Modus",
        "zscore":        "Z-score",
        "top_dim":       "Top-dimensie",
        "changes":       "Wijzigingen",
        "window":        "Venster",
    },
}

ALERT_EMOJI = {
    "pendulum_hourly": "\U0001F501",
    "pendulum_daily":  "\U0001F501",
    "short_run":      "\u23F1\uFE0F",
    "short_off":      "\U0001F4A4",
    "ml_anomaly":     "\U0001F9E0",
    "setpoint_osc":   "\U0001F3AF",
    "cop_low":        "\U0001F4C9",
    "stooklijn_advies": "\U0001F4C9",
}

ALERT_SCHEMA = {
    "pendulum_hourly": [
        ("\U0001F4C8", "cycles_hour", "{cph}"),
        ("\U0001F3AF", "target_hour", "\u2264 {target_cph}"),
    ],
    "pendulum_daily": [
        ("\U0001F4C8", "cycles_today", "{cycles_today}"),
        ("\U0001F3AF", "target_day", "\u2264 {target_cpd}"),
    ],
    "short_run": [
        ("\u23F1\uFE0F", "duration", "{duration_min} min"),
        ("\U0001F3AF", "threshold", "{threshold_min} min"),
    ],
    "short_off": [
        ("\u23F1\uFE0F", "off_time", "{off_min} min"),
        ("\U0001F3AF", "threshold", "{threshold_min} min"),
    ],
    "ml_anomaly": [
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F4C8", "zscore", "{z_max}"),
        ("\U0001F3AF", "top_dim", "{top_dim}"),
    ],
    "setpoint_osc": [
        ("\U0001F501", "changes", "{osc_count} \u00d7"),
        ("\u23F1\uFE0F", "window", "{window_min} min"),
        ("\U0001F3AF", "threshold", "{threshold} \u00d7"),
    ],
}


def build_rich_alert(alert_type, severity, context, *, language="en", emoji_enabled=True):
    """Build a sectioned rich-alert message for any alert type."""
    if language not in ALERT_LABELS:
        language = "en"
    labels = ALERT_LABELS[language]
    titles = ALERT_TITLES.get(language, ALERT_TITLES["en"])
    title = titles.get(alert_type, alert_type)
    type_e = ALERT_EMOJI.get(alert_type, "")
    sev_e = SEVERITY_EMOJI.get(severity, "")
    head_e = type_e or sev_e or "\U0001F514"
    now = _dt.datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M")
    ctx = dict(context or {})
    lines = []
    if emoji_enabled:
        lines.append(head_e + " Daikin Cycle ML \u2014 " + title)
        lines.append("\U0001F550 " + ts)
    else:
        lines.append("Daikin Cycle ML \u2014 " + title)
        lines.append(ts)
    lines.append(DIV)
    rows = ALERT_SCHEMA.get(alert_type) or []
    for emoji, label_key, tpl in rows:
        label = labels.get(label_key, label_key)
        try:
            val = tpl.format(**ctx)
        except (KeyError, IndexError, ValueError):
            val = "\u2014"
        lines.append(_row(emoji, label, val, emojis=emoji_enabled))
    advice = ctx.get("advice")
    if advice:
        lines.append(DIV)
        lines.append(str(advice).strip())
    lines.append(DIV)
    return "\n".join(lines)
