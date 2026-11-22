"""#467: native card custom:daikin-performance-card.

Node (vm) loads the three card files in any order and runs the model and
render parts on the states of the real integration (EN / NL / FR). The
model profile is applied to the fixture's hp_specs by the integration's own
apply_profile (R397), so the card reads what production writes. Chromium
mounts the element at phone, tablet and desktop width: no horizontal
overflow, the profile panel saves through set_model_profile, the editor.
"""
from __future__ import annotations

import json
import math
import random
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.engine import model_profile as mp
from tests.test_efficiency_native_card import _case, _set, _text

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "custom_components/daikin_cycle_ml/frontend"
FILES = ["daikin-performance-card.js", "dcm-performance-render.js", "dcm-performance-model.js"]
SHOTS = Path(tempfile.gettempdir()) / "dcm-perf-shots"   # screenshots to look at (R402), not committed

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")

PROFILE = mp.edit({}, "epra12eav3", fields={"rps_min": 15, "rps_max": 95}, points=[
    {"t_out": 7, "t_lwc": 35, "hmax": 12.0}, {"t_out": -7, "t_lwc": 35, "hmax": 10.4},
    {"t_out": 7, "t_lwc": 55, "hmax": 11.0}, {"t_out": -7, "t_lwc": 55, "hmax": 9.6},
])

RUNNER = r"""
const vm = require('vm'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
const win = {};
const ctx = vm.createContext({ window: win, Intl, Date, Math, JSON, Object, Array, String, Number, Set,
  parseFloat, isFinite, RegExp, Error, console: { info() {} }, HTMLElement: class {}, CustomEvent: class {}, document: {},
  customElements: { _d: {}, get(n) { return this._d[n]; }, define(n, c) { this._d[n] = c; } } });
const defined = [];
for (const f of D.files) { vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f }); defined.push(Object.keys(ctx.customElements._d).length); }
const P = win.DaikinPerformanceCardParts, M = P.model;
const out = { defined, tags: Object.keys(ctx.customElements._d), picker: win.customCards, version: win.DaikinPerformanceCard.version,
  i18n: P.render.I18N, suffix: M.SUFFIX, cases: {} };
for (const [name, c] of Object.entries(D.cases)) {
  const hass = { states: c.states, entities: c.entities, language: c.lang, locale: { language: c.lang } };
  const m = M.buildModel(hass, c.config || {});
  out.cases[name] = { lang: m.lang, ok: m.ok, lvl: m.lvl, key: m.key, loads: m.loads, limits: m.limits, copPct: m.copPct,
    headroom: m.headroom, staticLoad: m.staticLoad, primary: m.primary, atLimit: m.atLimit,
    html: P.render.render(m, c.config || {}, Object.assign({ prof: true, msg: '', msgErr: false }, c.ui || {})) };
}
const pts = [{ t_out: 7, t_lwc: 35, hmax: 12 }, { t_out: -7, t_lwc: 35, hmax: 10 }, { t_out: 7, t_lwc: 55, hmax: 11, src: { hmax: 'manual' } }, { t_out: -7, t_lwc: 55, hmax: 9 }];
out.at = [M.atCondition(pts, 'hmax', 0, 45), M.atCondition(pts, 'hmax', 7, 35), M.atCondition(pts, 'hmax', 12, 35),
  M.atCondition(pts, 'hmax', 0, 30), M.atCondition([], 'hmax', 0, 35), M.atCondition(pts, 'hmax', null, 35),
  M.atCondition([{ t_out: 7, t_lwc: 35, cop: 4.9 }], 'cop', -7, 45)];
out.carnot = [M.carnot(35, 7), M.carnot(45, -7), M.carnot(null, 7), M.carnot(10, 40)];
out.esc = P.render.render({ ok: false, lang: 'en', model: '<i>', meta: '' }, { title: '<script>x</script>' }, {});
process.stdout.write(JSON.stringify(out));
"""


