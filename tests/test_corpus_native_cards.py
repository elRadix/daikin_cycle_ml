"""Diagnostics corpus as test base for the native cards and their backend.

Every anonymised install in tests/fixtures/diagnostics (EPRA prod-1 on
four versions, a basic-profile unit without DHW tank, an ERGA split, an
EVLQ hybrid with Dutch entity ids) is replayed through:

- the live temperatures of thermal_power_live (engine.thermal), from the
  install's own ESPAltherma attributes;
- the recorder exclusion: every attribute set the diagnostics had to
  truncate (> 4 KB) belongs to a sensor whose large attributes stay out
  of the recorder (prod-1: daily_summary_recent 18,444 bytes, over the
  16 KB recorder limit);
- the Efficiency card (Node): entities found without the registry in the
  install's language, every tab rendered, every verdict has a text;
- the Daily summary card (Node) where the summary was not truncated.

A new diagnostics file (tools/ingest_diagnostics.py) joins these tests
by itself.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml import sensor as s
from custom_components.daikin_cycle_ml.engine.attribute_compat import build_compat_view
from custom_components.daikin_cycle_ml.engine.thermal import live_temps_from_view
from tests.test_diagnostics_corpus import FILES

ROOT = Path(__file__).resolve().parent.parent
COMP = ROOT / "custom_components/daikin_cycle_ml"
FRONT = COMP / "frontend"
EFF = ["dcm-efficiency-data.js", "dcm-efficiency-assess.js", "dcm-efficiency-charts.js",
       "dcm-efficiency-verdicts.js", "dcm-efficiency-i18n.js", "dcm-efficiency-render.js",
       "daikin-efficiency-card.js"]
DAILY = "daikin-daily-summary-card.js"


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _key_of() -> dict[tuple[str, str], tuple[str, str]]:
    """(platform, object-id suffix in any language) -> (translation key, language)."""
    out = {}
    for lang in ("en", "nl", "fr"):
        ent = json.loads((COMP / f"translations/{lang}.json").read_text(encoding="utf-8"))["entity"]
        for plat in ("sensor", "binary_sensor"):
            for key, v in ent[plat].items():
                out.setdefault((plat, _slug(v["name"])), (key, lang))
    return out


KEY_OF = _key_of()


def _doc(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hass_case(doc: dict) -> dict:
    """States as the install's HA holds them; thermal_power_live gets the
    live temperatures the current sensor computes from the install's source."""
    temps = live_temps_from_view(build_compat_view(doc["source"]["attributes"]))
    states, langs = {}, []
    for name, st in doc["entities"].items():
        plat, sfx = name.split(":", 1)
        key, lang = KEY_OF.get((plat, sfx), (None, None))
        if key and lang != "en":
            langs.append(lang)
        attrs = dict(st.get("attributes") or {})
        if key == "thermal_power_live":
            attrs.update(temps)
        states[f"{plat}.daikin_cycle_ml_{sfx}"] = {"state": st.get("state"), "attributes": attrs}
    lang = max(set(langs), key=langs.count) if langs else "en"
    return {"states": states, "lang": lang, "now": doc["generated_at"],
            "daily": "_truncated" not in (doc["entities"].get(
                next((n for n in doc["entities"] if KEY_OF.get(tuple(n.split(":", 1)), ("",))[0]
                      == "daily_summary_recent"), ""), {}).get("attributes") or {})}


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_corpus_live_temperatures(path):
    attrs = _doc(path)["source"]["attributes"]
    t = live_temps_from_view(build_compat_view(attrs))
    assert 5 <= t["lwt_c"] <= 80 and 5 <= t["return_c"] <= 80, t
    assert -30 <= t["outdoor_c"] <= 45, t
    assert abs(t["lwt_c"] - t["return_c"]) < 25, t
    assert t["lw_setpoint_c"] is not None
    # the liquid temperature (R3T) only when the definition publishes it: the
    # EDLA v1 source of #487 has 32 values and no R3T; the cards show "—"
    has_r3t = any("R3T" in k for k in attrs)
    assert (t["refrigerant_liquid_c"] is not None) == has_r3t, (t, has_r3t)


def test_corpus_truncated_attributes_stay_out_of_the_recorder():
    truncated: dict[str, int] = {}
    for path in FILES:
        for name, st in _doc(path)["entities"].items():
            attrs = st.get("attributes") or {}
            if attrs.get("_truncated"):
                key = KEY_OF[tuple(name.split(":", 1))][0]
                truncated[key] = max(truncated.get(key, 0), int(attrs["_original_bytes"]))
    assert truncated, "the corpus should hold at least one large attribute set"
    assert set(truncated) <= s.LARGE_ATTR_SENSORS, truncated
    # prod-1 on 1.26.0: the recorder warning of 2026-11-21
    assert truncated["daily_summary_recent"] > 16384


