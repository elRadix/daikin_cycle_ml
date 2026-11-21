"""#451: alerts to a Telegram notify entity are escaped for the bot's parse mode.

prod-1 (HA 2026.11): every alert to notify.telegram_<chat> failed with
"Can't parse entities: can't find end of the entity". The bot sends with
its default parse mode, Markdown, and our texts contain option names with
underscores (short_off_threshold_min, window_min, recompute_kmeans).
"""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.daikin_cycle_ml import coordinator as co
from custom_components.daikin_cycle_ml.engine.notify_format import escape_for_parse_mode
from homeassistant.helpers import entity_registry as er

# the end of the prod-1 short-off alert that Telegram rejected
PROD1 = ("• Off-time too short: if false positives, decrease short_off_threshold_min; "
         "run daikin_cycle_ml.recompute_kmeans *now* [x] `y`")


def test_markdown_escapes_the_markdown_characters():
    out = escape_for_parse_mode(PROD1, "markdown")
    assert "short\\_off\\_threshold\\_min" in out and "recompute\\_kmeans" in out
    assert "\\*now\\*" in out and "\\[x]" in out and "\\`y\\`" in out
    assert escape_for_parse_mode(PROD1, None) == out  # Markdown is the bot default


def test_markdownv2_html_and_plain():
    assert escape_for_parse_mode("a_b. (c)! 1-2 \\", "markdownv2") == "a\\_b\\. \\(c\\)\\! 1\\-2 \\\\"
    assert escape_for_parse_mode("<b>&</b>", "html") == "&lt;b&gt;&amp;&lt;/b&gt;"
    assert escape_for_parse_mode(PROD1, "plain_text") == PROD1
    assert escape_for_parse_mode(PROD1, "something_new") == PROD1


def _coord(hass):
    c = co.DaikinCycleMLCoordinator.__new__(co.DaikinCycleMLCoordinator)
    c.hass = hass
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._notify_fail_logged = set()
    return c


async def _send(hass, entity_id: str, platform: str, options: dict | None) -> dict:
    entry = MockConfigEntry(domain=platform, options=options or {})
    entry.add_to_hass(hass)
    reg = er.async_get(hass)
    obj = entity_id.split(".", 1)[1]
    reg.async_get_or_create("notify", platform, obj, suggested_object_id=obj, config_entry=entry)
    hass.states.async_set(entity_id, "unknown")
    calls = async_mock_service(hass, "notify", "send_message")
    assert await _coord(hass)._dispatch_notify(entity_id, PROD1) is True
    await hass.async_block_till_done()
    assert len(calls) == 1 and calls[0].data["entity_id"] == entity_id
    return dict(calls[0].data)


@pytest.mark.parametrize(("options", "expected"), [
    ({}, "short\\_off\\_threshold\\_min"),                      # default Markdown
    ({"parse_mode": "markdown"}, "short\\_off\\_threshold\\_min"),
    ({"parse_mode": "html"}, "short_off_threshold_min"),
    ({"parse_mode": "plain_text"}, "short_off_threshold_min"),
])
async def test_telegram_entity_text_follows_the_bot_parse_mode(hass, options, expected):
    payload = await _send(hass, "notify.telegram_chat", "telegram_bot", options)
    assert expected in payload["message"]


async def test_other_notify_entities_are_untouched(hass):
    payload = await _send(hass, "notify.signal_chat", "signal_messenger", {"parse_mode": "markdown"})
    assert payload["message"] == PROD1


async def test_entity_without_registry_entry_is_untouched(hass):
    hass.states.async_set("notify.adhoc", "unknown")
    calls = async_mock_service(hass, "notify", "send_message")
    assert await _coord(hass)._dispatch_notify("notify.adhoc", PROD1) is True
    await hass.async_block_till_done()
    assert calls[0].data["message"] == PROD1