def _run(cases: dict, files=None) -> dict:
    files = files or FILES
    proc = subprocess.run(["node", "-e", RUNNER], capture_output=True, text=True, timeout=120, check=False,
                          input=json.dumps({"files": [str(FRONT / f) for f in files], "cases": cases}))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# #478: hp_specs as the sensor writes it now: the fixture's attributes with
# the bundled EPRA12EAV3 entry (certified points, hc_max_a7, max_input_kw)
BUNDLED = json.loads((ROOT / "custom_components/daikin_cycle_ml/data/datasheets.json").read_text())["models"]["epra12eav3"]
MERGED_KEYS = ("points", "value_sources", "profile", "rps_min", "rps_max", "hmax_basis", "hmax_anchor",
               "hc_max_a7", "max_input_kw")


def _specs(case: dict) -> dict:
    eid = next(k for k, v in case["entities"].items() if v["translation_key"] == "hp_specs")
    return {**case["states"][eid]["attributes"], **BUNDLED}


def _with_profile(case: dict) -> dict:
    merged = mp.apply_profile(_specs(case), PROFILE, "epra12eav3", {"rps_min": 18, "rps_max": 90, "runs": 40})
    return _set(case, "hp_specs", **{k: merged.get(k) for k in MERGED_KEYS},
                rps_learned={"rps_min": 18, "rps_max": 90, "runs": 40})


def _datasheet_only(case: dict) -> dict:
    merged = mp.apply_profile(_specs(case), None, "epra12eav3")
    return _set(case, "hp_specs", **{k: merged.get(k) for k in MERGED_KEYS})


def _cases() -> dict:
    c = {lang: _with_profile(_case(lang)) for lang in ("en", "nl", "fr")}
    c["plain"] = _case("en")                                   # datasheet only: no max heat, no speed range
    # #478: at its limit = full confirmed speed AND water > 2 K below target (34 °C)
    c["limit"] = _set(_with_profile(_case("en")), "thermal_power_live", input_rps=95, lwt_c=31.5)
    c["limit_buh"] = _set(_set(_with_profile(_case("en")), "thermal_power_live", input_rps=95, lwt_c=31.5), "buh_active", "on")
    c["fast_on_target"] = _set(_with_profile(_case("en")), "thermal_power_live", input_rps=95)
    c["buh_reserve"] = _set(_with_profile(_case("en")), "buh_active", "on")
    c["seen"] = _set(_datasheet_only(_case("en")), "thermal_power_live", **{"state": "11.0"})
    c["near"] = _set(_with_profile(_case("en")), "thermal_power_live", input_rps=86)
    c["idle"] = _set(_with_profile(_case("en")), "compressor_running", "off")
    c["defrost"] = _set(_with_profile(_case("en")), "defrost_active", "on")
    c["cop_low"] = _set(_with_profile(_case("en")), "thermal_power_live", input_cop=3.0)
    c["primary_thermal"] = {**_with_profile(_case("en")), "config": {"primary_load": "thermal"}}
    c["primary_el"] = {**_with_profile(_case("en")), "config": {"primary_load": "electrical", "title": "Mine"}}
    c["cold"] = _set(_with_profile(_case("en")), "thermal_power_live", outdoor_c=-12, lwt_c=58)
    c["none"] = {**_case("en"), "states": {}, "entities": {}}
    c["datasheet_only"] = _datasheet_only(_case("en"))     # #467: hp_specs as the integration now writes it, no profile
    return c


@pytest.fixture(scope="module")
def out() -> dict:
    return _run(_cases())


def _carnot(lwt, out_c):
    tc, te = lwt + 2 + 273.15, out_c - 6 + 273.15
    return tc / (tc - te)


def test_parts_load_in_any_order():
    for _ in range(3):
        order = FILES[:]
        random.shuffle(order)
        r = _run({}, order)
        assert r["tags"] == ["daikin-performance-card", "daikin-performance-card-editor"]
        assert r["defined"][-1] == 2
        assert [p["type"] for p in r["picker"]] == ["daikin-performance-card"]


