"""#508: native card custom:daikin-reports-card.

The reports come from production code: day sources -> report_builder ->
report_query.get_report (the service response), and the card states from
the real-integration fixture (R397) plus the last_month_report sensor
computed by the coordinator. Node renders every tab in EN / NL / FR;
Chromium mounts the element (service call, period stepping, drop-downs,
tabs, phone width, editor) and writes screenshots to look at (R402).
"""
from __future__ import annotations

import asyncio
import html as _html
import datetime as dt
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.storage import report_builder as rb
from custom_components.daikin_cycle_ml.storage import report_query as rq
from custom_components.daikin_cycle_ml.storage.db import CycleDB
from tests.test_efficiency_native_card import _case
from tests.test_efficiency_native_card import _text as _raw_text
from tests.test_native_cards_responsive import _playwright

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "custom_components/daikin_cycle_ml/frontend"
FILES = ["daikin-reports-card.js", "dcm-reports-render.js", "dcm-reports-i18n.js", "dcm-reports-model.js"]
SHOTS = Path(tempfile.gettempdir()) / "dcm-reports-shots"
SENSOR_ID = {"en": "last_month_report", "nl": "rapport_vorige_maand", "fr": "rapport_du_mois_dernier"}
TABS = ["overview", "energy", "temps", "cycling", "events", "compare"]

pytestmark = [pytest.mark.skipif(not shutil.which("node"), reason="node not installed"),
              pytest.mark.usefixtures("at_noon")]


def _text(h: str) -> str:
    return _html.unescape(_raw_text(h))


def _day(n: int) -> str:
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


