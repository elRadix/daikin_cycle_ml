"""#427: the LWT fine-tuning card keeps its tab and pop-up over re-renders.

The card uses ``triggers_update: all``: button-card re-renders the whole
content on every Home Assistant state change. The tab the user picked and
an open pop-up were lost each time (Tweakers report). The colours of the
advice follow the convention: optimal = green, lower LWT = blue,
raise LWT = red.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CARD = Path(__file__).resolve().parent.parent / "dashboard/cards/lwt-fine-tuning/card.yaml"
GREEN, BLUE, RED = "#2E7D32", "#0097E0", "#C62828"

RUNNER = r"""
const vm = require('vm');
const D = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const timers = [];
const shown = [];
const win = {};
const ctx = vm.createContext({ Date, Math, JSON, Object, Array, String, Number, parseFloat,
  parseInt, isNaN, isFinite, RegExp, Error, console: { log() {}, warn() {}, error() {} },
  setTimeout: (f, ms) => { timers.push(f); return timers.length; }, clearTimeout: () => 0,
  window: win });
const content = vm.runInContext('(function(hass,states,entity,user,variables,html,helpers){' + D.content + '\n})', ctx);
const tap = vm.runInContext('(function(hass,states,entity,user,variables,html,helpers){' + D.tap + '\n})', ctx);
function states(delta) {
  return { 'sensor.daikin_cycle_ml_heating_curve_advice': { state: 'behoud', attributes: {
    bucket: '5-10', delta_c: delta, offset_delta_c: delta, huidige_lwt: 33, optimale_lwt: 33 + delta,
    buckets: { '0-5': { n: 4, cop: 3.4, lwt: 35 }, '5-10': { n: 5, cop: 4.1, lwt: 32 } }, samples: 40 } } };
}
const hass = { language: 'en', user: { name: 'u' }, themes: { darkMode: false } };
function render(self, delta, vars) {
  return content.call(self, hass, states(delta), undefined, hass.user, vars || {}, (s) => s.join(''), {});
}
const out = {};
const self = { _config: {} };
out.first = render(self, 0);
out.default_tab = render(self, 0, { default_tab: 'analysis' });
// user clicks the "live" tab
const btns = [];
const hub = { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, querySelector: () => null };
const tabEl = { dataset: { evAction: 'view', evArg: 'live' } };
const root = { querySelector: (s) => s === '.lwt-hub' ? hub : null,
  querySelectorAll: (s) => s === '.lwt-btn' ? btns : [tabEl] };
tap.call({ shadowRoot: root }, hass, {}, undefined, hass.user, {}, null, {});
out.hub_view = hub.attrs['data-view'];
out.after_click = render(self, 0);
// a pop-up was open: the re-render shows it again for the rest of its time
timers.length = 0;
win.__lwtShowPop = (h, el, ms) => shown.push({ pid: el.pid, ms: ms });
win.__lwtOpenPop = { pid: 'lwt3', until: Date.now() + 4000 };
const el = { pid: 'lwt3' };
const hub2 = { querySelector: (s) => s === '.lwt-pop' ? null : (s === '[data-ev-pid="lwt3"]' ? el : null) };
render({ shadowRoot: { querySelector: (s) => s === '.lwt-hub' ? hub2 : null } }, 0);
out.timers = timers.length;
timers.forEach((f) => f());
out.shown = shown;
// expired pop-up: nothing scheduled
timers.length = 0;
win.__lwtOpenPop = { pid: 'lwt3', until: Date.now() - 1 };
render(self, 0);
out.expired_timers = timers.length;
// ids are stable across renders
out.ids_a = (render(self, 0).match(/data-ev-pid="(lwt\d+)"/g) || []).join(',');
out.ids_b = (render(self, 0).match(/data-ev-pid="(lwt\d+)"/g) || []).join(',');
win.__lwtView = 'advice';
out.lower = render(self, -2);
out.raise = render(self, 2);
out.optimal = render(self, 0);
process.stdout.write(JSON.stringify(out));
"""


def _blocks() -> tuple[str, str]:
    src = CARD.read_text(encoding="utf-8")
    blocks = re.findall(r"\[\[\[(.*?)\]\]\]", src, re.S)
    tap = next(b for b in blocks if "evAction" in b and "__lwtView = arg" in b)
    content = next(b for b in blocks if "buildAdvies" in b and "return out;" in b)
    return tap, content


@pytest.fixture(scope="module")
def run() -> dict:
    if not shutil.which("node"):
        pytest.skip("node not installed")
    tap, content = _blocks()
    proc = subprocess.run(
        ["node", "-e", RUNNER], input=json.dumps({"tap": tap, "content": content}),
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _view(html: str) -> str:
    m = re.search(r'class="lwt-hub[^"]*"[^>]*data-view="(\w+)"', html)
    assert m, html[:400]
    return m.group(1)


def _advice_box(html: str) -> str:
    start = html.index('data-view="advice">')
    return html[start:html.index('data-view="buckets">')]


def test_renders_without_error(run):
    assert "Error:" not in run["first"]
    assert _view(run["first"]) == "advice"
    assert _view(run["default_tab"]) == "analysis"


def test_tab_survives_rerender(run):
    assert run["hub_view"] == "live"
    assert _view(run["after_click"]) == "live"
    assert re.search(r'lwt-btn lwt-btn-active" data-ev-action="view" data-ev-arg="live"',
                     run["after_click"])


def test_open_popup_is_shown_again(run):
    assert run["timers"] >= 1
    assert len(run["shown"]) == 1 and run["shown"][0]["pid"] == "lwt3"
    assert 500 <= run["shown"][0]["ms"] <= 4000
    assert run["expired_timers"] == 0


def test_popup_ids_stable(run):
    assert run["ids_a"] and run["ids_a"] == run["ids_b"]


def test_colours(run):
    lower, raise_, optimal = (_advice_box(run[k]) for k in ("lower", "raise", "optimal"))
    assert f"fill:{BLUE}" in lower.replace(" ", "") and "rgba(0,151,224,0.1)" in lower
    assert f"fill:{RED}" in raise_.replace(" ", "")
    assert "rgba(46,125,50,0.1)" in optimal and f"fill:{RED}" not in optimal.replace(" ", "")
