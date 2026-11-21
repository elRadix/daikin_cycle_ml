"""#475: one list of actions behind the Efficiency card's badge, tab dots and Advice.

Replay of the Tweakers report: the header said "⛔ Act" while Advice said
"Keep the curve" and nothing else. Live COP below the datasheet (watch),
the datasheet comparison of the day critical (bad, Efficiency tab), backup
heater minutes (watch, Today) and a heat-balance gap (watch, Curve). The
badge, the dots and the "What needs attention" list come from the same
list, so they cannot disagree.
"""
from __future__ import annotations

import html as _html
import re

import pytest

from tests.test_efficiency_native_card import _case, _run, _set, _text


def _reported(lang: str) -> dict:
    case = _set({**_case(lang), "history": {}}, "thermal_power_live", input_cop=3.8)
    return _set(case, "cop_vs_datasheet_pct", "-31", band="critical")


@pytest.fixture(scope="module")
def out() -> dict:
    cases = {lang: _reported(lang) for lang in ("en", "nl", "fr")}
    cases["calm"] = _set(_case(), "runtime_buh_today", "0")
    return _run(cases)


def _todo(html: str) -> str:
    m = re.search(r'<div class="todo" id="todo">(.*?)</ul>|<div class="todo" id="todo">(.*?)</div></div>', html, re.S)
    assert m, html[:400]
    return _text(m.group(0))


def test_act_badge_is_explained_in_advice(out):
    r = out["cases"]["en"]
    assert r["overall"] == "bad"
    advice = r["html"]["advice"]
    todo = _todo(advice)
    # the bad verdict of the Efficiency tab is listed first, with a link to that tab
    assert todo.index("Well below spec") < todo.index("below the datasheet")
    assert "See Efficiency ›" in todo and "See Live ›" in todo
    # the heating-curve advice stays below the list
    assert advice.index('id="todo"') < advice.index('class="adv ')


def test_badge_count_matches_the_list_on_every_tab(out):
    r = out["cases"]["en"]
    for tab, html in r["html"].items():
        badge = re.search(r'<button class="chip (\w+)" data-act="todo"[^>]*>(.*?)</button>', html, re.S)
        assert badge and badge.group(1) == "bad", tab
        n = int(badge.group(2).rsplit("·", 1)[1])
        assert n == r["html"]["advice"].count("data-todo="), tab
        assert n >= 3


def test_tabs_with_something_to_do_carry_a_dot(out):
    html = out["cases"]["en"]["html"]["live"]
    dots = dict(re.findall(r'data-tab="(\w+)">[^<]*<i class="tdot (\w+)"', html))
    assert dots.get("eff") == "bad" and dots.get("live") == "watch" and dots.get("today") == "watch"


@pytest.mark.parametrize(("lang", "title", "see"), [
    ("en", "What needs attention", "See"), ("nl", "Wat aandacht vraagt", "Zie"), ("fr", "Points d'attention", "Voir"),
])
def test_texts_in_every_language(out, lang, title, see):
    advice = _html.unescape(_text(out["cases"][lang]["html"]["advice"]))
    assert title in advice and f"{see} " in advice
    assert "undefined" not in advice and "NaN" not in advice


def test_nothing_to_do_says_so(out):
    r = out["cases"]["calm"]
    advice = r["html"]["advice"]
    if r["overall"] in ("good", "info"):
        assert "Nothing needs attention" in _text(advice) and "data-todo=" not in advice
        assert "tdot" not in r["html"]["live"]
    else:  # the fixture still has something: the list and the badge agree
        assert advice.count("data-todo=") >= 1


CLICKS = r"""
const { chromium } = require('playwright'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 400, height: 900 } });
  const errors = []; p.on('pageerror', (e) => errors.push(e.message));
  await p.setContent('<html><body><div id="c"></div></body></html>');
  await p.addScriptTag({ content: "customElements.define('ha-card', class extends HTMLElement {});" });
  for (const f of D.files) await p.addScriptTag({ content: fs.readFileSync(f, 'utf8') });
  const res = await p.evaluate(async (c) => {
    const N = Date.parse(c.now); Date.now = () => N;
    const el = document.createElement('daikin-efficiency-card'); el.setConfig({});
    document.getElementById('c').appendChild(el);
    el.hass = { states: c.states, entities: c.entities, language: 'en', locale: { language: 'en' }, callWS: async () => ({}) };
    await new Promise((r) => setTimeout(r, 50));
    const q = (s) => el.shadowRoot.querySelector(s), tab = () => q('.tab.on').dataset.tab;
    const out = { first: tab(), chip: q('.chip').textContent.trim(), dots: el.shadowRoot.querySelectorAll('.tdot').length };
    q('.chip').click(); out.afterChip = tab(); out.items = el.shadowRoot.querySelectorAll('[data-todo]').length;
    const go = q('.todo .go'); out.goTab = go.dataset.tab; go.click(); out.afterGo = tab();
    return out;
  }, D.case);
  res.errors = errors; process.stdout.write(JSON.stringify(res)); await b.close();
})().catch((e) => { process.stderr.write(String(e)); process.exit(1); });
"""


def test_badge_and_links_switch_tabs_in_chromium():
    import json
    import subprocess

    from tests.test_efficiency_native_card import FRONT, ORDER, _playwright

    if not _playwright():
        pytest.skip("playwright (node) not installed")
    proc = subprocess.run(
        ["node", "-e", CLICKS], capture_output=True, text=True, timeout=180, check=False,
        input=json.dumps({"files": [str(FRONT / f) for f in ORDER], "case": _reported("en")}),
    )
    assert proc.returncode == 0, proc.stderr
    r = json.loads(proc.stdout)
    assert r["errors"] == []
    assert r["first"] == "live" and r["chip"].startswith("⛔ Act · ") and r["dots"] >= 3
    assert r["afterChip"] == "advice" and r["items"] >= 3
    assert r["goTab"] == "eff" and r["afterGo"] == "eff"