def test_files_small_and_served():
    from custom_components.daikin_cycle_ml.frontend import CARD_FILES

    for f in FILES:
        assert f in CARD_FILES
        assert len((FRONT / f).read_text(encoding="utf-8").splitlines()) < 500


def test_suffixes_match_the_other_native_card(out):
    eff = json.loads(subprocess.run(["node", "-e", "const w={};global.window=w;require(process.argv[1]);"
                                     "process.stdout.write(JSON.stringify(w.DaikinEfficiencyCardParts.data.SUFFIX))",
                                     str(FRONT / "dcm-efficiency-data.js")], capture_output=True, text=True, check=True).stdout)
    for role, sfx in out["suffix"].items():
        assert eff[role] == sfx, role


def test_texts_complete_in_every_language(out):
    en = out["i18n"]["en"]
    for lang in ("nl", "fr"):
        assert set(out["i18n"][lang]) == set(en), lang
        assert set(out["i18n"][lang]["src"]) == set(en["src"])
        for k, v in en.items():
            if isinstance(v, str):
                assert set(re.findall(r"\{(\w+)\}", out["i18n"][lang][k])) == set(re.findall(r"\{(\w+)\}", v)), (lang, k)


def test_loads_against_the_profile_limits(out):
    r = out["cases"]["en"]
    assert r["ok"] and r["lang"] == "en"
    # max heat at (5.2 °C, 33 °C): W35 row (nearest water). #478: A2/W35 is
    # the estimate 9.97 x 0.95 = 9.47 kW (above the 5.74 kW rating point);
    # A7/W35 is the manual 12 kW
    th_max = 9.47 + (12.0 - 9.47) * (5.2 - 2) / 5
    # 33 °C water is within 3 K of the W35 points: counts as known, no "add a point" note
    assert r["limits"]["thMax"] == pytest.approx(th_max, abs=1e-6) and r["limits"]["thExact"] is True
    assert "Nearest point" not in _text(r["html"])
    assert r["loads"]["thermal"] == pytest.approx(5.02 / th_max * 100, abs=1e-6)
    cop35 = 4.08 + (4.92 - 4.08) * (5.2 - 2) / 5
    cop = cop35 * _carnot(33, 5.2) / _carnot(35, 5.2)
    assert r["limits"]["copSpec"] == pytest.approx(cop, abs=1e-6)
    assert r["loads"]["electrical"] == pytest.approx(0.95 / 2.28 * 100, abs=1e-6)   # Daikin max power input
    assert r["limits"]["elEst"] is False and r["limits"]["fSeen"] is False and r["atLimit"] is False
    # manual 15-95 beats learned 18-90; Tweakers: the dial runs from 0 rps to
    # the maximum (was (32 - 15) / 80, which read 0 % below the minimum)
    assert r["loads"]["compressor"] == pytest.approx(32 / 95 * 100)
    assert r["copPct"] == pytest.approx(5.2874 / cop * 100, abs=1e-6)
    assert r["headroom"] == pytest.approx(th_max - 5.02, abs=1e-6)
    assert r["staticLoad"] == pytest.approx(5.02 / 12 * 100)
    assert (r["lvl"], r["key"]) == ("good", "ok_efficient")


@pytest.mark.parametrize(("case", "lvl", "key"), [
    ("plain", "info", "no_limits"), ("limit", "bad", "at_limit"), ("limit_buh", "bad", "at_limit_buh"),
    ("fast_on_target", "watch", "near_limit"), ("buh_reserve", "watch", "buh_on"),
    ("near", "watch", "near_limit"), ("idle", "info", "idle"), ("defrost", "info", "defrost"), ("cop_low", "good", "ok"),
])
def test_verdicts(out, case, lvl, key):
    assert (out["cases"][case]["lvl"], out["cases"][case]["key"]) == (lvl, key)