async def _reports(tmp: Path) -> dict:
    """Responses of get_report and the last-month summary, from a DB with
    120 days of heating + hot water history (a colder second half)."""
    db = CycleDB(str(tmp / "card508.db"))
    await db.async_open()
    await db.async_initialize()
    try:
        for n in range(1, 121):
            day = _day(n)
            t_out = 1.0 + (n % 30) * 0.3 if n <= 60 else 6.0 + (n % 30) * 0.2
            el = 12.0 - t_out * 0.6
            await db.async_set_model_state(f"energy_acc.{day}", {
                "day": day, "heating_el_kwh": el, "heating_th_kwh": el * (3.4 + t_out * 0.08),
                "dhw_el_kwh": 1.5, "dhw_th_kwh": 4.2})
            await db.async_set_model_state(f"runtime_acc.{day}", {
                "day": day, "outdoor_sum": t_out * 86400, "outdoor_s": 86400.0, "outdoor_min": t_out - 4,
                "outdoor_max": t_out + 4, "source_fresh_s": 86400.0 if n != 12 else 30000.0,
                "buh_total_s": 600.0 if n % 9 == 0 else 0.0, "defrost_count": 3 if t_out < 3 else 0,
                "defrost_duration_s": 900.0 if t_out < 3 else 0.0})
            # two runs a day (hot water every third day) as the coordinator writes them
            for h, mode, mins in ((6, "heating", 150 - n % 40), (14, "heating", 90 + n % 30), (20, "dhw", 35)):
                if mode == "dhw" and n % 3:
                    continue
                start = time.mktime(time.strptime(f"{day} {h:02d}", "%Y-%m-%d %H"))
                await db._require().execute(
                    "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, is_transient, quality_score, dT_max, "
                    "rps_avg, buh_used, defrost_used) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (start, start + mins * 60, mins * 60, mode, 0, 70 + n % 25, 5.0, 38.0 + n % 10, 0, int(t_out < 3)))
            await db._require().commit()
            await db.async_rollup_day(day)
            await db.async_insert_alert("short_cycling", "warning", "x",
                                        ts=time.mktime(time.strptime(day + " 09", "%Y-%m-%d %H")))
        await rb.build_reports(db, today=_day(0), full=True)
        conn = db._require()
        months = await rq.available_keys(conn, "month")
        out = {
            "month": await rq.get_report(conn, period_type="month", key=months[1], include_days=True, scheme="be1515"),
            "week": await rq.get_report(conn, period_type="week", include_days=True, scheme="be1515"),
            "heating_ly": await rq.get_report(conn, period_type="month", key=months[1], mode="heating",
                                              against="last_year", include_days=True, scheme="be1515"),
            "missing": await rq.get_report(conn, period_type="year", key="1999", scheme="be1515"),
            "empty": {"period_type": "season", "key": None, "available": [], "found": False},
        }
        c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
        c.db, c.options, c.hass = db, {}, SimpleNamespace(config=SimpleNamespace(country="BE"))
        await c.async_refresh_report_summary()
        out["summary"] = c.last_month_report
        return json.loads(json.dumps(out))
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.fixture(scope="module")
def reports(tmp_path_factory):
    loop = asyncio.new_event_loop()        # leaves the test loop of pytest-asyncio alone
    try:
        return loop.run_until_complete(_reports(tmp_path_factory.mktemp("r508")))
    finally:
        loop.close()


def _card_case(lang: str, summary: dict) -> dict:
    c = _case(lang)
    hp = next(k for k, v in c["entities"].items() if v["translation_key"] == "hp_specs")
    eid = hp.split("_hp_specs")[0].split("_wp_specs")[0].split("_caracteristiques")[0] + "_" + SENSOR_ID[lang]
    c["entities"] = {k: dict(v, device_id="dev1") for k, v in c["entities"].items()}
    c["entities"][eid] = {"platform": "daikin_cycle_ml", "translation_key": "last_month_report", "device_id": "dev1"}
    c["states"][eid] = {"entity_id": eid, "state": str(summary["cop"]), "attributes": summary,
                        "last_updated": "2026-11-28T03:05:00+00:00"}
    c["devices"] = {"dev1": {"config_entries": ["entry_9"]}}
    c["sensor"] = eid
    return c


RUNNER = r"""
const vm = require('vm'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
const win = {};
const ctx = vm.createContext({ window: win, Intl, Date, Math, JSON, Object, Array, String, Number, Set, isFinite, parseFloat,
  RegExp, Error, console: { info() {} }, HTMLElement: class {}, CustomEvent: class {}, document: {},
  setInterval: () => 0, clearInterval: () => 0,
  customElements: { _d: {}, get(n) { return this._d[n]; }, define(n, c) { this._d[n] = c; } } });
const defined = [];
for (const f of D.files) { vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f }); defined.push(Object.keys(ctx.customElements._d).length); }
const P = win.DaikinReportsCardParts, M = P.model;
const out = { defined, tags: Object.keys(ctx.customElements._d), picker: win.customCards, version: win.DaikinReportsCard.version,
  i18n: P.i18n, cases: {} };
for (const [name, c] of Object.entries(D.cases)) {
  const hass = { states: c.states, entities: c.entities, devices: c.devices, language: c.lang, locale: { language: c.lang } };
  const res = {};
  for (const tab of D.tabs) {
    const ui = Object.assign({ tab }, c.ui || {});
    const m = M.buildModel(hass, c.config || {}, ui, c.resp);
    res[tab] = P.render.render(m, c.config || {});
    if (tab === 'overview') res.model = { lang: m.lang, ok: m.ok, entry: m.entryId, label: m.label, overall: m.overall,
      prevKey: m.prevKey, nextKey: m.nextKey, refFound: m.refFound, partial: m.partial, tiles: m.tiles, request: M.request(m.entryId, c.config || {}, ui) };
  }
  out.cases[name] = res;
}
out.labels = [M.periodLabel('week', '2026-W05', 'nl', P.i18n.nl), M.periodLabel('month', '2026-11', 'fr', P.i18n.fr),
  M.periodLabel('season', '2026/27', 'en', P.i18n.en), M.periodLabel('month', null, 'en', P.i18n.en)];
out.step = [M.step(['c', 'b', 'a'], 'b', -1), M.step(['c', 'b', 'a'], 'b', 1), M.step(['c', 'b', 'a'], 'a', -1), M.step([], 'x', 1)];
out.ui = [M.uiState({ period_type: 'year', mode: 'dhw', compare: 'none', default_tab: 'events' }, {}),
  M.uiState({ period_type: 'decade' }, { tab: 'nope' })];
out.esc = P.render.render(M.buildModel({ states: {}, entities: {} }, {}, {}, null), { title: '<script>x</script>' });
process.stdout.write(JSON.stringify(out));
"""


def _run(cases: dict, files=None) -> dict:
    proc = subprocess.run(["node", "-e", RUNNER], capture_output=True, text=True, timeout=120, check=False,
                          input=json.dumps({"files": [str(FRONT / f) for f in (files or FILES)], "cases": cases, "tabs": TABS}))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_reports_card_under_node(reports):
    cases = {}
    for lang in ("en", "nl", "fr"):
        cases[lang] = {**_card_case(lang, reports["summary"]), "resp": reports["month"]}
    cases["week"] = {**_card_case("en", reports["summary"]), "resp": reports["week"], "ui": {"type": "week"}}
    cases["heating_ly"] = {**_card_case("nl", reports["summary"]), "resp": reports["heating_ly"],
                           "ui": {"mode": "heating", "against": "last_year"}}
    cases["missing"] = {**_card_case("en", reports["summary"]), "resp": reports["missing"]}
    cases["empty"] = {**_card_case("en", reports["summary"]), "resp": reports["empty"]}
    cases["loading"] = {**_card_case("en", reports["summary"]), "resp": None}
    cases["error"] = {**_card_case("fr", reports["summary"]), "resp": None, "ui": {"error": "boom"}}
    cases["no_entity"] = {**_case("en"), "entities": {}, "resp": None}
    cases["title"] = {**_card_case("en", reports["summary"]), "resp": reports["month"], "config": {"title": "My <b>"}}
    out = _run(cases)

    assert out["tags"] == ["daikin-reports-card", "daikin-reports-card-editor"]
    assert out["defined"][-1] == 2 and out["defined"][0] == 0          # defined once every part is loaded
    assert out["picker"][0]["type"] == "daikin-reports-card"
    assert set(out["i18n"]) == {"en", "nl", "fr"}

    def keys(d, pre=""):
        return {pre + k for k, v in d.items() for _ in [0]} | {x for k, v in d.items() if isinstance(v, dict)
                                                                 for x in keys(v, pre + k + ".")}
    assert keys(out["i18n"]["en"]) == keys(out["i18n"]["nl"]) == keys(out["i18n"]["fr"])

    month = reports["month"]
    for lang in ("en", "nl", "fr"):
        c = out["cases"][lang]
        mdl = c["model"]
        assert mdl["ok"] and mdl["lang"] == lang and mdl["entry"] == "entry_9"
        assert mdl["refFound"] and mdl["overall"] in ("good", "watch", "act", "incomplete")
        assert mdl["request"] == {"period_type": "month", "mode": "all", "compare": "previous", "history": 12,
                                  "include_days": True, "entry_id": "entry_9"}
        assert mdl["prevKey"] == month["available"][2] and mdl["nextKey"] == month["available"][0]
        T = out["i18n"][lang]
        for tab in TABS:
            html = c[tab]
            assert T["tabs"][tab] in _text(html), (lang, tab)
            assert "EPRA12EAV3" in html and "undefined" not in html and "NaN" not in html, (lang, tab)
            assert re.search(r'aria-selected="true"[^>]*data-tab="' + tab + '"|data-tab="' + tab + '"[^>]*aria-selected="true"', html)
        assert "<svg" in c["energy"] and "<svg" in c["temps"] and "<svg" in c["cycling"]
        assert T["by_mode"] in _text(c["energy"]) and T["modes"]["dhw"] in _text(c["energy"])
        assert "short_cycling" in c["events"]
        assert T["m"]["el_per_dd"] in _text(c["compare"])
        assert T["verdict"][mdl["overall"]] in _text(c["overview"])
    assert "November" in out["cases"]["en"]["model"]["label"] or re.match(r"[A-Z][a-z]+ \d{4}", out["cases"]["en"]["model"]["label"])
    week = out["cases"]["week"]
    assert week["model"]["label"].startswith("Week ") and "Still running" in _text(week["overview"])
    ly = out["cases"]["heating_ly"]
    assert ly["model"]["refFound"] is False and ly["model"]["overall"] is None
    assert "Niets opgeslagen" in _text(ly["overview"]) and "Per modus" not in _text(ly["energy"])
    assert "No report for this period." in _text(out["cases"]["missing"]["overview"])
    assert "No report yet" in _text(out["cases"]["empty"]["overview"])
    assert "Loading the report" in _text(out["cases"]["loading"]["overview"])
    assert "boom" in _text(out["cases"]["error"]["overview"])
    assert "not found" in _text(out["cases"]["no_entity"]["overview"])
    assert "My &lt;b&gt;" in out["cases"]["title"]["overview"] and "&lt;script&gt;" in out["esc"]
    assert out["labels"] == ["Week 5 · 2026", "Novembre 2026", "2026/27", ""]
    assert out["step"] == ["a", "c", None, None]
    assert out["ui"][0] == {"type": "year", "mode": "dhw", "against": "none", "tab": "events", "key": None}
    assert out["ui"][1] == {"type": "month", "mode": "all", "against": "previous", "tab": "overview", "key": None}


def test_partial_period_shows_no_verdict(reports):
    resp = json.loads(json.dumps(reports["month"]))
    resp["compare"]["partial"] = True
    resp["compare"]["verdicts"] = {k: "incomplete" for k in resp["compare"]["verdicts"]}
    out = _run({"p": {**_card_case("en", reports["summary"]), "resp": resp}})
    html = out["cases"]["p"]["overview"]
    assert "the comparison is shown but not judged" in _text(html) and "Incomplete" in _text(html)


BROWSER = r"""
const { chromium } = require('playwright'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const b = await chromium.launch(); const out = {};
  for (const [name, w, dark] of [['phone', 390, false], ['desktop', 900, true]]) {
    const p = await b.newPage({ viewport: { width: w, height: 1400 }, deviceScaleFactor: 1, colorScheme: dark ? 'dark' : 'light' });
    const errors = []; p.on('pageerror', (e) => errors.push(e.message));
    const css = dark ? ':root{--card-background-color:#1c1c1c;--primary-text-color:#e1e1e1;--secondary-text-color:#9b9b9b;--secondary-background-color:#282828;--divider-color:#3a3a3a}body{background:#111}'
      : ':root{--card-background-color:#fff;--primary-text-color:#212121;--secondary-text-color:#727272;--secondary-background-color:#f3f3f3;--divider-color:#e0e0e0}body{background:#fafafa}';
    await p.setContent(`<html><head><style>${css}</style></head><body style="margin:0;padding:8px"><div id="c"></div></body></html>`);
    await p.addScriptTag({ content: "customElements.define('ha-card', class extends HTMLElement { connectedCallback(){ this.style.display='block'; this.style.background='var(--card-background-color)'; this.style.borderRadius='12px'; } });"
      + "customElements.define('ha-form', class extends HTMLElement {});" });
    for (const f of D.files) await p.addScriptTag({ content: fs.readFileSync(f, 'utf8') });
    out[name] = await p.evaluate(async (D) => {
      const wait = (ms) => new Promise((r) => setTimeout(r, ms));
      const calls = [];
      const c = D.case;
      const el = document.createElement('daikin-reports-card'); el.setConfig({});
      document.getElementById('c').appendChild(el);
      el.hass = { states: c.states, entities: c.entities, devices: c.devices, language: D.lang, locale: { language: D.lang },
        callWS: async (msg) => { calls.push(msg); const sd = msg.service_data;
          const r = D.responses[sd.period_type + ':' + (sd.period || 'newest')] || D.responses[sd.period_type + ':newest'];
          return { response: Object.assign({}, r, { mode: sd.mode }) }; }, callService: async () => {} };
      await wait(200);
      const R = el.shadowRoot, q = (s) => R.querySelector(s);
      const res = { calls: [], tabs: {}, overflow: {} };
      const fits = () => document.documentElement.scrollWidth <= window.innerWidth + 1;
      res.first = calls[0];
      res.label = q('.hs').textContent;
      res.selKey = q('select[data-ctl="key"]').value;
      q('[data-act="prev"]').click(); await wait(200);
      res.afterPrev = calls[calls.length - 1].service_data.period;
      res.labelPrev = q('.hs').textContent;
      for (const t of D.tabs) { q(`[data-tab="${t}"]`).click(); await wait(30); res.tabs[t] = q('.panel').textContent.length; res.overflow[t] = fits(); }
      const sel = q('select[data-ctl="type"]'); sel.value = 'week'; sel.dispatchEvent(new Event('change', { bubbles: true })); await wait(200);
      res.afterType = calls[calls.length - 1].service_data;
      const md = q('select[data-ctl="mode"]'); md.value = 'heating'; md.dispatchEvent(new Event('change', { bubbles: true })); await wait(200);
      res.afterMode = calls[calls.length - 1].service_data.mode;
      res.n = calls.length;
      el.hass = Object.assign({}, el.hass); await wait(100);
      res.nAfterSameHass = calls.length;
      const ed = document.createElement('daikin-reports-card-editor'); ed.hass = el.hass; ed.setConfig({ mode: 'dhw' });
      res.editor = ed.querySelector('ha-form').schema.map((s) => s.name);
      return res;
    }, { case: D.case, responses: D.responses, lang: D.lang, tabs: D.tabs });
    out[name].errors = errors;
    for (const t of ['overview', 'energy', 'compare']) {
      await p.evaluate((t) => { const R = document.querySelector('daikin-reports-card').shadowRoot;
        R.querySelector(`[data-tab="${t}"]`).click(); }, t);
      await p.waitForTimeout(60);
      await p.screenshot({ path: `${D.shots}/${name}-${t}.png`, fullPage: true });
    }
    await p.close();
  }
  await b.close();
  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(not _playwright(), reason="playwright (node) not installed")
def test_reports_card_in_chromium(reports):
    SHOTS.mkdir(exist_ok=True)
    month = reports["month"]
    prev_key = month["available"][2]
    responses = {"month:newest": month, f"month:{month['key']}": month,
                 f"month:{prev_key}": {**month, "key": prev_key}, "week:newest": reports["week"]}
    data = {"files": [str(FRONT / f) for f in FILES], "case": _card_case("en", reports["summary"]),
            "responses": responses, "lang": "en", "tabs": TABS, "shots": str(SHOTS)}
    proc = subprocess.run(["node", "-e", BROWSER], capture_output=True, text=True, timeout=180, check=False,
                          input=json.dumps(data))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    for name, r in out.items():
        assert r["errors"] == [], (name, r["errors"])
        assert r["first"]["type"] == "call_service" and r["first"]["service"] == "get_report"
        assert r["first"]["return_response"] is True and r["first"]["service_data"]["entry_id"] == "entry_9"
        assert "period" not in r["first"]["service_data"]           # the newest first
        assert r["afterPrev"] == prev_key
        assert r["label"] != r["labelPrev"]
        assert r["selKey"] == month["key"]                     # the drop-down shows the period shown
        assert all(v > 20 for v in r["tabs"].values()), r["tabs"]
        assert all(r["overflow"].values()), (name, r["overflow"])       # no horizontal scroll
        assert r["afterType"]["period_type"] == "week" and "period" not in r["afterType"]
        assert r["afterMode"] == "heating"
        assert r["nAfterSameHass"] == r["n"]                            # same state: no new call
        assert r["editor"] == ["device_id", "title", "period_type", "mode", "compare", "default_tab", "language"]
    assert (SHOTS / "phone-overview.png").exists() and (SHOTS / "desktop-compare.png").exists()
