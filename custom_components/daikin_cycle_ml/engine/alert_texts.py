"""Alert messages for end users (#463): level, texts, card pointers.

Every alert answers two questions for the user: do I need to do
something, and if not, where can I see what is going on. The texts live
per language in alert_texts_en / _nl / _fr (same keys, same
placeholders: tests/test_463_alert_messages.py); this module holds what
is shared: the level of each alert type, the native card it points to,
and the rendering helpers.

Pure module: no Home Assistant imports.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from . import alert_texts_en, alert_texts_fr, alert_texts_nl

LANGS = ("en", "nl", "fr")
TEXTS: dict[str, Any] = {"en": alert_texts_en, "nl": alert_texts_nl, "fr": alert_texts_fr}

LEVEL_INFO = "info"     # no action needed
LEVEL_WATCH = "watch"   # keep an eye on it
LEVEL_ACT = "act"       # action needed
LEVEL_EMOJI = {LEVEL_INFO: "ℹ️", LEVEL_WATCH: "⚠️", LEVEL_ACT: "⛔"}

LEVEL: dict[str, str] = {
    "pendulum_hourly": LEVEL_WATCH,
    "pendulum_daily": LEVEL_WATCH,
    "short_run": LEVEL_INFO,
    "short_cycling_pattern": LEVEL_WATCH,
    "short_off": LEVEL_INFO,
    "ml_anomaly": LEVEL_INFO,
    "setpoint_osc": LEVEL_INFO,
    "cop_degradation": LEVEL_WATCH,
    "defrost_excessive": LEVEL_WATCH,
    "buh_excessive": LEVEL_WATCH,
    "source_stale": LEVEL_ACT,
    "cop_physically_impossible": LEVEL_WATCH,
    "missing_attributes": LEVEL_WATCH,
    "dhw_pendulum": LEVEL_WATCH,
    "high_cycle_rate": LEVEL_WATCH,
    "cop_vs_datasheet_low": LEVEL_INFO,
    "db_retention_warning": LEVEL_WATCH,
    "kmeans_retrain_stale": LEVEL_INFO,
    "energy_daily_anomaly": LEVEL_WATCH,
}

# Where the user sees it: (card, tab, graph or None). Names per language
# in alert_texts_<lang>.CARDS / TABS / GRAPHS, equal to the card labels.
SEE: dict[str, tuple[tuple[str, str, str | None], ...]] = {
    "pendulum_hourly": (("eff", "live", "compressor"), ("daily", "cycles", None)),
    "pendulum_daily": (("daily", "cycles", None), ("eff", "live", "compressor")),
    "short_run": (("eff", "live", "compressor"),),
    "short_cycling_pattern": (("eff", "live", "compressor"), ("daily", "cycles", None)),
    "short_off": (("eff", "live", "compressor"),),
    "ml_anomaly": (("daily", "today", None), ("eff", "live", None)),
    "setpoint_osc": (("eff", "live", "water"),),
    "cop_degradation": (("eff", "eff", None),),
    "defrost_excessive": (("daily", "events", None), ("eff", "curve", "strip")),
    "buh_excessive": (("daily", "events", None), ("eff", "curve", "strip")),
    "source_stale": (),
    "cop_physically_impossible": (("eff", "curve", "balance"),),
    "missing_attributes": (),
    "dhw_pendulum": (("daily", "cycles", None),),
    "high_cycle_rate": (("eff", "live", "compressor"),),
    "cop_vs_datasheet_low": (("eff", "eff", None), ("eff", "curve", None)),
    "db_retention_warning": (),
    "kmeans_retrain_stale": (),
    "energy_daily_anomaly": (("eff", "today", None),),
}

# Context values that are no help to a user as a fact line.
HIDDEN_FACTS = frozenset({
    "z_max", "top_dim", "severity_label", "z_score", "baseline_el_sigma",
    "multiplier", "consecutive_failures", "last_failure_reason", "last_ok_ts",
    "threshold", "threshold_min", "threshold_s", "threshold_pct",
    "threshold_ratio", "target_cph", "target_cpd", "samples", "source_sensor",
    "alert_retention_days", "cycle_retention_days",
})
MAX_FACTS = 4
# Facts shown first: what explains most alerts (weather, water, mode).
FACT_PRIORITY = ("outdoor", "lwt_actual", "lwt_setpoint", "lwt_target", "mode", "flow",
                 "indoor", "last_duration_min", "avg_duration_7d_min", "duration_7d_min")

_FIELD = re.compile(r"\{(\w+)\}")
_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")
_EMPTY = (None, "", "—", "None", "unknown", "unavailable")


def resolve_language(options: Mapping[str, Any] | None, ha_language: str | None) -> str:
    """Notification language: the option when the user chose one, else the
    Home Assistant language (en / nl / fr), else English."""
    chosen = str((options or {}).get("notification_language") or "auto").lower()
    if chosen in LANGS:
        return chosen
    ha = str(ha_language or "").lower()[:2]
    return ha if ha in LANGS else "en"


def fact_rank(template: str) -> int:
    """Sort key of a fact row: FACT_PRIORITY order, the rest after it."""
    names = _FIELD.findall(template)
    ranks = [FACT_PRIORITY.index(n) for n in names if n in FACT_PRIORITY]
    return min(ranks) if ranks else len(FACT_PRIORITY)


def fields(template: str) -> set[str]:
    """Placeholder names of a template."""
    return set(_FIELD.findall(template))


def localize_number(text: str, language: str) -> str:
    """Decimal comma for Dutch and French (8.2 -> 8,2)."""
    return _DECIMAL.sub(",", text) if language in ("nl", "fr") else text


def fill(template: str, ctx: Mapping[str, Any], language: str) -> str | None:
    """Template with the context values, or None when a value is missing."""
    values: dict[str, str] = {}
    for name in fields(template):
        val = ctx.get(name)
        if val in _EMPTY:
            return None
        values[name] = localize_number(str(val), language)
    return template.format(**values)


def see_line(alert_type: str, language: str) -> str | None:
    """'See: Efficiency card -> Live -> Compressor' in the user's language."""
    mod = TEXTS[language]
    parts = []
    for card, tab, graph in SEE.get(alert_type, ()):
        names = [mod.CARDS[card], mod.TABS[card][tab]]
        if graph:
            names.append(mod.GRAPHS[graph])
        parts.append(" → ".join(names))
    if not parts:
        return None
    line: str = mod.WORDS["see"] + " " + mod.WORDS["or"].join(parts)
    return line


def message_parts(alert_type: str, ctx: Mapping[str, Any], language: str) -> dict[str, Any]:
    """Title, level, what happened, what to do, see-line and the fields used."""
    lang = language if language in TEXTS else "en"
    mod = TEXTS[lang]
    text = mod.ALERTS.get(alert_type)
    if text is None:
        return {"title": alert_type, "level": LEVEL_INFO, "level_text": mod.LEVELS[LEVEL_INFO],
                "what": "", "todo": "", "see": None, "used": set()}
    what = fill(text["what"], ctx, lang) or text["what_plain"]
    used = fields(text["what"]) if what != text["what_plain"] else set()
    return {
        "title": text["title"],
        "level": LEVEL.get(alert_type, LEVEL_INFO),
        "level_text": mod.LEVELS[LEVEL.get(alert_type, LEVEL_INFO)],
        "what": what,
        "todo": text["todo"],
        "see": see_line(alert_type, lang),
        "used": used,
    }