def test_missing_limits_are_said_not_invented(out):
    r = out["cases"]["plain"]
    assert r["limits"]["thMax"] is None and r["loads"]["thermal"] is None and r["loads"]["compressor"] is None
    text = _text(r["html"])
    assert "Max heat unknown · add it in the model profile" in text and "Speed range not known yet" in text
    assert "Add the max heat for this condition" in text
    assert "Missing" in text            # every datasheet point without max heat


@pytest.mark.parametrize(("lang", "words"), [
    ("en", ["Capacity used", "Compressor", "Electrical power", "COP vs rating point", "Model profile", "Manual", "Remove my value", "Estimate"]),
    ("nl", ["Benut vermogen", "Compressor", "Elektrisch vermogen", "COP t.o.v. meetpunt", "Modelprofiel", "Handmatig", "Schatting"]),
    ("fr", ["Puissance utilisée", "Compresseur", "Puissance électrique", "COP / point de mesure", "Profil du modèle", "Manuel", "Estimation"]),
])
def test_renders_in_every_language(out, lang, words):
    text = _text(out["cases"][lang]["html"])
    for w in words:
        assert w in text, (lang, w)
    assert "undefined" not in text and "NaN" not in text


def test_profile_panel_rows_and_sources(out):
    html = out["cases"]["en"]["html"]
    assert html.count('data-c="hmax"') == 7     # the 7 certified points (#478); the profile values sit on them
    assert 'data-field="rps_min"' in html and 'value="15"' in html
    assert 'data-act="clear-field"' in html and 'data-act="clear-point"' in html and 'data-act="add-point"' in html


def test_primary_dial_and_title(out):
    assert out["cases"]["primary_thermal"]["primary"] == "thermal"
    main = re.search(r'<div class="dial main">.*?<div class="cap">([^<]+)</div>', out["cases"]["primary_thermal"]["html"]).group(1)
    assert main == "Capacity used"
    html = out["cases"]["primary_el"]["html"]
    assert re.search(r'<div class="dial main">.*?<div class="cap">([^<]+)</div>', html).group(1) == "Electrical power"
    assert ">Mine · EPRA12EAV3<" in html


def test_outside_the_points_says_which_point(out):
    r = out["cases"]["cold"]
    assert r["limits"]["thExact"] is False
    assert "Nearest point: A-7/W55" in _text(r["html"])


def test_interpolation_helpers(out):
    at = out["at"]
    assert at[0]["value"] == pytest.approx((11 + 10) / 2 / 2 + (12 + 10) / 2 / 2, abs=1e-9) or at[0]["value"] == pytest.approx(10.5, abs=1e-9)
    assert at[0]["exact"] is True and at[0]["manual"] is True
    assert at[1]["value"] == 12 and at[1]["exact"] is True
    assert at[2]["value"] == 12 and at[2]["exact"] is False          # max heat held outside
    assert at[3]["exact"] is False
    assert at[4] is None and at[5] is None
    assert at[6]["value"] == pytest.approx(4.9 * _carnot(35, -7) / _carnot(35, 7) * _carnot(45, -7) / _carnot(35, -7), abs=1e-9)
    assert out["carnot"][2] is None and out["carnot"][3] is None
    assert math.isclose(out["carnot"][0], _carnot(35, 7))


def test_not_found_and_escaping(out):
    assert "Daikin Cycle ML entities not found." in _text(out["cases"]["none"]["html"])
    assert "<script>" not in out["esc"] and "&lt;script&gt;" in out["esc"]