RUNNER = r"""
const vm = require('vm'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
const win = {};
const ctx = vm.createContext({ window: win, Intl, Date, Math, JSON, Object, Array, String, Number, Set,
  parseFloat, isFinite, RegExp, Error, console: { info() {}, log() {}, warn() {}, debug() {} },
  HTMLElement: class {}, CustomEvent: class {}, document: {},
  customElements: { _d: {}, get(n) { return this._d[n]; }, define(n, c) { this._d[n] = c; } },
  setInterval: () => 0, clearInterval: () => 0 });
for (const f of D.files) vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
const P = win.DaikinEfficiencyCardParts, K = win.DaikinDailySummaryCard, out = {};
for (const [name, c] of Object.entries(D.cases)) {
  const hass = { states: c.states, entities: {}, language: c.lang, locale: { language: c.lang } };
  const now = Date.parse(c.now) / 1000;
  const m = P.data.buildModel(hass, {}, { samples: [], spans: {} }, now, '3h');
  m.buf = { samples: [], spans: {} };
  const a = P.assess.assess(m);
  const r = { ok: m.ok, lang: m.lang, missing: Object.keys(m.ids).filter((k) => !m.ids[k]), v: {}, html: {}, daily: {} };
  for (const k of Object.keys(a)) if (a[k] && a[k].lvl && k !== 'overall') r.v[k] = [a[k].lvl, a[k].k];
  for (const tab of P.render.TABS) r.html[tab] = P.render.render(m, a, {}, { tab, range: '3h', adv: true, help: true });
  if (c.daily) {
    const dm = K.buildModel(hass, {}, now * 1000);
    r.dailyOk = dm.ok; r.days = dm.allDays.length;
    for (const tab of K.TABS) r.daily[tab] = K.render(dm, {}, { tab, win: 30, day: null, alert: null, allAlerts: false });
  }
  out[name] = r;
}
out.__verdicts = Object.keys(P.verdicts.en);
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def replay() -> dict:
    if not shutil.which("node"):
        pytest.skip("node not installed")
    cases = {p.stem: _hass_case(_doc(p)) for p in FILES}
    proc = subprocess.run(
        ["node", "-e", RUNNER], capture_output=True, text=True, timeout=120, check=False,
        input=json.dumps({"files": [str(FRONT / f) for f in EFF + [DAILY]], "cases": cases}),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_corpus_efficiency_card(replay, path):
    r = replay[path.stem]
    assert r["ok"] is True
    # every entity of the card is found without the registry, in the install's language
    assert r["missing"] == [], r["missing"]
    for tab, html in r["html"].items():
        text = _text(html)
        assert not re.search(r"undefined|NaN|\{\w+\}|\[object", text), (tab, text[:300])
    for lvl, key in r["v"].values():
        assert lvl in ("good", "watch", "bad", "info") and key in replay["__verdicts"], key


def test_corpus_language_follows_the_install(replay):
    langs = {stem: r["lang"] for stem, r in replay.items() if not stem.startswith("__")}
    assert langs["evlq08cv3_1_22_7_d89874c2b5_202611160654"] == "nl"
    assert "Live" in _text(replay["evlq08cv3_1_22_7_d89874c2b5_202611160654"]["html"]["live"])


def test_corpus_prod1_verdicts(replay):
    # prod-1 on 1.26.0: COP 6.27 at 8.2 °C outdoor / 33 °C water, flow 14.1, ΔT 5.7
    v = replay["epra12eav3_1_26_0_441e207ca5_202611200641"]["v"]
    assert v["cop"] == ["good", "cop_ok"]
    assert v["water"] == ["good", "w_ok"] and v["hydraulics"] == ["good", "h_ok"]
    assert v["comfort"] == ["good", "r_ok"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_corpus_daily_summary_card(replay, path):
    r = replay[path.stem]
    if not r["daily"]:
        pytest.skip("daily_summary_recent truncated in this diagnostics file")
    assert r["dailyOk"] is True
    for tab, html in r["daily"].items():
        text = _text(html)
        assert not re.search(r"undefined|NaN|\[object", text), tab
        if tab != "today" and r["days"] == 0:   # #435 day 1: detection was frozen
            assert "No daily data yet" in text or "Nog geen dagdata" in text, tab
