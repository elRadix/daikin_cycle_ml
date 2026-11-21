"""#463: alert messages for end users, in en / nl / fr.

Contract:
- every alert type has a title, a sentence with values, a plain sentence
  and a to-do in every language, with the same placeholders;
- a rendered alert never shows a raw {placeholder}, None, an option key or
  jargon (z-score, k-means, sigma), and has at most four fact lines;
- the level line says whether action is needed; a critical trigger is
  never "no action needed";
- the language follows Home Assistant unless the user picked one;
- texts reviewed by an HVAC engineer: no filter advice, ice is never
  scraped off, the backup heater text names its normal uses.
"""
from __future__ import annotations

import re

import pytest

from custom_components.daikin_cycle_ml.engine import alert_texts as at
from custom_components.daikin_cycle_ml.engine.notify_format import escape_for_parse_mode
from custom_components.daikin_cycle_ml.engine.status_report import (
    ALERT_SCHEMA,
    ALERT_TITLES,
    DIV,
    build_rich_alert,
)

TYPES = sorted(at.LEVEL)
FIELD = re.compile(r"\{(\w+)\}")

# Context values in the shape coordinator._build_alert_context sends them
# (preformatted strings, counts as ints). Every placeholder of every
# template has one, so each alert renders its full sentence.
CTX = {
    "cph": 6, "target_cph": 4, "cycles_today": 46, "target_cpd": 40,
    "duration_min": 12, "threshold_min": 20, "min_cycles": 3, "window_min": 60,
    "off_min": 3, "outdoor": "8.2", "lwt_actual": "34.5", "lwt_setpoint": "35.0",
    "lwt_target": "34.0", "mode": "heating", "flow": "18.4", "indoor": "20.6",
    "osc_count": 7, "week_pct": "-12.5", "count_7d": 41, "threshold": 30,
    "buh_count_7d": 9, "age_s": 900, "count": 2, "missing_count": 2,
    "missing_list": "Flow sensor (l/min), DHW tank temp. (R5T)", "dhw_cph": 5,
    "pct_diff": "-14", "cop_expected": "4.1", "stale_alerts": 120, "stale_cycles": 40,
    "hours_since_ok": 410, "today_el_kwh": "15.5", "baseline_el_mean": "6.0",
    "z_max": 6.4, "top_dim": "duration_s", "z_score": 4.9, "baseline_el_sigma": "1.2",
    "multiplier": 1.5, "last_duration_min": 14, "avg_duration_7d_min": 38,
}
JARGON = ("z-score", "z_max", "k-means", "kmeans", "sigma", "recompute_", "_threshold", "duration_s")


@pytest.mark.parametrize("lang", ["nl", "fr"])
def test_same_keys_and_placeholders_as_english(lang: str) -> None:
    en, other = at.TEXTS["en"], at.TEXTS[lang]
    assert set(other.ALERTS) == set(en.ALERTS) == set(at.LEVEL) == set(at.SEE)
    for t, text in en.ALERTS.items():
        for key in ("title", "what", "what_plain", "todo"):
            assert set(FIELD.findall(other.ALERTS[t][key])) == set(FIELD.findall(text[key])), (t, key)
    assert set(other.KMEANS_REASONS) == set(en.KMEANS_REASONS)
    assert set(other.OTHER_TITLES) == set(en.OTHER_TITLES)
    for name in ("LEVELS", "CARDS", "GRAPHS"):
        assert set(getattr(other, name)) == set(getattr(en, name))
    assert {c: set(t) for c, t in other.TABS.items()} == {c: set(t) for c, t in en.TABS.items()}


def test_plain_sentence_and_todo_have_no_placeholders() -> None:
    for lang in at.LANGS:
        for t, text in at.TEXTS[lang].ALERTS.items():
            assert not FIELD.findall(text["what_plain"]), (lang, t)
            assert not FIELD.findall(text["todo"]), (lang, t)
            assert not FIELD.findall(text["title"]), (lang, t)


@pytest.mark.parametrize("lang", at.LANGS)
@pytest.mark.parametrize("alert_type", TYPES)
def test_every_alert_renders_clean(alert_type: str, lang: str) -> None:
    out = build_rich_alert(alert_type, "warning", CTX, language=lang, full_model="EPRA12EAV3")
    text = at.TEXTS[lang].ALERTS[alert_type]
    assert "{" not in out and "None" not in out
    for word in JARGON:
        assert word not in out.lower(), (alert_type, lang, word)
    assert text["title"] in out
    assert at.TEXTS[lang].LEVELS[at.LEVEL[alert_type]] in out
    assert text["todo"] in out
    # Full sentence with the values, in the language's number format.
    assert at.fill(text["what"], CTX, lang) in out
    if lang in ("nl", "fr"):
        assert "8,2" in out or "outdoor" not in FIELD.findall(text["what"])
    facts = out.split(DIV)[2:-1]
    fact_lines = [ln for block in facts for ln in block.splitlines() if ln.strip()]
    assert len(fact_lines) <= at.MAX_FACTS
    see = at.see_line(alert_type, lang)
    assert (see in out) if at.SEE[alert_type] else ("🔎" not in out)


