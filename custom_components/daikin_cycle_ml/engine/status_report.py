"""Rich sectioned status report (Batch 37)."""
from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Mapping
from typing import Any

from .alert_texts import HIDDEN_FACTS as _HIDDEN_FACTS
from .alert_texts import LEVEL_EMOJI as _LEVEL_EMOJI
from .alert_texts import LEVEL_INFO as _LEVEL_INFO
from .alert_texts import LEVEL_WATCH as _LEVEL_WATCH
from .alert_texts import MAX_FACTS as _MAX_FACTS
from .alert_texts import fact_rank as _fact_rank
from .alert_texts import TEXTS as _ALERT_TEXTS
from .alert_texts import fields as _alert_fields
from .alert_texts import fill as _alert_fill
from .alert_texts import message_parts as _alert_message_parts

try:
    from ..const import (
        ALERT_TYPE_EMOJI,
        COP_LOW_THRESHOLD,
        SEVERITY_EMOJI,
        STOOKLIJN_STATE_LABEL_EN,
        STOOKLIJN_STATE_LABEL_FR,
        STOOKLIJN_STATE_LABEL_NL,
    )
except Exception:  # pragma: no cover
    ALERT_TYPE_EMOJI = {}
    COP_LOW_THRESHOLD = 2.5
    SEVERITY_EMOJI = {}
    STOOKLIJN_STATE_LABEL_EN = {}
    STOOKLIJN_STATE_LABEL_NL = {}
    STOOKLIJN_STATE_LABEL_FR = {}

DIV = "\u2501" * 22
_SAMPLES_WORD = {"en": "samples", "nl": "samples", "fr": "\u00e9chantillons"}
_TPL_FIELD_RE = re.compile(r"\{(\w+)\}")


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