BROWSER = r"""
const { chromium } = require('playwright'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const b = await chromium.launch();
  const out = { widths: {} };
  for (const [name, w] of [['phone', 390], ['tablet', 820], ['desktop', 1280]]) {
    const p = await b.newPage({ viewport: { width: w, height: 900 } });
    const errors = []; p.on('pageerror', (e) => errors.push(e.message));
    await p.setContent('<html><body style="margin:0"><div id="c" style="padding:8px"></div></body></html>');
    await p.addScriptTag({ content: "customElements.define('ha-card', class extends HTMLElement { connectedCallback(){ this.style.display='block'; } });"
      + "customElements.define('ha-form', class extends HTMLElement { set data(v){ this._d = v; } get data(){ return this._d; } });" });
    for (const f of D.files) await p.addScriptTag({ content: fs.readFileSync(f, 'utf8') });
    const r = await p.evaluate(async (c) => {
      const res = { calls: [] };
      const el = document.createElement('daikin-performance-card');
      el.setConfig({});
      document.getElementById('c').appendChild(el);
      el.hass = { states: c.states, entities: c.entities, language: 'en', locale: { language: 'en' },
        callService: async (d, s, data) => { res.calls.push([d, s, data]); if (data.fields && data.fields.rps_max === 999) throw new Error('rps_max=999 out of range'); } };
      await new Promise((r) => setTimeout(r, 30));
      const R = el.shadowRoot, q = (s) => R.querySelector(s);
      res.overflow = el.scrollWidth - el.clientWidth;
      res.dials = R.querySelectorAll('.dial').length;
      q('[data-act="prof"]').click();
      res.profOpen = !!q('.prof');
      res.overflowProf = el.scrollWidth - el.clientWidth;
      const inp = q('[data-field="rps_max"]'); inp.value = '92'; inp.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
      await new Promise((r) => setTimeout(r, 10));
      res.msg = q('.pmsg') ? q('.pmsg').textContent : '';
      const cell = q('[data-c="hmax"]'); cell.value = '11.5'; cell.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
      await new Promise((r) => setTimeout(r, 10));
      q('#new-t').value = '2'; q('#new-w').value = '45'; q('#new-hc').value = '10.1'; q('[data-act="add-point"]').click();
      await new Promise((r) => setTimeout(r, 10));
      q('#new-t').value = ''; q('[data-act="add-point"]').click();
      q('#new-t').value = '2'; q('#new-w').value = '45'; q('#new-hc').value = ''; q('#new-cop').value = ''; q('[data-act="add-point"]').click();
      const clr = q('[data-act="clear-point"]'); if (clr) clr.click();
      await new Promise((r) => setTimeout(r, 10));
      const cf = q('[data-act="clear-field"]'); if (cf) cf.click();
      await new Promise((r) => setTimeout(r, 10));
      const bad = q('[data-field="rps_max"]'); bad.value = '999'; bad.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
      await new Promise((r) => setTimeout(r, 10));
      res.err = q('.pmsg.err') ? q('.pmsg.err').textContent : '';
      q('[data-act="prof"]').click();
      res.profClosed = !q('.prof');
      const before = R.getElementById('root').innerHTML; el.hass = Object.assign({}, el.hass); res.stable = R.getElementById('root').innerHTML === before;
      const Card = customElements.get('daikin-performance-card');
      try { el.setConfig({ primary_load: 'x' }); } catch (e) { res.badCfg = e.message; }
      try { el.setConfig(null); } catch (e) { res.nullCfg = e.message; }
      res.stub = Card.getStubConfig(); res.size = el.getCardSize(); res.grid = el.getGridOptions(); res.hassBack = el.hass === el.hass;
      const ed = Card.getConfigElement(); document.body.appendChild(ed);
      let changed = null; ed.addEventListener('config-changed', (e) => { changed = e.detail.config; });
      ed.setConfig({ primary_load: 'thermal' }); ed.hass = el.hass;
      const form = ed.querySelector('ha-form');
      res.schema = form.schema.map((s) => s.name); res.label = form.computeLabel({ name: 'primary_load' }) + '|' + form.computeLabel({ name: 'zz' });
      form.dispatchEvent(new CustomEvent('value-changed', { detail: { value: { primary_load: 'electrical', title: '' } } }));
      res.changed = changed;
      document.body.removeChild(ed); document.body.appendChild(ed);
      return res;
    }, D.c);
    await p.screenshot({ path: D.shots + '/perf_' + name + '.png', fullPage: true });
    r.errors = errors; out.widths[name] = r;
  }
  await b.close();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _playwright() -> bool:
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, check=False).returncode == 0


@pytest.mark.skipif(not _playwright(), reason="playwright (node) not installed")
def test_card_on_phone_tablet_and_desktop():
    SHOTS.mkdir(exist_ok=True)
    c = _with_profile(_case("en"))
    proc = subprocess.run(["node", "-e", BROWSER], capture_output=True, text=True, timeout=240, check=False,
                          input=json.dumps({"files": [str(FRONT / f) for f in FILES], "c": c, "shots": str(SHOTS)}))
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    for name, r in res["widths"].items():
        assert r["errors"] == [], (name, r["errors"])
        assert r["overflow"] <= 0 and r["overflowProf"] <= 0, name          # no sideways scroll
        assert r["dials"] == 3 and r["profOpen"] and r["profClosed"] and r["stable"]
        calls = [call[2] for call in r["calls"]]
        assert all(call[0] == "daikin_cycle_ml" and call[1] == "set_model_profile" for call in r["calls"])
        assert {"fields": {"rps_max": 92}} in calls
        assert any(c.get("points") and c["points"][0].get("hmax") == 11.5 for c in calls)
        assert {"points": [{"t_out": 2, "t_lwc": 45, "hmax": 10.1}]} in calls
        assert any(c.get("points") and c["points"][0].get("hmax") is None and c["points"][0].get("cop") is None for c in calls)
        assert any(c.get("fields") and list(c["fields"].values()) == [None] for c in calls)
        assert "Saved" in r["msg"] and "rps_max=999" in r["err"]
        assert r["badCfg"].startswith("primary_load must be") and r["nullCfg"] == "Invalid configuration"
        assert r["stub"] == {"primary_load": "compressor"} and r["size"] == 8 and r["grid"]["columns"] == 12
        assert r["schema"] == ["device_id", "title", "primary_load", "language"]
        assert r["label"] == "Big dial|zz" and r["changed"] == {"primary_load": "electrical"}


def test_datasheet_only_install_gets_a_thermal_load(out):
    """#478 (Daikin certification 4D133543C): the EPRA12 rating points are
    lower bounds; the maximum is estimated from Daikin's 9.97 kW at A7/W35:
    at 5.2 °C / 33 °C between A2/W35 9.47 (estimate) and A7/W35 9.97."""
    r = out["cases"]["datasheet_only"]
    th = 9.47 + (9.97 - 9.47) * (5.2 - 2) / 5
    assert r["limits"]["thMax"] == pytest.approx(th, abs=1e-6)
    assert r["loads"]["thermal"] == pytest.approx(5.02 / th * 100, abs=1e-6)
    assert r["limits"]["thEstimate"] is True and r["limits"]["basis"] == "max"
    text = _text(r["html"])
    assert "Estimate from Daikin&#39;s maximum (9.97 kW at A7/W35), lower in frost" in r["html"]
    assert "32 rps ·" not in text                                  # no range yet: just the speed


def test_more_heat_than_the_estimate_raises_the_maximum(out):
    """#478: the reported case: delivering more than the maximum while the
    compressor has speed left proves the maximum is too low: no "at its limit"."""
    r = out["cases"]["seen"]
    assert r["limits"]["thSeen"] is True and r["limits"]["thMax"] == pytest.approx(11.0)
    assert r["loads"]["thermal"] == pytest.approx(100.0) and r["atLimit"] is False and r["lvl"] != "bad"
    text = _text(r["html"])
    assert "Delivers more than the estimate" in text and "the maximum is at least 11.0 kW" in text
    assert "AT ITS LIMIT" not in text
