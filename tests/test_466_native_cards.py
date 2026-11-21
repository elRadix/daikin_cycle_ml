"""#466: native cards after Tweakers feedback.

- Efficiency card: the target ΔT is a card option (target_dt, default 5 K).
  An installation set to 3 K was told its ΔT was off; the target lines,
  verdicts and help now use the installer's value.
- Both cards draw their charts at the card's own width, so text and lines
  keep their size on a wide desktop card (they were scaled up ~3x from a
  360-unit drawing).
- Flow and ΔT chart: units on both axes and a legend for every line.
- A chart whose history starts inside the window starts its time axis
  there instead of squeezing the data against the right edge.
- Daily summary Trends show the last value and the range.
Fixture: states and history of the real integration (EN / NL / FR).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from tests.test_efficiency_native_card import FRONT, ORDER, _case, _run, _set, _text

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def _dt(lang: str, dt: float, target: float | None) -> dict:
    c = _set({**_case(lang), "history": {}}, "thermal_power_live", input_dt_k=dt)
    if target is not None:
        c["config"] = {"target_dt": target}
    return c


@pytest.fixture(scope="module")
def out() -> dict:
    cases = {
        "dt3_default": _dt("en", 2.8, None),       # 5 K default: below 3 K -> watch
        "dt3_target3": _dt("en", 2.8, 3),          # installer set 3 K: good
        "dt6_target3": _dt("en", 6.5, 3),          # above 3 + 3 K -> watch
        "bad_option": _dt("en", 2.8, 40),          # out of range -> 5 K
    }
    for lang in ("en", "nl", "fr"):
        cases["t3_" + lang] = _dt(lang, 3.1, 3)
    return _run(cases)


def test_default_target_is_five_kelvin(out):
    v = out["cases"]["dt3_default"]["v"]
    assert v["water"] == ["watch", "w_dt_low"]
    assert v["hydraulics"] == ["watch", "h_high"]
    assert out["cases"]["bad_option"]["v"]["water"] == ["watch", "w_dt_low"]


def test_installer_target_is_used(out):
    assert out["cases"]["dt3_target3"]["v"]["water"] == ["good", "w_ok"]
    assert out["cases"]["dt3_target3"]["v"]["hydraulics"] == ["good", "h_ok"]
    assert out["cases"]["dt6_target3"]["v"]["water"] == ["watch", "w_dt_high"]
    assert out["cases"]["dt6_target3"]["v"]["hydraulics"] == ["watch", "h_low"]


@pytest.mark.parametrize(("lang", "line", "verdict", "help_text"), [
    ("en", "target 3 K", "your target 3 K", "Your target is 3 K"),
    ("nl", "doel 3 K", "je doel 3 K", "Je doel is 3 K"),
    ("fr", "cible 3 K", "votre cible 3 K", "Votre cible est 3 K"),
])
def test_texts_name_the_target(out, lang, line, verdict, help_text):
    html = out["cases"]["t3_" + lang]["html"]["live"]
    text = _text(html)
    assert line in text
    assert verdict in text
    assert help_text in text
    # no fixed 5 K left except the "Daikin default about 5 K" remark in the help
    rest = re.sub(r"(about|ongeveer|environ) 5 K", "", text)
    assert not re.search(r"(?<![\d.,])5 K", rest)


def test_flow_chart_has_units_and_legend(out):
    html = out["cases"]["t3_en"]["html"]["live"]
    assert ">l/min<" in html and ">ΔT K<" in html and ">°C<" in html
    text = _text(html)
    assert "flow l/min (←)" in text and "ΔT K (→)" in text and "- - target 3 K" in text


def test_no_old_fixed_texts_left():
    for f in ("dcm-efficiency-verdicts.js", "dcm-efficiency-i18n.js"):
        src = (FRONT / f).read_text(encoding="utf-8")
        for old in ("At 5 K", "Bij 5 K", "À 5 K", "below 3 K", "above 8 K", "design 5 K", "ontwerp 5 K"):
            assert old not in src, (f, old)


WIDTH = r"""
const vm = require('vm'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
const win = {};
const ctx = vm.createContext({ window: win, Intl, Date, Math, JSON, Object, Array, String, Number,
  parseFloat, isFinite, RegExp, Error, console: { info() {}, log() {}, warn() {}, debug() {} },
  HTMLElement: class {}, CustomEvent: class {}, document: {},
  customElements: { _d: {}, get(n) { return this._d[n]; }, define(n, c) { this._d[n] = c; } },
  setInterval: () => 0, clearInterval: () => 0 });
for (const f of D.files) vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
const C = win.DaikinEfficiencyCardParts.charts, S = win.DaikinDailySummaryCard;
const fmt = (ms) => String(ms / 1000);
const win3h = { from: 0, to: 10800, spans: {}, samples: [{ t: 9000, a: 1 }, { t: 10000, a: 2 }] };
const full = { from: 0, to: 10800, spans: {}, samples: [{ t: 0, a: 1 }, { t: 10000, a: 2 }] };
const opts = { series: [{ get: (p) => p.a, color: '#000' }], yL: { unit: 'l/min' } };
const out = { sizes: [] };
for (const w of [undefined, 0, 200, 1180, 5000]) {
  out.sizes.push([C.setWidth(w), C.lineChart(full, opts, fmt).match(/viewBox="([^"]+)"/)[1]]);
}
C.setWidth(360);
out.fit = C.lineChart(win3h, opts, fmt);
out.full = C.lineChart(full, opts, fmt);
out.daily = [S.setChartWidth(1000), S.setChartWidth(-1)];
process.stdout.write(JSON.stringify(out));
"""


def test_charts_follow_the_card_width():
    files = [str(FRONT / f) for f in ORDER] + [str(FRONT / "daikin-daily-summary-card.js")]
    proc = subprocess.run(["node", "-e", WIDTH], input=json.dumps({"files": files}),
                          capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    r = json.loads(proc.stdout)
    assert r["sizes"] == [[360, "0 0 360 150"], [360, "0 0 360 150"], [300, "0 0 300 150"],
                          [1180, "0 0 1180 240"], [1400, "0 0 1400 240"]]
    assert r["daily"] == [1000, 360]
    # history inside the window: the axis starts at the first sample
    first_x = float(re.search(r'<polyline points="([\d.]+),', r["fit"]).group(1))
    assert first_x == pytest.approx(30.0, abs=0.2)
    assert float(re.search(r'<polyline points="([\d.]+),', r["full"]).group(1)) == pytest.approx(30.0, abs=0.2)
    assert ">l/min<" in r["fit"]


@pytest.mark.parametrize("lang", ["en", "nl", "fr"])
def test_daily_trends_show_numbers(lang):
    from tests.test_daily_summary_native_card import _fixture
    from tests.test_daily_summary_native_card import _run as daily_run

    html = daily_run({lang: _fixture(lang)})["cases"][lang]["html"]["overview"]
    sparks = html[html.index('class="sparks"'):]
    assert sparks.count('class="sv"') == 3      # last value of each trend
    assert sparks.count('class="sr"') == 3      # its range over the period
    assert re.search(r'class="sv"[^>]*>\d', sparks)
