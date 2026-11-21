"""Native Lovelace card ``custom:daikin-efficiency-card``.

Node (vm, no browser) loads the seven card files in a shuffled order and
runs the pure parts on the states and the 24 h history of the real
integration (tests/fixtures/card_states_427.json + card_history_24h.json,
en / nl / fr), then on scenarios that push every graph into good / watch /
bad. Chromium (Playwright, skipped when absent) mounts the element: the
history websocket call, tabs, range, advanced, help, curve points and the
visual editor.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

from tests.test_427_cards_live_states import FIXTURE, HISTORY_FIXTURE, _localized

ROOT = Path(__file__).resolve().parent.parent
COMP = ROOT / "custom_components/daikin_cycle_ml"
FRONT = COMP / "frontend"
PARTS = ["dcm-efficiency-data.js", "dcm-efficiency-assess.js", "dcm-efficiency-charts.js",
         "dcm-efficiency-verdicts.js", "dcm-efficiency-i18n.js", "dcm-efficiency-render.js"]
MAIN = "daikin-efficiency-card.js"
# main file first, parts in reverse: the element waits for every part
ORDER = [MAIN] + PARTS[::-1]

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")

RUNNER = r"""
const vm = require('vm'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
const win = {};
const ctx = vm.createContext({ window: win, Intl, Date, Math, JSON, Object, Array, String, Number,
  parseFloat, isFinite, RegExp, Error, console: { info() {}, log() {}, warn() {}, debug() {} },
  HTMLElement: class {}, CustomEvent: class {}, document: {},
  customElements: { _d: {}, get(n) { return this._d[n]; }, define(n, c) { this._d[n] = c; } },
  setInterval: () => 0, clearInterval: () => 0 });
const defined = [];
for (const f of D.files) {
  vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
  defined.push(Object.keys(ctx.customElements._d).length);
}
const P = win.DaikinEfficiencyCardParts;
const out = { defined, tags: Object.keys(ctx.customElements._d), picker: win.customCards,
  version: win.DaikinEfficiencyCard.version, suffix: P.data.SUFFIX, binary: P.data.BINARY,
  i18n: P.i18n, verdicts: P.verdicts, limits: P.assess.LIMITS, tabs: P.render.TABS, cases: {}, unit: {} };
for (const [name, c] of Object.entries(D.cases)) {
  const hass = { states: c.states, entities: c.entities, language: c.lang, locale: { language: c.lang } };
  const ids = P.data.resolveEntities(hass, c.config || {});
  const buf = P.data.parseHistory(c.history || {}, ids);
  const now = Date.parse(c.now) / 1000;
  const m = P.data.buildModel(hass, c.config || {}, buf, now, c.range || '3h'); m.buf = buf;
  const a = P.assess.assess(m);
  const r = { ids, lang: m.lang, ok: m.ok, samples: buf.samples.length, live: m.live, fit: m.curve.fit, html: {}, v: {} };
  for (const k of Object.keys(a)) if (a[k] && a[k].lvl && k !== 'overall') r.v[k] = [a[k].lvl, a[k].k];
  r.overall = a.overall.lvl;
  for (const tab of P.render.TABS) {
    r.html[tab] = P.render.render(m, a, c.config || {}, Object.assign({ tab, range: '3h', adv: true, help: true, bucket: '2-4' }, c.ui || {}));
  }
  out.cases[name] = r;
}
const U = out.unit, d = P.data;
const pts = [{ t_out: 7, t_lwc: 35, cop: 4.92 }, { t_out: 2, t_lwc: 35, cop: 4.08 }, { t_out: -7, t_lwc: 35, cop: 3.04 },
  { t_out: 7, t_lwc: 55, cop: 2.94 }, { t_out: -7, t_lwc: 55, cop: 2.05 }];
U.ds = [d.datasheetCop(pts, 7, 35), d.datasheetCop(pts, -7, 55), d.datasheetCop(pts, 4.5, 35),
  d.datasheetCop(pts, 7, 45), d.datasheetCop([], 7, 35), d.datasheetCop(pts, null, 35),
  /* only A7 points (ERGA06): 3 °C outdoor scales A7 with the Carnot ratio */
  d.datasheetCop([{ t_out: 7, t_lwc: 35, cop: 4.85 }], 3, 35), d.carnot(35, 3) / d.carnot(35, 7),
  /* beyond the warmest point (prod-1 at 8.2 °C) */
  d.datasheetCop(pts, 8.2, 35), d.carnot(35, 8.2) / d.carnot(35, 7)];
U.fit = d.fitCurve([{ x: -10, y: 45, n: 1 }, { x: 0, y: 40, n: 3 }, { x: 10, y: 35, n: 2 }]);
U.fitNone = d.fitCurve([{ x: 1, y: 30, n: 5 }]);
U.buckets = d.bucketPoints({ '-4--2': { lwt: 36, cop: 4, n: 3 }, '-10-': { lwt: 40, n: 1 }, '20+': { lwt: 25, n: 1 }, '0-2': { lwt: 34 }, 'x': { lwt: 1 }, '2-4': {} });
const hb = { samples: [{ t: 1000, lwt: 30, kw: 5 }, { t: 1900, lwt: 36, kw: 5 }, { t: 2100, lwt: 99, kw: 0 }], spans: {} };
U.mean10 = d.mean10(hb, 2200, 'lwt');
U.carry = d.windowed(hb, 2200, '10m').samples.map((s) => [s.t, s.lwt]);
U.spans = d.toSpans([{ t: 10, on: true }, { t: 20, on: false }, { t: 30, on: true }], 50);
U.parsed = d.parseHistory({ 'sensor.a': [{ s: '5', a: { lwt_c: 33, input_cop: 5 }, lu: 100 }, { s: '6', lu: 160 }],
  'binary_sensor.b': [{ s: 'on', lu: 120 }, { s: 'off', lu: 130 }] }, { thermal_power_live: 'sensor.a', defrost_active: 'binary_sensor.b' });
const lb = { samples: [], spans: {} };
const lh = { states: { 'sensor.x_thermal_power_live': { state: '4', last_updated: '2026-11-19T13:00:00Z', attributes: { lwt_c: 31 } },
  'binary_sensor.x_compressor_running': { state: 'on', last_changed: '2026-11-19T12:00:00Z' } } };
const lids = { thermal_power_live: 'sensor.x_thermal_power_live', compressor_running: 'binary_sensor.x_compressor_running' };
U.append = [d.appendLive(lb, lh, lids, 1795093200), d.appendLive(lb, lh, lids, 1795093200), lb.samples.length, lb.spans.compressor_running.length];
U.carnot = [d.carnot(35, 7), d.carnot(null, 7)];
const f = P.render.makeFmt('nl');
U.fill = [f.fill('{a} · {b} · {c} · {d} · {e}', { a: 5.3, b: 4.92, c: 34, d: null, e: 'x' }), f.fill('{pct} %', { pct: 7 }, true), f.fill('{pct} %', { pct: -7 }, true)];
U.esc = P.render.render({ ok: false, lang: 'en', model: '<i>m</i>' }, {}, { title: '<script>x</script>' }, { tab: 'live' });
process.stdout.write(JSON.stringify(out));
"""


def _run(cases: dict) -> dict:
    proc = subprocess.run(
        ["node", "-e", RUNNER], capture_output=True, text=True, timeout=120, check=False,
        input=json.dumps({"files": [str(FRONT / f) for f in ORDER], "cases": cases}),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _case(lang: str = "en", **attrs) -> dict:
    """Localized fixture + history (entity ids as HA creates them in ``lang``)."""
    dump = json.loads(FIXTURE.read_text(encoding="utf-8"))
    loc = _localized(dump, lang)
    en = _localized(dump, "en")
    key_to_id = {v["translation_key"]: k for k, v in loc["entities"].items()}
    hist = {}
    for eid, rows in json.loads(HISTORY_FIXTURE.read_text(encoding="utf-8")).items():
        hist[key_to_id[en["entities"][eid]["translation_key"]]] = rows
    return {"states": loc["states"], "entities": loc["entities"], "lang": lang, "now": loc["now"], "history": hist, **attrs}


def _set(case: dict, key: str, state=None, **attrs) -> dict:
    eid = next(k for k, v in case["entities"].items() if v["translation_key"] == key)
    st = json.loads(json.dumps(case["states"][eid]))
    if state is not None:
        st["state"] = state
    st["attributes"].update(attrs)
    case["states"][eid] = st
    return case


def _scenarios() -> dict:
    c = {lang: _case(lang) for lang in ("en", "nl", "fr")}
    c["no_registry"] = {**_case("nl"), "entities": {}}
    c["none"] = {**_case(), "states": {}, "entities": {}}
    c["far_above"] = _set({**_case(), "history": {}}, "thermal_power_live", lwt_c=37.5)
    c["below"] = _set({**_case(), "history": {}}, "thermal_power_live", lwt_c=32.4)
    c["dhw"] = _set(_case(), "dhw_active", "on")
    c["defrost"] = _set(_case(), "defrost_active", "on")
    warm = _set(_case(), "compressor_running", "off")
    c["off_warm"] = _set(_set(warm, "current_cycle", "idle"), "thermal_power_live", "0.0", outdoor_c=22)
    c["dt_high"] = _set({**_case(), "history": {}}, "thermal_power_live", input_dt_k=9.5)
    c["min_flow"] = {**_case(), "config": {"min_flow": 20}}
    c["no_flow"] = _set(_case(), "thermal_power_live", input_flow_lmin=0)
    c["short"] = _set(_case(), "compressor_starts_today", starts_last_hour=5)
    c["room_cold"] = _set(_case(), "thermal_power_live", room_c=19.0)
    c["room_warm"] = _set(_case(), "thermal_power_live", room_c=21.8)
    c["no_room"] = _set(_case(), "thermal_power_live", room_c=None)
    c["cop_low"] = _set({**_case(), "history": {}}, "thermal_power_live", input_cop=3.0)
    c["cop_suspect"] = _set({**_case(), "history": {}}, "thermal_power_live", input_cop=7.0)
    c["imbalance"] = _set({**_case(), "history": {}}, "thermal_power_live", input_power_w=1500)
    c["lower"] = _set(_case(), "heating_curve_advice", "lower_lwt", step_c=2, doel_setpoint=32.0, besparing_cop_pct=4.0, reason="")
    c["adv_dhw"] = _set(_case(), "heating_curve_advice", suppressed_by="dhw_active")
    c["curve_ok"] = _set(_case(), "heating_curve_advice", buckets={
        "-4--2": {"lwt": 40.0, "cop": 3.2, "n": 50}, "0-2": {"lwt": 37.5, "cop": 3.9, "n": 80},
        "4-6": {"lwt": 34.5, "cop": 4.6, "n": 90}, "8-10": {"lwt": 32.0, "cop": 5.4, "n": 40}})
    c["curve_buh"] = _set(_case(), "heating_curve_advice", buckets={
        "-2-0": {"lwt": 50.0, "cop": 2.6, "n": 50}, "4-6": {"lwt": 44.0, "cop": 3.4, "n": 50}})
    c["spf_low"] = _set(_case(), "spf_season", "3.1")
    c["sheet_low"] = _set(_case(), "cop_vs_datasheet_pct", "-31", band="critical")
    c["degr"] = _set(_case(), "cop_degradation_status", "warning", week_pct=-9.0)
    c["defrost_bad"] = _set(_set(_case(), "runtime_buh_today", "0"), "defrost_duration_today", "12000")
    c["defrost_watch"] = _set(_set(_case(), "runtime_buh_today", "0"), "defrost_duration_today", "6000")
    return c


@pytest.fixture(scope="module")
def out() -> dict:
    return _run(_scenarios())


def test_parts_load_in_any_order_and_register(out):
    # nothing is defined until the last part arrives
    assert out["defined"] == [0, 0, 0, 0, 0, 0, 2]
    assert out["tags"] == ["daikin-efficiency-card", "daikin-efficiency-card-editor"]
    assert [c["type"] for c in out["picker"]] == ["daikin-efficiency-card"]


def test_card_files_stay_small():
    for f in PARTS + [MAIN]:
        assert len((FRONT / f).read_text(encoding="utf-8").splitlines()) < 500, f


def test_suffix_table_matches_translations(out):
    def slug(s: str) -> str:
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    tr = {lang: json.loads((COMP / f"translations/{lang}.json").read_text(encoding="utf-8"))["entity"]
          for lang in ("en", "nl", "fr")}
    for role, names in out["suffix"].items():
        plat = "binary_sensor" if role in out["binary"] else "sensor"
        expected = []
        for lang in ("en", "nl", "fr"):
            s = slug(tr[lang][plat][role]["name"])
            if s not in expected:
                expected.append(s)
        assert names == expected, role


def test_texts_complete_in_every_language(out):
    for table in ("i18n", "verdicts"):
        en = out[table]["en"]
        for lang in ("nl", "fr"):
            assert set(out[table][lang]) == set(en), (table, lang)
            for k, v in en.items():
                ph = lambda s: sorted(re.findall(r"\{(\w+)\}", json.dumps(s)))  # noqa: E731
                assert ph(out[table][lang][k]) == ph(v), (table, lang, k)


def test_every_verdict_of_the_assessment_has_a_text(out):
    src = (FRONT / "dcm-efficiency-assess.js").read_text(encoding="utf-8")
    keys = set(re.findall(r'v\("(?:good|watch|bad|info)", "(\w+)"', src))
    keys |= set(re.findall(r'\["(?:good|watch|bad|info)", "(\w+)"\]', src))
    assert len(keys) > 90
    assert keys <= set(out["verdicts"]["en"])


@pytest.mark.parametrize("lang", ["en", "nl", "fr", "no_registry"])
def test_real_integration_renders_every_tab(out, lang):
    r = out["cases"][lang]
    assert r["ok"] is True and all(r["ids"].values()), r["ids"]
    assert r["samples"] > 100
    assert r["live"]["lwt"] == 33.0 and r["live"]["out"] == 5.2 and r["live"]["room"] == 20.4
    for tab, html in r["html"].items():
        text = _text(html)
        assert not re.search(r"undefined|NaN|\{\w+\}|\[object", text), (lang, tab, text)
        assert html.count('class="vd ') >= (1 if tab == "advice" else 2), tab
    assert r["html"]["live"].count("<polyline") >= 6


def test_real_integration_verdicts(out):
    v = out["cases"]["en"]["v"]
    assert v["tracker"] == ["good", "trk_on"] and v["water"] == ["good", "w_ok"]
    assert v["hydraulics"] == ["good", "h_ok"] and v["comfort"] == ["good", "r_ok"]
    assert v["cop"] == ["good", "cop_ok"] and v["sheet"] == ["good", "sh_ok"]
    assert v["curveFit"] == ["info", "cv_flat"]  # the simulation keeps the water at 33 °C
    assert v["events"] == ["watch", "ev_buh"]   # 3 min backup heater at 07:00
    assert v["advice"] == ["info", "ad_no_room"]
    assert out["cases"]["en"]["overall"] == "watch"


@pytest.mark.parametrize(("case", "key", "expected"), [
    ("far_above", "tracker", ["bad", "trk_far_above"]),
    ("below", "tracker", ["watch", "trk_below"]),
    ("dhw", "tracker", ["info", "trk_dhw"]),
    ("defrost", "tracker", ["info", "trk_defrost"]),
    ("defrost", "water", ["info", "w_defrost"]),
    ("off_warm", "tracker", ["info", "trk_off_warm"]),
    ("dt_high", "water", ["watch", "w_dt_high"]),
    ("dt_high", "hydraulics", ["watch", "h_low"]),
    ("min_flow", "hydraulics", ["bad", "h_below_min"]),
    ("no_flow", "hydraulics", ["bad", "h_no_flow"]),
    ("short", "compressor", ["bad", "c_short"]),
    ("room_cold", "comfort", ["bad", "r_cold"]),
    ("room_warm", "comfort", ["watch", "r_warm"]),
    ("no_room", "comfort", ["info", "r_none"]),
    ("cop_low", "cop", ["bad", "cop_low"]),
    ("cop_suspect", "cop", ["watch", "cop_suspect"]),
    ("imbalance", "balance", ["bad", "ba_bad"]),
    ("lower", "advice", ["watch", "ad_lower"]),
    ("adv_dhw", "advice", ["info", "ad_dhw"]),
    ("curve_ok", "curveFit", ["good", "cv_ok"]),
    ("curve_buh", "curveFit", ["watch", "cv_buh"]),
    ("spf_low", "spf", ["bad", "spf_low"]),
    ("sheet_low", "sheet", ["bad", "sh_low"]),
    ("degr", "trend", ["watch", "tr_warning"]),
    ("defrost_bad", "events", ["bad", "ev_defrost_bad"]),
    ("defrost_watch", "events", ["watch", "ev_defrost_watch"]),
])
def test_scenarios(out, case, key, expected):
    assert out["cases"][case]["v"][key] == expected


def test_scenario_texts(out):
    live = _text(out["cases"]["far_above"]["html"]["live"])
    assert "Far above the target (3.5 K)" in live
    assert "lower than the datasheet" not in live
    curve = _text(out["cases"]["curve_ok"]["html"]["curve"])
    # weighted fit of the four bands (n 50 / 80 / 90 / 40)
    assert "Good curve: LWT = 38 − 0.68 × outdoor" in curve and "LWT = 38.0 − 0.68 × T_out" in curve
    assert "Lower the curve by 2 °C" in _text(out["cases"]["lower"]["html"]["advice"])
    assert "below the minimum flow you set (20 l/min)" in _text(out["cases"]["min_flow"]["html"]["live"])
    nl = _text(out["cases"]["nl"]["html"]["live"])
    assert "Op doel" in nl and "33,0 °" in nl
    assert "Sur la cible" in _text(out["cases"]["fr"]["html"]["live"])


def test_help_explains_with_the_model_specs(out):
    html = out["cases"]["en"]["html"]
    assert "Your EPRA12EAV3 works between 18 and 60 °C; above 55 °C the backup heater helps" in _text(html["live"])
    assert "datasheet gives SCOP 4.82 for 35 °C water and 3.48 for 55 °C" in _text(html["eff"])
    assert "Right now" in _text(html["curve"]) and "below 5 °C the outdoor unit defrosts" in _text(html["curve"])
    assert "Je EPRA12EAV3 werkt tussen 18 en 60 °C" in _text(out["cases"]["nl"]["html"]["live"])


def test_not_found(out):
    r = out["cases"]["none"]
    assert r["ok"] is False and "entities not found" in r["html"]["live"]


def test_pure_helpers(out):
    u = out["unit"]
    assert u["ds"][0] == pytest.approx(4.92) and u["ds"][1] == pytest.approx(2.05)
    assert u["ds"][2] == pytest.approx(4.5) and u["ds"][3] == pytest.approx((4.92 + 2.94) / 2)
    assert u["ds"][4] is None and u["ds"][5] is None
    # outside the datasheet points: nearest point x Carnot ratio (#435: ERGA06 has A7 only)
    assert u["ds"][6] == pytest.approx(4.85 * u["ds"][7]) and u["ds"][6] < 4.85
    assert u["ds"][8] == pytest.approx(4.92 * u["ds"][9]) and u["ds"][8] > 4.92
    assert u["fit"]["a"] == pytest.approx(40) and u["fit"]["b"] == pytest.approx(-0.5) and u["fit"]["spread"] == 20
    assert u["fitNone"] is None
    assert [(b["key"], b["x"]) for b in u["buckets"]] == [("-10-", -11), ("-4--2", -3), ("0-2", 1), ("20+", 21)]
    # value holds until the next sample: 300 s at 30 °C + 200 s at 36 °C, compressor off after
    assert u["mean10"] == pytest.approx((30 * 300 + 36 * 200) / 500)
    assert u["carry"][0] == [1600, 30]  # 30 °C held from t=1000 into the window
    assert u["spans"] == [{"from": 10, "to": 20}, {"from": 30, "to": 50}]
    p = u["parsed"]
    assert [s["lwt"] for s in p["samples"]] == [33, 33] and p["samples"][1]["kw"] == 6
    assert p["spans"]["defrost_active"] == [{"t": 120, "on": True}, {"t": 130, "on": False}]
    assert u["append"] == [True, False, 1, 1]
    assert u["carnot"][0] == pytest.approx((37 + 273.15) / (37 - 1)) and u["carnot"][1] is None
    assert u["fill"] == ["5,3 · 4,92 · 34 · — · x", "+7 %", "-7 %"]
    assert "<script>" not in u["esc"] and "&lt;script&gt;" in u["esc"]


def test_card_version_matches_changelog(out):
    log = (ROOT / "dashboard/cards/daikin-efficiency-card/CHANGELOG.md").read_text(encoding="utf-8")
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
  for (const f of D.files) await p.addScriptTag({ content: fs.readFileSync(f, 'utf8') });
  const res = await p.evaluate(async (c) => {
    const N = Date.parse(c.now); Date.now = () => N;
    const out = { calls: [] };
    const Card = customElements.get('daikin-efficiency-card');
    const el = document.createElement('daikin-efficiency-card');
    try { el.setConfig({ default_tab: 'nope' }); } catch (e) { out.badTab = e.message; }
    try { el.setConfig({ range: '1y' }); } catch (e) { out.badRange = e.message; }
    el.setConfig({ range: '24h' });
    document.getElementById('c').appendChild(el);
    el.hass = { states: c.states, entities: c.entities, language: 'en', locale: { language: 'en' },
      callWS: async (msg) => { out.calls.push(msg); return c.history; } };
    await new Promise((r) => setTimeout(r, 50));
    const R = () => el.shadowRoot, q = (s) => R().querySelector(s);
    const tab = () => q('.tab.on').dataset.tab;
    out.first = tab(); out.range = q('.win.on').dataset.range;
    out.lines = R().querySelectorAll('polyline').length;
    q('[data-range="30m"]').click(); out.range2 = q('.win.on').dataset.range;
    q('[data-act="adv"]').click(); out.adv = R().querySelectorAll('.vd[data-vd="liquid"]').length;
    q('[data-act="help"]').click(); out.helpClosed = !q('.hb');
    q('[data-act="help"]').click(); out.helpOpen = !!q('.hb');
    q('[data-tab="curve"]').click(); out.curve = tab();
    q('.pt').dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true })); out.detail = !!q('.detail');
    for (const t of ['today', 'eff', 'advice']) { q(`[data-tab="${t}"]`).click(); out[t] = R().querySelectorAll('.vd').length; }
    const before = q('#root').innerHTML;
    el.hass = Object.assign({}, el.hass);
    out.stable = q('#root').innerHTML === before;
    /* history refused: the card says so and keeps drawing live data */
    const el2 = document.createElement('daikin-efficiency-card'); el2.setConfig({});
    document.getElementById('c').appendChild(el2);
    el2.hass = { states: c.states, entities: c.entities, language: 'nl', callWS: async () => { throw new Error('no recorder'); } };
    await new Promise((r) => setTimeout(r, 50));
    el2.hass = Object.assign({}, el2.hass);
    out.failNote = el2.shadowRoot.querySelector('.note') ? el2.shadowRoot.querySelector('.note').textContent : '';
    out.stub = Card.getStubConfig(); out.size = el.getCardSize(); out.grid = el.getGridOptions();
    const ed = Card.getConfigElement(); document.body.appendChild(ed);
    let changed = null; ed.addEventListener('config-changed', (e) => { changed = e.detail.config; });
    ed.setConfig({ range: '3h' }); ed.hass = el.hass;
    const form = ed.querySelector('ha-form');
    out.schema = form.schema.map((x) => x.name); out.formHelp = form.data.show_help;
    form.dispatchEvent(new CustomEvent('value-changed', { detail: { value: { range: '24h', title: '', tabs: [], show_help: true, min_flow: 12 } } }));
    out.changed = changed;
    return out;
  }, D.case);
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
        input=json.dumps({"files": [str(FRONT / f) for f in ORDER], "case": _case()}),
    )
    assert proc.returncode == 0, proc.stderr
    r = json.loads(proc.stdout)
    assert r["errors"] == []
    assert "default_tab must be one of" in r["badTab"] and "range must be one of" in r["badRange"]
    call = r["calls"][0]
    assert len(r["calls"]) == 1 and call["type"] == "history/history_during_period"
    assert call["no_attributes"] is False and call["minimal_response"] is False
    assert sorted(call["entity_ids"]) == sorted([
        "sensor.daikin_cycle_ml_thermal_power_live", "binary_sensor.daikin_cycle_ml_compressor_running",
        "binary_sensor.daikin_cycle_ml_defrost_active", "binary_sensor.daikin_cycle_ml_dhw_active",
        "binary_sensor.daikin_cycle_ml_buh_active"])
    assert r["first"] == "live" and r["range"] == "24h" and r["range2"] == "30m"
    assert r["lines"] >= 6 and r["adv"] == 1
    assert r["helpClosed"] is True and r["helpOpen"] is True
    assert r["curve"] == "curve" and r["detail"] is True
    assert r["today"] >= 3 and r["eff"] >= 3 and r["advice"] >= 2  # advice itself is the big box
    assert r["stable"] is True
    assert "Historie is niet beschikbaar" in r["failNote"]
    assert r["stub"] == {"default_tab": "live", "range": "3h"} and r["size"] == 12 and r["grid"]["columns"] == 12
    assert r["schema"] == ["device_id", "title", "default_tab", "range", "tabs", "language", "show_help", "min_flow"]
    assert r["formHelp"] is True
    assert r["changed"] == {"range": "24h", "min_flow": 12}
