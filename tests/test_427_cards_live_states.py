"""#427: every dashboard card against the states the integration really writes.

``tests/fixtures/card_states_427.json`` is a dump of all sensor and
binary_sensor states after the real integration ran ~38 h of simulated
operation (heating runs, DHW splits, defrost, BUH, a short run) on a real
database. Regenerate it with::

    DCML_DUMP_CARD_STATES=1 TZ=Europe/Amsterdam pytest --no-cov --timeout=0 \\
        tests/test_427_cards_live_states.py -k dump

Each card's JavaScript is executed under Node for EN, NL and FR (entity ids
in that language, ``configured_language`` and HA language set to it). The
tests pin: no errors / undefined / NaN, no words of another language, the
decimal separator of the language, and the data fixes of #427.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import sensor as s_mod
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from homeassistant.util import slugify

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/card_states_427.json"
CARDS = sorted((ROOT / "dashboard/cards").glob("*/*.yaml"))
COMP = ROOT / "custom_components/daikin_cycle_ml"
LANGS = ("en", "nl", "fr")
TR = {
    lang: json.loads((COMP / f"translations/{lang}.json").read_text(encoding="utf-8"))["entity"]
    for lang in LANGS
}

RUNNER = r"""
const vm = require('vm');
const D = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const NOW = Date.parse(D.now);
const out = {};
for (const [name, blocks] of Object.entries(D.cards)) {
  out[name] = blocks.map((body) => {
    const hass = { language: D.lang, locale: { language: D.lang }, states: D.states, entities: D.entities,
                   user: { name: 'u', is_admin: true }, themes: { darkMode: false } };
    const FD = class extends Date { constructor(...a) { if (a.length) super(...a); else super(NOW); }
                                    static now() { return NOW; } };
    const ctx = vm.createContext({ Date: FD, Math, JSON, Object, Array, String, Number, parseFloat, parseInt,
      isNaN, isFinite, encodeURIComponent, decodeURIComponent, RegExp, Error, Intl, Set, Map,
      setTimeout: () => 0, clearTimeout: () => 0, requestAnimationFrame: () => 0,
      console: { log() {}, warn() {}, error() {} }, window: {} });
    const fn = vm.runInContext('(function(hass,states,entity,user,variables,html,helpers){' + body + '\n})', ctx);
    try {
      const o = fn.call({ _config: {} }, hass, D.states, undefined, hass.user, {},
                        (s, ...v) => s.map((x, i) => x + (i < v.length ? v[i] : '')).join(''), {});
      return typeof o === 'string' ? o : JSON.stringify(o);
    } catch (e) { return 'THROW: ' + e.message; }
  });
}
process.stdout.write(JSON.stringify(out));
"""


def _oid(lang: str, plat: str, key: str) -> str:
    return slugify(f"Daikin Cycle ML {TR[lang][plat][key]['name']}")


def _localized(dump: dict, lang: str) -> dict:
    """States + registry entries with entity ids as HA creates them in ``lang``."""
    ids = {
        f"{plat}.{_oid('en', plat, key)}": (f"{plat}.{_oid(lang, plat, key)}", key)
        for plat in ("sensor", "binary_sensor") for key in TR["en"][plat]
    }
    states, ents = {}, {}
    for eid, st in dump["states"].items():
        new, key = ids.get(eid, (eid, None))
        st = json.loads(json.dumps(st))
        st["entity_id"] = new
        if "configured_language" in st["attributes"]:
            st["attributes"]["configured_language"] = lang
        states[new] = st
        if key:
            ents[new] = {"platform": "daikin_cycle_ml", "translation_key": key}
    return {"now": dump["now"], "states": states, "entities": ents}


def _text(out: str) -> str:
    t = re.sub(r"<style.*?</style>", "", out, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(re.sub(r"\s+", " ", t))


@pytest.fixture(scope="module")
def rendered() -> dict[str, dict[str, list[str]]]:
    if not shutil.which("node"):
        pytest.skip("node not installed")
    dump = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cards = {
        c.parent.name: re.findall(r"\[\[\[(.*?)\]\]\]", c.read_text(encoding="utf-8"), re.S)
        for c in CARDS
    }
    res = {}
    for lang in LANGS:
        payload = {**_localized(dump, lang), "lang": lang, "cards": cards}
        proc = subprocess.run(
            ["node", "-e", RUNNER], input=json.dumps(payload), capture_output=True,
            text=True, timeout=120, check=False,
        )
        assert proc.returncode == 0, proc.stderr
        res[lang] = json.loads(proc.stdout)
    return res


def _card_text(rendered: dict, lang: str, card: str) -> str:
    return " ".join(_text(o) for o in rendered[lang][card] if isinstance(o, str))


def test_fixture_is_real_integration_output():
    st = json.loads(FIXTURE.read_text(encoding="utf-8"))["states"]
    summary = st["sensor.daikin_cycle_ml_daily_summary_recent"]["attributes"]
    assert summary["events_by_day"], "events_by_day must be exposed (#427)"
    assert int(st["sensor.daikin_cycle_ml_cycles_today"]["state"]) >= 5
    assert st["sensor.daikin_cycle_ml_last_cycle"]["attributes"]["dt_avg_k"] is not None


BAD = re.compile(r"undefined|NaN|\[object Object\]|THROW|Infinity|Error:")


@pytest.mark.parametrize("lang", LANGS)
def test_cards_render_without_errors(rendered, lang):
    for card, outs in rendered[lang].items():
        for i, out in enumerate(outs):
            if not isinstance(out, str):
                continue
            hit = BAD.search(_text(out))
            assert hit is None, f"{card}[{i}] {lang}: {_text(out)[max(0, hit.start() - 80):hit.end() + 40]}"


FOREIGN = {
    # words that must not appear in the other languages (whole words, case sensitive)
    "en": r"\b(cycli|dagen|Verwarming|Kwaliteit|geleden|vandaag|Slechtste|drempel|pendel|ideaal|KWAL|jours|Chauffage|Qualité|\d+u\d\d)\b",
    "nl": r"\b(very reliable|Event counts|COP PERFORMANCE|MODE BREAKDOWN|SYSTEM HEALTH|Short runs|Avg off|Cycles vs|CYCLES PER|target|jours|Chauffage)\b",
    "fr": r"\b(cycli|dagen|Verwarming|Kwaliteit|pendel|ideaal|very reliable|COP PERFORMANCE|MODE BREAKDOWN|SYSTEM HEALTH|Heating|running|keep|\d+u\d\d)\b",
}


@pytest.mark.parametrize("lang", LANGS)
def test_no_words_of_another_language(rendered, lang):
    for card in rendered[lang]:
        text = _card_text(rendered, lang, card)
        hits = sorted({m.group(0) for m in re.finditer(FOREIGN[lang], text)})
        assert not hits, f"{card} ({lang}): {hits}"


def test_decimal_separator_follows_language(rendered):
    cop = json.loads(FIXTURE.read_text(encoding="utf-8"))["states"]["sensor.daikin_cycle_ml_cop_mean_day"]["state"]
    en = f"{float(cop):.2f}"
    for card in ("cop-energy",):
        assert en in _card_text(rendered, "en", card)
        assert en.replace(".", ",") in _card_text(rendered, "nl", card)
        assert en.replace(".", ",") in _card_text(rendered, "fr", card)


def test_simple_card_last_cycle_and_quality(rendered):
    st = json.loads(FIXTURE.read_text(encoding="utf-8"))["states"]
    dt = float(st["sensor.daikin_cycle_ml_last_cycle"]["attributes"]["dt_avg_k"])
    q = round(float(st["sensor.daikin_cycle_ml_quality_today"]["state"]))
    text = _card_text(rendered, "en", "simple-card")
    assert f"ΔT {dt:.1f}K" in text                       # was "—" (read avg_dt_k)
    assert f"Q {q} " in text                              # quality score, not the ratio
    assert "Mode heating" in text and "Phase · running" in text
    nl = _card_text(rendered, "nl", "simple-card")
    assert "Modus verwarmen" in nl and "Fase · draait" in nl


def test_daily_summary_follows_language(rendered):
    assert "cycles" in _card_text(rendered, "en", "daily-summary")
    assert "cycli" in _card_text(rendered, "nl", "daily-summary")
    assert "jours" in _card_text(rendered, "fr", "daily-summary")


def test_event_charts_use_events_by_day(rendered):
    summary = json.loads(FIXTURE.read_text(encoding="utf-8"))["states"][
        "sensor.daikin_cycle_ml_daily_summary_recent"]["attributes"]
    per_cycle: dict[str, int] = {}
    for d in summary["days"]:
        per_cycle[d["day"]] = per_cycle.get(d["day"], 0) + d["defrost"]
    events = {d: summary["events_by_day"].get(d, {}).get("defrost_events", 0) for d in per_cycle}
    # today: 4 defrost events, but only 3 cycles started today had one
    assert any(events[d] > per_cycle[d] for d in per_cycle)
    expected = sum(max(per_cycle[d], events[d]) for d in per_cycle)
    assert expected != sum(per_cycle.values())
    text = _card_text(rendered, "en", "daily-summary")
    assert f"{expected} Defrost" in text


def test_lwt_card_tracking_without_data(rendered):
    text = _card_text(rendered, "en", "lwt-fine-tuning")
    assert "No data yet" in text and "Very good" not in text


# --------------------------------------------------------------------------
# Fixture generator (runs the real integration; opt-in, ~4 min)
# --------------------------------------------------------------------------

SRC = "sensor.althermasensors"
PWR = "sensor.hp_power"


def _source(mode: str, outdoor: float) -> tuple[dict, float]:
    on = mode != "off"
    dhw, defrost, buh = mode == "dhw", mode == "defrost", mode == "buh"
    lwt = 50.0 if dhw else (33.0 if on else 27.0)
    inlet = 45.0 if dhw else (29.0 if on else 27.0)
    if defrost:
        lwt, inlet = 24.0, 27.0
    attrs = {
        "INV frequency (rps)": (45 if dhw else 32) if on else 0,
        "Operation Mode": "Heating",
        "I/U operation mode": "DHW" if dhw else ("Heating" if on else "Stop"),
        "3way valve(On:DHW_Off:Space)": 1 if dhw else 0,
        "Defrost Operation": defrost,
        "Leaving water temp. after BUH (R2T)": lwt + (3 if buh else 0),
        "Leaving water temp. before BUH (R1T)": lwt,
        "Inlet water temp.(R4T)": inlet,
        "Outdoor air temp.(R1T)": outdoor,
        "Flow sensor (l/min)": 18.0 if on else 0.0,
        "Water pump operation": on,
        "BUH Step1": buh,
        "BUH Step2": False,
        "LW setpoint (main)": 34.0,
    }
    power = ((1400.0 if dhw else 950.0) + (3000.0 if buh else 0.0)) if on else 25.0
    return attrs, power


def _mode_at(t: datetime) -> str:
    """180 min on / 20 off, DHW at 06:00 and 18:00, a short run at 11:05,
    a defrost in every run, 3 min BUH at 07:00."""
    m = t.hour * 60 + t.minute
    if 6 * 60 <= m < 6 * 60 + 40 or 18 * 60 <= m < 18 * 60 + 35:
        return "dhw"
    if 11 * 60 + 5 <= m < 11 * 60 + 13:
        return "heating"
    if 11 * 60 <= m < 11 * 60 + 30:
        return "off"
    blk = m % 200
    if blk >= 180:
        return "off"
    if 90 <= blk < 96:
        return "defrost"
    if t.hour == 7 and t.minute < 3:
        return "buh"
    return "heating"


@pytest.mark.skipif(not os.environ.get("DCML_DUMP_CARD_STATES"), reason="fixture generator")
async def test_dump_card_states(hass, freezer):  # pragma: no cover - generator
    import glob

    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_fire_time_changed,
    )

    from custom_components.daikin_cycle_ml.const import DOMAIN
    from homeassistant.helpers import entity_registry as er
    from homeassistant.util import dt as dt_util

    await hass.config.async_set_time_zone("Europe/Amsterdam")
    tz = dt_util.get_default_time_zone()
    start = datetime(2026, 11, 17, 0, 0, tzinfo=tz)
    end = datetime(2026, 11, 19, 14, 0, tzinfo=tz)
    freezer.move_to(start)
    for f in glob.glob(os.path.join(hass.config.config_dir, ".storage", "daikin_cycle_ml*")):
        os.remove(f)
    attrs, power = _source("off", 6.0)
    hass.states.async_set(SRC, "Online", attrs)
    hass.states.async_set(PWR, str(power), {"unit_of_measurement": "W", "device_class": "power"})
    entry = MockConfigEntry(domain=DOMAIN, entry_id="cardtest",
                            data={"source_sensor": SRC, "model": "epra12eav3"},
                            options={"power_sensor_entity": PWR})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = entry.runtime_data
    t, n = start, 0
    while t < end:
        n += 1
        t += timedelta(seconds=30)
        freezer.move_to(t)
        outdoor = round(10 - (4.0 + 5.0 * abs(((t.hour * 60 + t.minute) / 720.0) - 1.0)), 1)
        attrs, power = _source(_mode_at(t), outdoor)
        hass.states.async_set(SRC, "Online", attrs)
        hass.states.async_set(PWR, str(power), {"unit_of_measurement": "W", "device_class": "power"})
        await hass.async_block_till_done()
        await coord.async_refresh()
        if n % 30 == 0:
            async_fire_time_changed(hass, t)
            await hass.async_block_till_done()
    reg = er.async_get(hass)
    states, ents = {}, {}
    for st in hass.states.async_all():
        if st.entity_id.startswith(("sensor.daikin_cycle_ml", "binary_sensor.daikin_cycle_ml")):
            states[st.entity_id] = {
                "entity_id": st.entity_id, "state": st.state,
                "attributes": json.loads(json.dumps(dict(st.attributes), default=str)),
            }
            e = reg.async_get(st.entity_id)
            if e:
                ents[st.entity_id] = {"platform": e.platform, "translation_key": e.translation_key}
    FIXTURE.write_text(json.dumps({"now": t.isoformat(), "states": states, "entities": ents},
                                  ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


# --------------------------------------------------------------------------
# Sensor: events_by_day is exposed, limited to the summary window
# --------------------------------------------------------------------------


def test_daily_summary_sensor_exposes_events_by_day():
    c = MagicMock()
    c.daily_summary_recent = {
        "oldest_day": "2026-11-17", "latest_day": "2026-11-19",
        "events_by_day": {
            "2026-11-19": {"buh_min": 3.0, "defrost_events": 4},
            "2026-10-01": {"buh_min": 9.0, "defrost_events": 9},   # outside the window
            "2026-11-17": {"buh_min": 0.0, "defrost_events": 6},
        },
    }
    out = s_mod._attrs_daily_summary_recent(DataSnapshot(), c)
    assert list(out["events_by_day"]) == ["2026-11-17", "2026-11-19"]
    c.daily_summary_recent = {"events_by_day": {"2026-11-19": {"defrost_events": 1}}}
    assert s_mod._attrs_daily_summary_recent(DataSnapshot(), c)["events_by_day"] == {
        "2026-11-19": {"defrost_events": 1}}
    c.daily_summary_recent = None
    assert s_mod._attrs_daily_summary_recent(DataSnapshot(), c)["events_by_day"] == {}