@pytest.mark.parametrize("lang", at.LANGS)
def test_missing_value_falls_back_to_plain_sentence(lang: str) -> None:
    out = build_rich_alert("short_run", "warning", {"threshold_min": 20}, language=lang)
    assert at.TEXTS[lang].ALERTS["short_run"]["what_plain"] in out
    assert "{duration_min}" not in out


def test_used_values_are_not_repeated_as_facts() -> None:
    out = build_rich_alert("pendulum_hourly", "warning", CTX, language="en")
    assert out.count("6 compressor starts") == 1
    assert "8.2 °C" in out  # outdoor first in the facts


def test_french_uses_non_breaking_space_before_colon() -> None:
    out = build_rich_alert("short_run", "warning", CTX, language="fr")
    assert " : " in out


def test_critical_never_reads_no_action_needed() -> None:
    assert at.LEVEL["ml_anomaly"] == at.LEVEL_INFO
    for lang in at.LANGS:
        out = build_rich_alert("ml_anomaly", "critical", CTX, language=lang)
        assert at.TEXTS[lang].LEVELS[at.LEVEL_WATCH] in out
        assert at.TEXTS[lang].LEVELS[at.LEVEL_INFO] not in out


def test_unknown_type_renders_title_only() -> None:
    out = build_rich_alert("no_such_alert", "warning", {}, language="nl")
    assert "no_such_alert" in out
    assert "Geen actie nodig" in out
    assert "\n\n" not in out


def test_emoji_off_has_no_emoji_markers() -> None:
    out = build_rich_alert("defrost_excessive", "warning", CTX, language="en", emoji_enabled=False)
    for marker in ("👉", "🔎", "⚠️", "ℹ️", "⛔"):
        assert marker not in out


@pytest.mark.parametrize(
    ("options", "ha", "expected"),
    [
        ({}, "nl", "nl"),
        ({"notification_language": "auto"}, "fr", "fr"),
        ({"notification_language": "auto"}, "de", "en"),
        ({"notification_language": "en"}, "nl", "en"),
        ({"notification_language": "FR"}, "nl", "fr"),
        ({"notification_language": "xx"}, "nl-BE", "nl"),
        (None, None, "en"),
    ],
)
def test_language_follows_home_assistant_unless_chosen(options, ha, expected) -> None:
    assert at.resolve_language(options, ha) == expected


def test_titles_include_the_two_other_messages() -> None:
    for lang in at.LANGS:
        assert set(ALERT_TITLES[lang]) == set(at.LEVEL) | {"cop_low", "stooklijn_advies"}


def test_every_schema_alert_has_texts() -> None:
    assert set(ALERT_SCHEMA) <= set(at.LEVEL)


@pytest.mark.parametrize("mode", ["markdown", "markdownv2", "html"])
@pytest.mark.parametrize("lang", at.LANGS)
def test_telegram_escape_keeps_every_alert_readable(lang: str, mode: str) -> None:
    for t in TYPES:
        out = build_rich_alert(t, "warning", CTX, language=lang)
        escaped = escape_for_parse_mode(out, mode)
        title = at.TEXTS[lang].ALERTS[t]["title"]
        plain = re.sub(r"\\(.)", r"\1", escaped).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        assert title in plain


def test_hvac_review_rules() -> None:
    """Texts reviewed by an HVAC engineer (#463)."""
    for lang in at.LANGS:
        mod = at.TEXTS[lang]
        joined = " ".join(" ".join(a.values()) for a in mod.ALERTS.values()).lower()
        assert "filter" not in joined and "filtre" not in joined
    en = at.TEXTS["en"].ALERTS
    assert "never scrape ice" in en["defrost_excessive"]["todo"]
    assert "never scrape ice" in en["cop_degradation"]["todo"]
    assert "disinfection" in en["buh_excessive"]["todo"]
    assert "emergency" in en["buh_excessive"]["todo"]
    assert "radiator valves" in en["short_cycling_pattern"]["todo"]
    assert "keeps heating" in en["source_stale"]["todo"]
    assert "pompe à chaleur" in at.TEXTS["fr"].ALERTS["ml_anomaly"]["what"]
    assert at.LEVEL["short_run"] == at.LEVEL_INFO
    assert at.LEVEL["cop_physically_impossible"] == at.LEVEL_WATCH
    assert at.LEVEL["source_stale"] == at.LEVEL_ACT