def hour_bucket(hour: int) -> str:
    """Map hour 0-23 to a greeting bucket."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def _row(emoji: str, label: str, value: Any, width: int = 15, emojis: bool = True) -> str:
    pre = (emoji + " ") if (emoji and emojis) else ""
    pad = " " * max(1, width - len(label))
    return pre + label + pad + str(value)


def _fmt_float(v: Any, digits: int = 1, suffix: str = "") -> str:
    if v is None:
        return "\u2014"
    try:
        return ("%." + str(digits) + "f") % float(v) + suffix
    except (TypeError, ValueError):
        return "\u2014"


def _fmt_int(v: Any) -> str:
    if v is None:
        return "\u2014"
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return "\u2014"


def _subtitle_line(ts: str, full_model: str, emoji_enabled: bool) -> str:
    """Second line: model (if set) + timestamp. Backward-compat: full_model empty."""
    if emoji_enabled:
        if full_model:
            return "\U0001F3E0 " + full_model + " \u00B7 \U0001F550 " + ts
        return "\U0001F550 " + ts
    if full_model:
        return full_model + " \u00B7 " + ts
    return ts


def build_status_report(snapshot: Mapping[str, Any], *, language: str = "en", emoji_enabled: bool = True, full_model: str = "") -> str:
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
        lines.append(_subtitle_line(ts, full_model, emoji_enabled))
    else:
        lines.append("Daikin Cycle ML \u2014 " + header_text)
        lines.append(_subtitle_line(ts, full_model, emoji_enabled))
    lines.append(DIV)

    state = snapshot.get("state") or "idle"
    mode = snapshot.get("mode") or "unknown"
    mode_str = ML.get(mode, mode)
    lines.append(_row("\U0001F4A4" if state == "idle" else "\U0001F504",
                      L["status"], state, emojis=emoji_enabled))
    lines.append(_row("\U0001F501", L["mode"], mode_str, emojis=emoji_enabled))
    ago = snapshot.get("last_cycle_ago_min")
    v = f"{int(ago)} min" if ago is not None else "\u2014"
    lines.append(_row("\u23F1\uFE0F", L["last"], v, emojis=emoji_enabled))
    q = snapshot.get("quality_last")
    v = f"{int(q)} / 100" if q is not None else "\u2014"
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
        v = f"{int(cyc_today)} / {int(tgt)}" if tgt else str(int(cyc_today))
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
        v = f"{int(cph)} / \u2264{int(tgt_cph)}" if tgt_cph else str(int(cph))
        lines.append(_row("\U0001F501", L["per_hour"], v, emojis=emoji_enabled))
    lines.append(DIV)

    samples = snapshot.get("baseline_samples")
    modes = snapshot.get("baseline_modes") or []
    if samples is not None:
        modes_str = (" \u00b7 " + ", ".join(modes)) if modes else ""
        lines.append(_row("\U0001F393", L["baseline"],
                          f"{int(samples)} {_SAMPLES_WORD.get(language, 'samples')}{modes_str}",
                          emojis=emoji_enabled))
    sev = snapshot.get("anomaly_severity") or "normal"
    sev_e = SEVERITY_EMOJI.get(sev, "") if emoji_enabled else ""
    lines.append(_row("\U0001F9E0", L["anomaly"],
                      (sev_e + " " + sev).strip() if sev_e else sev,
                      emojis=emoji_enabled))
    cop = snapshot.get("cop_today")
    cop_n = snapshot.get("cop_today_samples")
    if cop is not None:
        v = f"{float(cop):.2f} ({int(cop_n)} {_SAMPLES_WORD.get(language, 'samples')})" if cop_n else (f"{float(cop):.2f}")
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


def build_stooklijn_report(cache: Any, *, language: str = "en", emoji_enabled: bool = True, full_model: str = "") -> str:
    """Bilingual stooklijn advice report."""
    if not isinstance(cache, Mapping):
        cache = {}
    is_nl = language == "nl"
    is_fr = language == "fr"
    title = ("Stooklijn advies" if is_nl
             else "Conseil de loi d'eau" if is_fr else "Stooklijn advice")
    state_raw = str(cache.get("state") or "unknown")
    _labels = (STOOKLIJN_STATE_LABEL_NL if is_nl
               else STOOKLIJN_STATE_LABEL_FR if is_fr
               else STOOKLIJN_STATE_LABEL_EN)
    state = _labels.get(state_raw, state_raw)
    try:
        _step_fmt = int(cache.get("step_c") or 0)
    except (TypeError, ValueError):
        _step_fmt = 0
    try:
        state = state.format(step=_step_fmt)
    except (KeyError, IndexError, ValueError, AttributeError):
        pass
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
    now = _dt.datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M")
    if emoji_enabled:
        lines = ["\U0001F4C9 Daikin Cycle ML \u2014 " + title,
                 _subtitle_line(ts, full_model, emoji_enabled), DIV]
    else:
        lines = ["Daikin Cycle ML \u2014 " + title, _subtitle_line(ts, full_model, emoji_enabled), DIV]
    lbl_state = "\u00c9tat" if is_fr else "Status"
    lbl_besp = "COP-winst" if is_nl else "Gain de COP" if is_fr else "COP gain"
    lbl_cmf = "Confort" if is_fr else "Comfort"
    lbl_conf = "Vertrouwen" if is_nl else "Fiabilit\u00e9" if is_fr else "Confidence"
    lbl_smp = "\u00c9chantillons" if is_fr else "Samples"
    lines.append(_row("\U0001F3AF", lbl_state, state, emojis=emoji_enabled))
    lines.append(_row("\U0001F4C8", lbl_besp, (f"+{besparing:.0f}%"), emojis=emoji_enabled))
    lines.append(_row("\U0001F321\uFE0F", lbl_cmf, (f"{comfort:+.1f} \u00b0C"), emojis=emoji_enabled))
    lines.append(_row("\U0001F3AF", lbl_conf, f"{int(betrouw * 100)}%", emojis=emoji_enabled))
    lines.append(_row("\U0001F4E6", lbl_smp, str(samples), emojis=emoji_enabled))
    lines.append(DIV)
    return "\n".join(lines)


def build_cop_low_report(cop: Any, samples: Any, *, language: str = "en", emoji_enabled: bool = True, full_model: str = "") -> str:
    """Bilingual low-COP report."""
    is_nl = language == "nl"
    is_fr = language == "fr"
    title = "Dag-COP laag" if is_nl else "COP du jour bas" if is_fr else "Day COP low"
    lbl_cop = "COP"
    lbl_th = "Drempel" if is_nl else "Seuil" if is_fr else "Threshold"
    lbl_smp = "\u00c9chantillons" if is_fr else "Samples"
    now = _dt.datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M")
    if emoji_enabled:
        lines = ["\U0001F4C9 Daikin Cycle ML \u2014 " + title,
                 _subtitle_line(ts, full_model, emoji_enabled), DIV]
    else:
        lines = ["Daikin Cycle ML \u2014 " + title, _subtitle_line(ts, full_model, emoji_enabled), DIV]
    lines.append(_row("\U0001F4C9", lbl_cop, (f"{float(cop):.2f}"), emojis=emoji_enabled))
    lines.append(_row("\U0001F3AF", lbl_th, f"{COP_LOW_THRESHOLD:.2f}", emojis=emoji_enabled))
    lines.append(_row("\U0001F4E6", lbl_smp, str(int(samples)), emojis=emoji_enabled))
    lines.append(DIV)
    return "\n".join(lines)


ALERT_LABELS = {
    "en": {
        "cycles_hour": "Cycles / hour", "target_hour": "Target",
        "cycles_today": "Cycles today", "target_day": "Target",
        "duration": "Duration", "threshold": "Threshold",
        "off_time": "Off-time", "mode": "Mode",
        "zscore": "Z-score", "top_dim": "Top dim",
        "changes": "Changes", "window": "Window",
        "lwt_setpoint": "Water target", "lwt_target": "Water target (curve)",
        "lwt_actual": "Water now", "outdoor": "Outdoor",
        "last_duration": "Last run", "avg_duration_7d": "Average run (7 days)", "samples": "Samples", "delta_max": "Setpoint swing",
        "cop": "COP", "severity": "Severity",
        "indoor": "Indoor", "flow": "Flow",
        "week_pct": "Week", "threshold_pct": "Threshold",
        "trend_30d": "COP trend (30 days)",
        "count_7d": "Count 7d", "duration_7d_min": "Defrost time (7 days)",
        "buh_ratio_7d": "Backup heater share", "threshold_ratio": "Threshold",
        "stale_alerts": "Stale alerts", "stale_cycles": "Stale cycles",
        "alert_retention_days": "Alert retention",
        "cycle_retention_days": "Cycle retention",
        "hours_since_ok": "Hours since OK",
        "last_ok_ts": "Last OK",
        "consecutive_failures": "Consecutive fails",
        "last_failure_reason": "Last failure",
        "buh_count_7d": "BUH count 7d",
        "age_s": "Age", "threshold_s": "Threshold",
        "source_sensor": "Source",
        "missing_count": "Missing", "missing_list": "Which",
        "dhw_cph": "DHW cycles/h", "target_cph": "Target",
        "multiplier": "Multiplier", "pct_diff": "Diff",
        "cop_expected": "Expected",
        "today_el_kwh": "Today kWh",
        "baseline_el_mean": "Baseline mean",
        "baseline_el_sigma": "Baseline sigma",
        "z_score": "Z-score",
    },
    "nl": {
        "cycles_hour": "Cycli / uur", "target_hour": "Doel",
        "cycles_today": "Cycli vandaag", "target_day": "Doel",
        "duration": "Duur", "threshold": "Drempel",
        "off_time": "Off-tijd", "mode": "Modus",
        "zscore": "Z-score", "top_dim": "Top-dimensie",
        "changes": "Wijzigingen", "window": "Venster",
        "lwt_setpoint": "Watertemperatuur doel", "lwt_target": "Doel volgens stooklijn",
        "lwt_actual": "Watertemperatuur nu", "outdoor": "Buiten",
        "last_duration": "Laatste run", "avg_duration_7d": "Gemiddelde run (7 dagen)", "samples": "Monsters", "delta_max": "Setpoint-swing",
        "cop": "COP", "severity": "Ernst",
        "indoor": "Binnen", "flow": "Flow",
        "week_pct": "Week", "threshold_pct": "Drempel",
        "trend_30d": "COP-trend (30 dagen)",
        "count_7d": "Aantal 7d", "duration_7d_min": "Ontdooitijd (7 dagen)",
        "buh_ratio_7d": "Aandeel backup-heater", "threshold_ratio": "Drempel",
        "stale_alerts": "Verouderde meldingen",
        "stale_cycles": "Verouderde cycli",
        "alert_retention_days": "Melding-retentie",
        "cycle_retention_days": "Cyclus-retentie",
        "hours_since_ok": "Uren sinds OK",
        "last_ok_ts": "Laatste OK",
        "consecutive_failures": "Opeenvolgende fouten",
        "last_failure_reason": "Laatste fout",
        "buh_count_7d": "BUH-aantal 7d",
        "age_s": "Leeftijd", "threshold_s": "Drempel",
        "source_sensor": "Bron",
        "missing_count": "Ontbrekend", "missing_list": "Welke",
        "dhw_cph": "SWW-cycli/uur", "target_cph": "Doel",
        "multiplier": "Factor", "pct_diff": "Verschil",
        "cop_expected": "Verwacht",
        "today_el_kwh": "Vandaag kWh",
        "baseline_el_mean": "Baseline gemiddelde",
        "baseline_el_sigma": "Baseline sigma",
        "z_score": "Z-score",
    },
}


ALERT_SCHEMA = {
    "pendulum_hourly": [
        ("\U0001F4C8", "cycles_hour", "{cph}"),
        ("\U0001F3AF", "target_hour", "\u2264 {target_cph}"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "lwt_setpoint", "{lwt_setpoint} \u00b0C"),
        ("\u23F1\uFE0F", "last_duration", "{last_duration_min} min"),
        ("\u23F1\uFE0F", "avg_duration_7d", "{avg_duration_7d_min} min"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "pendulum_daily": [
        ("\U0001F4C8", "cycles_today", "{cycles_today}"),
        ("\U0001F3AF", "target_day", "\u2264 {target_cpd}"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "lwt_setpoint", "{lwt_setpoint} \u00b0C"),
        ("\u23F1\uFE0F", "last_duration", "{last_duration_min} min"),
        ("\u23F1\uFE0F", "avg_duration_7d", "{avg_duration_7d_min} min"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "short_run": [
        ("\u23F1\uFE0F", "duration", "{duration_min} min"),
        ("\U0001F3AF", "threshold", "{threshold_min} min"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "lwt_setpoint", "{lwt_setpoint} \u00b0C"),
        ("\U0001F321\uFE0F", "lwt_actual", "{lwt_actual} \u00b0C"),
        ("\U0001F321\uFE0F", "indoor", "{indoor} \u00b0C"),
        ("\U0001F4A7", "flow", "{flow} l/min"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "short_off": [
        ("\u23F1\uFE0F", "off_time", "{off_min} min"),
        ("\U0001F3AF", "threshold", "{threshold_min} min"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "lwt_setpoint", "{lwt_setpoint} \u00b0C"),
        ("\U0001F321\uFE0F", "indoor", "{indoor} \u00b0C"),
        ("\U0001F4A7", "flow", "{flow} l/min"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "ml_anomaly": [
        ("\u26A0\uFE0F", "severity", "{severity_label}"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F4C8", "zscore", "{z_max}"),
        ("\U0001F3AF", "top_dim", "{top_dim}"),
        ("\u23F1\uFE0F", "last_duration", "{last_duration_min} min"),
        ("\u23F1\uFE0F", "avg_duration_7d", "{avg_duration_7d_min} min"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "setpoint_osc": [
        ("\U0001F3AF", "lwt_setpoint", "{lwt_setpoint} \u00b0C"),
        ("\U0001F3AF", "lwt_target", "{lwt_target} \u00b0C"),
        ("\U0001F4C8", "delta_max", "\u0394 {delta_max} \u00b0C"),
        ("\U0001F501", "changes", "{osc_count} \u00d7"),
        ("\u23F1\uFE0F", "window", "{window_min} min"),
        ("\U0001F3AF", "threshold", "{threshold} \u00d7"),
        ("\U0001F501", "mode", "{mode}"),
    ],
    "cop_degradation": [
        ("\U0001F4C9", "week_pct", "{week_pct}%"),
        ("\U0001F3AF", "threshold", "\u2264 {threshold_pct}%"),
        ("\U0001F4C8", "trend_30d", "{trend_30d}"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "defrost_excessive": [
        ("\u2744\uFE0F", "count_7d", "{count_7d} / 7d"),
        ("\U0001F3AF", "threshold", "\u2264 {threshold}"),
        ("\u23F1\uFE0F", "duration_7d_min", "{duration_7d_min} min"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "buh_excessive": [
        ("\U0001F525", "buh_ratio_7d", "{buh_ratio_7d}"),
        ("\U0001F3AF", "threshold_ratio", "\u2264 {threshold_ratio}"),
        ("\U0001F4C8", "buh_count_7d", "{buh_count_7d}"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "source_stale": [
        ("\U0001F4E1", "age_s", "{age_s} s"),
        ("\U0001F3AF", "threshold_s", "{threshold_s} s"),
        ("\U0001F517", "source_sensor", "{source_sensor}"),
        ("\U0001F501", "mode", "{mode}"),
    ],
    "cop_physically_impossible": [
        ("\U0001F9EA", "count", "{count}"),
    ],
    "missing_attributes": [
        ("\u2753", "missing_count", "{missing_count}"),
        ("\U0001F4CB", "missing_list", "{missing_list}"),
        ("\U0001F517", "source_sensor", "{source_sensor}"),
        ("\U0001F501", "mode", "{mode}"),
    ],
    "dhw_pendulum": [
        ("\U0001F6BF", "dhw_cph", "{dhw_cph}"),
        ("\U0001F3AF", "target_cph", "\u2264 {target_cph}"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "high_cycle_rate": [
        ("\U0001F504", "cycles_hour", "{cph}"),
        ("\U0001F3AF", "target_cph", "\u2264 {target_cph} \u00d7 {multiplier}"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "cop_vs_datasheet_low": [
        ("\U0001F4CA", "pct_diff", "{pct_diff}%"),
        ("\U0001F3AF", "cop_expected", "vs {cop_expected}"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
    "db_retention_warning": [
        ("\U0001F5C4\uFE0F", "stale_alerts", "{stale_alerts}"),
        ("\U0001F5C4\uFE0F", "stale_cycles", "{stale_cycles}"),
        ("\U0001F3AF", "alert_retention_days", "{alert_retention_days} d"),
        ("\U0001F3AF", "cycle_retention_days", "{cycle_retention_days} d"),
        ("\U0001F501", "mode", "{mode}"),
    ],
    "kmeans_retrain_stale": [
        ("\u2699\ufe0f", "hours_since_ok", "{hours_since_ok} h"),
        ("\U0001F4C5", "last_ok_ts", "{last_ok_ts}"),
        ("\U0001F504", "consecutive_failures", "{consecutive_failures}"),
        ("\U0001F4CB", "last_failure_reason", "{last_failure_reason}"),
        ("\U0001F501", "mode", "{mode}"),
    ],
    "energy_daily_anomaly": [
        ("\u26A1\uFE0F", "today_el_kwh", "{today_el_kwh} kWh"),
        ("\U0001F4CA", "baseline_el_mean", "{baseline_el_mean} kWh"),
        ("\U0001F4C8", "baseline_el_sigma", "\u00b1 {baseline_el_sigma} kWh"),
        ("\U0001F4CF", "z_score", "{z_score}\u03c3"),
        ("\U0001F4E6", "samples", "{samples}"),
        ("\U0001F501", "mode", "{mode}"),
    ],
    "short_cycling_pattern": [
        ("\U0001F504", "min_cycles", "\u2265 {min_cycles}"),
        ("\u23F1\uFE0F", "window_min", "{window_min} min"),
        ("\U0001F3AF", "threshold_min", "{threshold_min} min"),
        ("\U0001F501", "mode", "{mode}"),
        ("\U0001F321\uFE0F", "outdoor", "{outdoor} \u00b0C"),
    ],
}


def build_rich_alert(alert_type: str, severity: str, context: Mapping[str, Any], *, language: str = "en", emoji_enabled: bool = True, full_model: str = "") -> str:
    """Alert message for end users (#463).

    Title, level (no action needed / keep an eye on it / action needed),
    what happened, what to do, where to look (native card -> tab -> graph)
    and up to four facts that explain the alert. Texts: engine/alert_texts*.
    """
    lang = language if language in _ALERT_TEXTS else "en"
    labels = ALERT_LABELS.get(lang, ALERT_LABELS["en"])
    ctx = dict(context or {})
    if "mode" in ctx:
        ctx["mode"] = MODE_LABELS.get(lang, MODE_LABELS["en"]).get(ctx["mode"], ctx["mode"])
    parts = _alert_message_parts(alert_type, ctx, lang)
    if severity == "critical" and parts["level"] == _LEVEL_INFO:
        # A critical trigger (e.g. ml_anomaly z >= 6) is never "no action needed".
        parts["level"] = _LEVEL_WATCH
        parts["level_text"] = _ALERT_TEXTS[lang].LEVELS[_LEVEL_WATCH]
    head_e = ALERT_TYPE_EMOJI.get(alert_type) or SEVERITY_EMOJI.get(severity, "") or "\U0001F514"
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    def _e(emoji: str) -> str:
        return (emoji + " ") if emoji_enabled else ""

    lines = [
        _e(head_e) + "Daikin Cycle ML \u2014 " + parts["title"],
        _subtitle_line(ts, full_model, emoji_enabled),
        DIV,
        _e(_LEVEL_EMOJI[parts["level"]]) + parts["level_text"],
        parts["what"],
        _e("\U0001F449") + str(ctx.get("advice") or parts["todo"]).strip(),
    ]
    if parts["see"]:
        lines.append(_e("\U0001F50E") + parts["see"])
    facts: list[str] = []
    rows = sorted(ALERT_SCHEMA.get(alert_type) or [], key=lambda r: _fact_rank(r[2]))
    for emoji, label_key, tpl in rows:
        names = _alert_fields(tpl)
        if not names or names & _HIDDEN_FACTS or names & parts["used"]:
            continue
        value = _alert_fill(tpl, ctx, lang)
        if value is None:
            continue
        sep = "\u00a0: " if lang == "fr" else ": "
        facts.append(_e(emoji) + labels.get(label_key, label_key) + sep + value)
        if len(facts) >= _MAX_FACTS:
            break
    if facts:
        lines.append(DIV)
        lines.extend(facts)
    lines.append(DIV)
    return "\n".join(line for line in lines if line)

SEVERITY_LABELS = {
    "en": {"critical": "critical", "warning": "warning",
           "watch": "watch", "normal": "normal", "info": "info"},
    "nl": {"critical": "kritiek", "warning": "waarschuwing",
           "watch": "let op", "normal": "normaal", "info": "informatie"},
}


# ---------------------------------------------------------------------
# French (fr) — azsono03 fork. Same keys as "en"; any key missing here
# falls back to the English text through the .get(...) lookups above.
# ---------------------------------------------------------------------
GREETINGS["fr"] = {
    "morning":   ("\U0001F305", "RAPPORT DU MATIN",      "\u2615 Bonjour \u2014 bonne journ\u00e9e !"),
    "afternoon": ("\u2600\uFE0F", "RAPPORT DE L'APR\u00c8S-MIDI", "\u2615 Bon apr\u00e8s-midi !"),
    "evening":   ("\U0001F307", "RAPPORT DU SOIR",       "\U0001F319 Bonne soir\u00e9e !"),
    "night":     ("\U0001F319", "RAPPORT DE NUIT",       "\U0001F634 Nuit calme \u2014 tout va bien."),
}

LABELS["fr"] = {
    "status": "\u00c9tat", "mode": "Mode", "last": "Dernier cycle",
    "quality": "Qualit\u00e9", "lwt": "D\u00e9part eau", "indoor": "Int\u00e9rieur",
    "outdoor": "Ext\u00e9rieur", "flow": "D\u00e9bit", "thermal": "Chaleur",
    "cycles_today": "Cycles aujourd'hui", "short": "Cycles courts",
    "good": "Bons cycles", "per_hour": "Par heure",
    "baseline": "R\u00e9f\u00e9rence", "anomaly": "Anomalie", "cop_today": "COP du jour",
    "stats": "Statistiques", "total": "Total", "today": "Aujourd'hui",
    "d7": "7 j", "d30": "30 j", "avg_dur": "Dur\u00e9e moyenne",
}

MODE_LABELS["fr"] = {
    "heating": "chauffage", "cooling": "rafra\u00eechissement",
    "dhw": "eau chaude", "unknown": "inconnu",
}

ALERT_LABELS["fr"] = {
    "cycles_hour": "Cycles / heure", "target_hour": "Objectif",
    "cycles_today": "Cycles aujourd'hui", "target_day": "Objectif",
    "duration": "Dur\u00e9e", "threshold": "Seuil",
    "off_time": "Temps d'arr\u00eat", "mode": "Mode",
    "zscore": "\u00c9cart (z)", "top_dim": "Crit\u00e8re principal",
    "changes": "Changements", "window": "Fen\u00eatre",
    "lwt_setpoint": "Eau, consigne", "lwt_target": "Eau, consigne de la loi d'eau",
    "lwt_actual": "Eau, maintenant", "outdoor": "Ext\u00e9rieur",
    "last_duration": "Dernier cycle", "avg_duration_7d": "Cycle moyen (7 jours)",
    "samples": "\u00c9chantillons", "delta_max": "\u00c9cart de consigne",
    "cop": "COP", "severity": "Gravit\u00e9",
    "indoor": "Int\u00e9rieur", "flow": "D\u00e9bit",
    "week_pct": "Semaine", "threshold_pct": "Seuil",
    "trend_30d": "Tendance du COP (30 jours)",
    "count_7d": "Nombre 7 j", "duration_7d_min": "Temps de d\u00e9givrage (7 jours)",
    "buh_ratio_7d": "Part de l'appoint", "threshold_ratio": "Seuil",
    "stale_alerts": "Alertes \u00e0 purger", "stale_cycles": "Cycles \u00e0 purger",
    "alert_retention_days": "Conservation alertes",
    "cycle_retention_days": "Conservation cycles",
    "hours_since_ok": "Heures depuis OK",
    "last_ok_ts": "Dernier OK",
    "consecutive_failures": "\u00c9checs d'affil\u00e9e",
    "last_failure_reason": "Dernier \u00e9chec",
    "buh_count_7d": "Appoint 7 j",
    "age_s": "\u00c2ge", "threshold_s": "Seuil",
    "source_sensor": "Source",
    "missing_count": "Manquantes", "missing_list": "Lesquelles",
    "dhw_cph": "Cycles ECS / h", "target_cph": "Objectif",
    "multiplier": "Facteur", "pct_diff": "\u00c9cart",
    "cop_expected": "Attendu",
    "today_el_kwh": "Aujourd'hui kWh",
    "baseline_el_mean": "Moyenne de r\u00e9f\u00e9rence",
    "baseline_el_sigma": "\u00c9cart type",
    "z_score": "\u00c9cart (z)",
    "count": "Nombre",
    "min_cycles": "Cycles min.", "window_min": "Fen\u00eatre",
    "threshold_min": "Seuil",
}

SEVERITY_LABELS["fr"] = {
    "critical": "critique", "warning": "avertissement",
    "watch": "\u00e0 surveiller", "normal": "normal", "info": "info",
}


# ---------------------------------------------------------------------
# #463: titles, advice and learning-status texts come from
# engine/alert_texts_<lang>.py (same keys in en / nl / fr). The names are
# kept for the callers and tests that read them.
# ---------------------------------------------------------------------
ALERT_TITLES: dict[str, dict[str, str]] = {
    lang: {**{t: a["title"] for t, a in mod.ALERTS.items()}, **mod.OTHER_TITLES}
    for lang, mod in _ALERT_TEXTS.items()
}
ALERT_ADVICE: dict[str, dict[str, str]] = {
    lang: {t: a["todo"] for t, a in mod.ALERTS.items()} for lang, mod in _ALERT_TEXTS.items()
}
KMEANS_ADVICE_BY_REASON: dict[str, dict[str | None, str]] = {
    lang: dict(mod.KMEANS_REASONS) for lang, mod in _ALERT_TEXTS.items()
}

