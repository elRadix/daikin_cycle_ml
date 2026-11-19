"""Native Lovelace card ``custom:daikin-daily-summary-card``.

Node (vm, no browser) runs the card's pure functions on the states of the
real integration (tests/fixtures/card_states_427.json, en / nl / fr) and
on the #436 reporter's data. Chromium (Playwright, skipped when absent)
mounts the custom element, clicks tabs / windows / days / alerts, uses the
keyboard and drives the visual editor.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

from tests.test_427_cards_live_states import FIXTURE, _localized
from tests.test_436_quality_consistency import DAYS_436

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "custom_components/daikin_cycle_ml/frontend/daikin-daily-summary-card.js"
COMP = ROOT / "custom_components/daikin_cycle_ml"

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")

RUNNER = r"""
const vm = require('vm'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
const win = {};
const ctx = vm.createContext({ window: win, Intl, Date, Math, JSON, Object, Array, String, Number,
  parseFloat, isFinite, RegExp, Error, console: { info() {}, log() {}, warn() {} },
  HTMLElement: class {}, CustomEvent: class {}, document: {},
  customElements: { _d: {}, get(n) { return this._d[n]; }, define(n, c) { this._d[n] = c; } },
  setInterval: () => 0, clearInterval: () => 0 });
vm.runInContext(fs.readFileSync(D.card, 'utf8'), ctx);
const K = win.DaikinDailySummaryCard;
const out = { version: K.version, suffix: K.SUFFIX, defined: Object.keys(ctx.customElements._d),
  picker: win.customCards, cases: {} };
for (const [name, c] of Object.entries(D.cases)) {
  const hass = { states: c.states, entities: c.entities, language: c.lang, locale: { language: c.lang } };
  const m = K.buildModel(hass, c.config || {}, Date.parse(c.now || '2026-11-19T14:00:00+01:00'));
  const r = { ids: m.ids, lang: m.lang, ok: m.ok, days: m.allDays.length, html: {} };
  const days = m.allDays.slice(-(c.config && c.config.window || 7));
  r.stats = K.periodStats(days);
  r.stats.best = r.stats.best && r.stats.best.day; r.stats.worst = r.stats.worst && r.stats.worst.day;
  r.dayq = days.map((d) => [d.day, d.quality === null ? null : Math.round(d.quality), d.runs, d.avg_run]);
  for (const tab of K.TABS) {
    const ui = Object.assign({ tab, win: 7, day: null, alert: null, allAlerts: false }, c.ui || {}, { tab });
    r.html[tab] = K.render(m, c.config || {}, ui);
  }
  out.cases[name] = r;
}
process.stdout.write(JSON.stringify(out));
"""


def _run(cases: dict) -> dict:
    proc = subprocess.run(
        ["node", "-e", RUNNER], capture_output=True, text=True, timeout=120,
        input=json.dumps({"card": str(CARD), "cases": cases}), check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _fixture(lang: str) -> dict:
    loc = _localized(json.loads(FIXTURE.read_text(encoding="utf-8")), lang)
    return {"states": loc["states"], "entities": loc["entities"], "lang": lang, "now": loc["now"]}


def _without_registry(case: dict) -> dict:
    return {**case, "entities": {}}


def _states_436() -> dict:
    case = _fixture("en")
    sid = "sensor.daikin_cycle_ml_daily_summary_recent"
    st = json.loads(json.dumps(case["states"][sid]))
    st["attributes"].update({"days": DAYS_436, "events_by_day": {}})
    case["states"][sid] = st
    return case


@pytest.fixture(scope="module")
def out() -> dict:
    cases = {lang: _fixture(lang) for lang in ("en", "nl", "fr")}
    cases["nl_no_registry"] = _without_registry(_fixture("nl"))
    cases["fr_no_registry"] = _without_registry(_fixture("fr"))
    cases["i436"] = _states_436()
    cases["lang_override"] = {**_fixture("en"), "config": {"language": "fr"}}
    cases["other_device"] = {**_fixture("en"), "config": {"device_id": "not-this-one"}}
    cases["empty"] = {"states": {}, "entities": {}, "lang": "en"}
    xss = _fixture("en")
    aid = "sensor.daikin_cycle_ml_alerts_today"
    st = json.loads(json.dumps(xss["states"][aid]))
    st["attributes"]["alerts"] = [{
        "time": "2026-11-19T10:00:00", "type": "x", "severity": "warning",
        "message": "<img src=x onerror=alert(1)> — <b>boom</b>\n━━━━\n<script>bad()</script>",
    }]
    xss["states"][aid] = st
    cases["xss"] = {**xss, "ui": {"alert": 0}}
    first = _fixture("en")
    for role, value in (("cycles_today", "0"), ("last_cycle", "unknown")):
        eid = f"sensor.daikin_cycle_ml_{role}"
        first["states"][eid] = {**first["states"][eid], "state": value}
    cases["first_run"] = first
    return _run(cases)


def test_suffix_table_matches_translations(out):
    def slug(s: str) -> str:
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    tr = {
        lang: json.loads((COMP / f"translations/{lang}.json").read_text(encoding="utf-8"))
        for lang in ("en", "nl", "fr")
    }
    for role, names in out["suffix"].items():
        expected = [slug(tr[lang]["entity"]["sensor"][role]["name"]) for lang in ("en", "nl", "fr")]
        assert names == expected, role


def test_registered_element_editor_and_picker(out):
    assert out["defined"] == ["daikin-daily-summary-card", "daikin-daily-summary-card-editor"]
    assert [c["type"] for c in out["picker"]] == ["daikin-daily-summary-card"]
    assert out["picker"][0]["preview"] is True


@pytest.mark.parametrize("case", ["en", "nl", "fr", "nl_no_registry", "fr_no_registry"])
def test_entities_found_in_every_language(out, case):
    r = out["cases"][case]
    assert r["ok"] is True
    assert all(r["ids"].values()), r["ids"]
    assert r["days"] == 3


def test_language_follows_ha_and_override(out):
    assert [out["cases"][x]["lang"] for x in ("en", "nl", "fr")] == ["en", "nl", "fr"]
    assert out["cases"]["lang_override"]["lang"] == "fr"
    assert "Aujourd'hui" in _text(out["cases"]["lang_override"]["html"]["today"]).replace("&#39;", "'")


def test_device_filter_and_not_found(out):
    for case in ("other_device", "empty"):
        r = out["cases"][case]
        assert r["ok"] is False
        assert "entities not found" in r["html"]["today"]


@pytest.mark.parametrize(
    "lang,words",
    [
        ("en", ["Today", "Overview", "Running", "Heating", "Today's alerts", "Show all (8)"]),
        ("nl", ["Vandaag", "Overzicht", "In bedrijf", "Verwarming", "Meldingen vandaag", "Alles tonen (8)"]),
        ("fr", ["Aujourd'hui", "Synthèse", "En marche", "Chauffage", "Alertes du jour", "Tout afficher (8)"]),
    ],
)
def test_today_tab_localized(out, lang, words):
    text = _text(out["cases"][lang]["html"]["today"]).replace("&#39;", "'")
    for w in words:
        assert w in text, (lang, w)
    # three alerts until "show all"
    assert out["cases"][lang]["html"]["today"].count('class="alert"') == 3


@pytest.mark.parametrize("lang", ["en", "nl", "fr"])
def test_every_tab_renders_without_gaps(out, lang):
    for tab, html in out["cases"][lang]["html"].items():
        assert "undefined" not in html and "NaN" not in html, (lang, tab)
        assert "EPRA12EAV3" in html  # model in the header
        assert 'aria-selected="true"' in html


def test_charts_and_day_targets(out):
    html = out["cases"]["en"]["html"]
    for tab in ("quality", "cycles", "duration", "events"):
        assert "<svg" in html[tab]
        assert html[tab].count('data-day="2026-11-1') >= 3, tab
    assert "Tap a day for details" in html["cycles"]


def test_436_quality_and_runs(out):
    r = out["cases"]["i436"]
    assert round(r["stats"]["quality"]) == 84  # average of all 18 cycles
    assert [q for _, q, _, _ in r["dayq"]] == [93, 80, 81, 89]
    assert r["stats"]["worst"] == "2026-11-17" and r["stats"]["best"] == "2026-11-16"
    assert "84" in _text(r["html"]["overview"])


def test_alert_text_is_escaped(out):
    html = out["cases"]["xss"]["html"]["today"]
    assert "<script>" not in html and "<img" not in html and "<b>boom" not in html
    assert "&lt;script&gt;bad()&lt;/script&gt;" in html
    assert "━" not in html  # separator lines dropped


def test_first_run_note(out):
    assert "The first cycle is still running" in out["cases"]["first_run"]["html"]["today"]
    assert "The first cycle is still running" not in out["cases"]["en"]["html"]["today"]


def test_card_version_matches_changelog(out):
    log = (ROOT / "dashboard/cards/daikin-daily-summary-card/CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{out['version']}]" in log


# ---------- Chromium: the real custom element ----------

BROWSER = r"""
const { chromium } = require('playwright'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 420, height: 900 } });
  const errors = []; p.on('pageerror', (e) => errors.push(e.message));
  await p.setContent('<html><body><div id="c"></div></body></html>');
  await p.addScriptTag({ content: "customElements.define('ha-card', class extends HTMLElement {});"
    + "customElements.define('ha-form', class extends HTMLElement { set data(v){ this._d = v; } get data(){ return this._d; } });" });
  await p.addScriptTag({ content: fs.readFileSync(D.card, 'utf8') });
  const res = await p.evaluate(async (s) => {
    const out = {};
    const el = document.createElement('daikin-daily-summary-card');
    try { el.setConfig({ default_tab: 'nope' }); out.badTab = 'no error'; } catch (e) { out.badTab = e.message; }
    el.setConfig({ window: 7 });
    document.getElementById('c').appendChild(el);
    el.hass = { states: s.states, entities: s.entities, language: 'en', locale: { language: 'en' } };
    const R = () => el.shadowRoot;
    const sel = () => R().querySelector('.tab.on').dataset.tab;
    out.first = sel();
    R().querySelector('[data-tab="cycles"]').click(); out.afterClick = sel();
    R().querySelector('[data-win="15"]').click(); out.win = R().querySelector('.win.on').dataset.win;
    const hits = R().querySelectorAll('.hit'); hits[hits.length - 1].dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
    out.detail = !!R().querySelector('.detail');
    R().querySelector('[data-act="close"]').click(); out.closed = !R().querySelector('.detail');
    R().querySelector('[data-tab="overview"]').click();
    R().querySelector('.bw').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, composed: true }));
    out.bwTab = sel(); out.bwDetail = !!R().querySelector('.detail');
    R().querySelector('[data-tab="today"]').click();
    R().querySelector('.alert').click(); out.alertOpen = !!R().querySelector('.msg');
    R().querySelector('[data-act="more"]').click(); out.alerts = R().querySelectorAll('.alert').length;
    const before = R().getElementById('root').innerHTML;
    el.hass = Object.assign({}, el.hass);  /* same states -> no re-render */
    out.stable = R().getElementById('root').innerHTML === before;
    out.cardSize = el.getCardSize(); out.grid = el.getGridOptions();
    out.stub = customElements.get('daikin-daily-summary-card').getStubConfig();
    const ed = customElements.get('daikin-daily-summary-card').getConfigElement();
    document.body.appendChild(ed);
    let changed = null; ed.addEventListener('config-changed', (e) => { changed = e.detail.config; });
    ed.setConfig({ window: 15 }); ed.hass = el.hass;
    const form = ed.querySelector('ha-form');
    out.schema = form.schema.map((x) => x.name); out.formWin = form.data.window;
    form.dispatchEvent(new CustomEvent('value-changed', { detail: { value: { window: '30', title: '', tabs: [], default_tab: 'quality' } } }));
    out.changed = changed;
    return out;
  }, D.states);
  res.errors = errors;
  process.stdout.write(JSON.stringify(res)); await b.close();
})().catch((e) => { process.stderr.write(String(e)); process.exit(1); });
"""


def _playwright() -> bool:
    proc = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, check=False)
    return proc.returncode == 0


@pytest.mark.skipif(not _playwright(), reason="playwright (node) not installed")
def test_card_in_chromium():
    proc = subprocess.run(
        ["node", "-e", BROWSER], capture_output=True, text=True, timeout=180, check=False,
        input=json.dumps({"card": str(CARD), "states": _fixture("en")}),
    )
    assert proc.returncode == 0, proc.stderr
    r = json.loads(proc.stdout)
    assert r["errors"] == []
    assert "default_tab must be one of" in r["badTab"]
    assert r["first"] == "today" and r["afterClick"] == "cycles" and r["win"] == "15"
    assert r["detail"] is True and r["closed"] is True
    assert r["bwTab"] == "quality" and r["bwDetail"] is True
    assert r["alertOpen"] is True and r["alerts"] == 8
    assert r["stable"] is True
    assert r["cardSize"] == 9 and r["grid"]["columns"] == 12
    assert r["stub"] == {"default_tab": "today", "window": 7}
    assert r["schema"] == ["device_id", "title", "default_tab", "window", "tabs", "language", "show_help"]
    assert r["formWin"] == "15"
    assert r["changed"] == {"window": 30, "default_tab": "quality"}
