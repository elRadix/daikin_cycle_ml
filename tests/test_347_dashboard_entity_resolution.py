"""#347 / #369: dashboard cards must work regardless of entity_id language.

HA derives entity_ids from the translated entity name in the language
active when the entities were first created. A Dutch install gets
``sensor.daikin_cycle_ml_cyclus_status`` instead of
``sensor.daikin_cycle_ml_cycle_state``; French gets
``sensor.daikin_cycle_ml_etat_du_cycle``. Cards that hard-coded the
English ids rendered empty on non-English installs.

These tests pin:
  * no bare entity-id literal left in any button-card JS block;
  * every alias table matches the shipped translations (drift guard);
  * Jinja headers resolve EN / NL / FR ids identically (real HA engine);
  * every JS block renders identically for EN / NL / FR / renamed ids
    (executed under Node when available).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import entity_sources
from homeassistant.helpers.template import Template
from homeassistant.util import slugify

ROOT = Path(__file__).resolve().parent.parent
CARDS = sorted((ROOT / "dashboard/cards").glob("*/*.yaml"))
COMP = ROOT / "custom_components/daikin_cycle_ml"
PREF = "daikin_cycle_ml_"
LANGS = ("en", "nl", "fr")
TR = {
    lang: json.loads((COMP / f"translations/{lang}.json").read_text(encoding="utf-8"))[
        "entity"
    ]
    for lang in LANGS
}
LIT = re.compile(r"'((?:binary_sensor|sensor)\.daikin_cycle_ml_[a-z0-9_]+)'")


def _oid(lang: str, plat: str, key: str) -> str:
    return slugify(f"Daikin Cycle ML {TR[lang][plat][key]['name']}")


def _expected() -> dict[str, list[str]]:
    """EN entity_id -> [translation_key, nl object_id, fr object_id]."""
    out = {}
    for plat in ("sensor", "binary_sensor"):
        for key in TR["en"][plat]:
            out[f"{plat}.{_oid('en', plat, key)}"] = [
                key, _oid("nl", plat, key), _oid("fr", plat, key),
            ]
    return out


EXPECTED = _expected()


def _src(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _js_blocks(path: Path) -> list[str]:
    return re.findall(r"\[\[\[(.*?)\]\]\]", _src(path), re.S)


# --------------------------------------------------------------------------
# Static guards
# --------------------------------------------------------------------------


def test_cards_found():
    assert len(CARDS) >= 7


@pytest.mark.parametrize("card", CARDS, ids=lambda p: p.parent.name)
def test_no_bare_entity_literal_in_js(card: Path):
    """Every quoted entity id in JS must go through _dcmR()."""
    bad = []
    for block in _js_blocks(card):
        for m in LIT.finditer(block):
            if block[max(0, m.start() - 6): m.start()] != "_dcmR(":
                bad.append(m.group(1))
    assert not bad, f"{card.parent.name}: unresolved literals {sorted(set(bad))}"


@pytest.mark.parametrize("card", CARDS, ids=lambda p: p.parent.name)
def test_alias_tables_match_translations(card: Path):
    """_dcmA / REGISTRY / _DCM_TK entries track translations/*.json."""
    src = _src(card)
    for raw in re.findall(r"var _dcmA = (\{.*?\});\n", src):
        for eid, val in json.loads(raw).items():
            assert eid in EXPECTED, eid
            k, nl, fr = EXPECTED[eid]
            assert val == [k, nl[len(PREF):], fr[len(PREF):]] or val == [k, nl, fr], eid
    for raw in re.findall(r"var _DCM_TK = (\{.*?\});", src):
        for slug, key in json.loads(raw).items():
            eid = f"sensor.{PREF}{slug}"
            assert EXPECTED[eid][0] == key, slug
    if "var resolveEntity" in src:
        for names in re.findall(r"^\s*\w+:\s*\[('[^\]\n]*')\]", src, re.M):
            lst = re.findall(r"'([^']+)'", names)
            eid = f"sensor.{PREF}{lst[0]}"
            if eid not in EXPECTED:
                continue
            _k, nl, fr = EXPECTED[eid]
            assert nl[len(PREF):] in lst and fr[len(PREF):] in lst, lst


def test_dcm_resolver_alias_format_is_full_object_id():
    """_dcmR builds `domain + '.' + alias`, so aliases carry the prefix."""
    for card in CARDS:
        for raw in re.findall(r"var _dcmA = (\{.*?\});\n", _src(card)):
            for val in json.loads(raw).values():
                assert val[1].startswith(PREF) and val[2].startswith(PREF)


# --------------------------------------------------------------------------
# Jinja headers: real HA template engine
# --------------------------------------------------------------------------


def _jinja_strings(card: Path) -> list[str]:
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str) and ("{{" in node or "{%" in node) and "[[[" not in node:
            found.append(node)

    walk(yaml.safe_load(_src(card)))
    return found


JINJA = [(c, s) for c in CARDS for s in _jinja_strings(c)]


def _register(hass: HomeAssistant, lang: str, model: str = "erga08eav3") -> None:
    reg = er.async_get(hass)
    sources = entity_sources(hass)  # what integration_entities() reads at runtime
    sources.clear()
    for eid in list(hass.states.async_entity_ids()):
        hass.states.async_remove(eid)
    for ent in list(reg.entities.values()):
        reg.async_remove(ent.entity_id)
    for plat in ("sensor", "binary_sensor"):
        for key in TR["en"][plat]:
            entry = reg.async_get_or_create(
                plat, "daikin_cycle_ml", f"uid_{lang}_{key}",
                suggested_object_id=_oid(lang, plat, key),
                translation_key=key,
            )
            assert entry.entity_id == f"{plat}.{_oid(lang, plat, key)}", entry.entity_id
            sources[entry.entity_id] = {"domain": "daikin_cycle_ml"}
            hass.states.async_set(
                entry.entity_id, "1",
                {"configured_language": "fr", "model": model, "family": "Altherma",
                 "kw": 8, "refrigerant": "R32"},
            )


@pytest.mark.parametrize(
    "card,tpl", JINJA, ids=[f"{c.parent.name}-{i}" for i, (c, _s) in enumerate(JINJA)]
)
async def test_jinja_header_language_independent(hass: HomeAssistant, card: Path, tpl: str):
    """Header renders the same for EN, NL and FR entity ids."""
    out = {}
    for lang in LANGS:
        _register(hass, lang)
        await hass.async_block_till_done()
        out[lang] = Template(tpl, hass).async_render(parse_result=False)
    assert out["nl"] == out["en"] and out["fr"] == out["en"], out
    if "configured_language" in tpl:
        # configured_language is "fr" in the fixture: a resolved header is French
        assert any(w in out["en"] for w in ("RÉSUMÉ", "ANALYSE", "Répartition", "énergie", "Loi d", "direct", "Cycles · durée")), out["en"]


async def test_jinja_header_resolves_french_language(hass: HomeAssistant):
    """Sanity: resolved cycle_state attr actually reaches the template."""
    card = ROOT / "dashboard/cards/pattern-analysis/pattern-analysis.yaml"
    tpl = next(s for s in _jinja_strings(card) if "ANALYSE DES CYCLES" in s)
    _register(hass, "nl", model="evlq08cv3")
    await hass.async_block_till_done()
    rendered = Template(tpl, hass).async_render(parse_result=False)
    assert "ANALYSE DES CYCLES" in rendered and "EVLQ08CV3" in rendered


# --------------------------------------------------------------------------
# JS blocks: executed under Node (skipped when node is unavailable)
# --------------------------------------------------------------------------

NODE_RUNNER = r"""
const vm = require('vm');
const D = JSON.parse(require('fs').readFileSync(0, 'utf8'));
function render(body, sc, noReg) {
  const hass = { language: 'en', states: sc.states, entities: noReg ? undefined : sc.entities,
                 user: { name: 'u', is_admin: true }, themes: { darkMode: false } };
  const FD = class extends Date { constructor(...a) { if (a.length) super(...a); else super('2026-11-17T12:00:00Z'); }
                                  static now() { return Date.parse('2026-11-17T12:00:00Z'); } };
  let seed = 1; const M = Object.create(Math);
  M.random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const ctx = vm.createContext({ Date: FD, Math: M, JSON, Object, Array, String, Number, parseFloat,
    parseInt, isNaN, isFinite, encodeURIComponent, decodeURIComponent, RegExp, Error,
    setTimeout: () => 0, clearTimeout: () => 0, requestAnimationFrame: () => 0,
    console: { log() {}, warn() {}, error() {} }, window: {} });
  const fn = vm.runInContext('(function(hass,states,entity,user,variables,html,helpers){' + body + '\n})', ctx);
  try { const o = fn.call({ _config: {} }, hass, sc.states, undefined, hass.user, { lang_override: '' },
                          (s) => s.join(''), {});
        return typeof o === 'string' ? o : String(JSON.stringify(o)); }
  catch (e) { return 'THROW: ' + e.message; }
}
function norm(s, map) { for (const id of Object.keys(map).sort((a, b) => b.length - a.length)) s = s.split(id).join(map[id]); return s; }
const res = [];
for (const body of D.blocks) {
  const en = render(body, D.scen.en, false);
  const r = { en_ok: !/THROW:/.test(en) };
  for (const k of ['nl', 'fr', 'renamed']) r[k] = norm(render(body, D.scen[k], false), D.maps[k]) === en;
  for (const k of ['nl', 'fr']) r[k + '_noreg'] = norm(render(body, D.scen[k], true), D.maps[k]) === en;
  res.push(r);
}
process.stdout.write(JSON.stringify(res));
"""


def _scenario(lang: str, renamed: bool = False) -> dict:
    states, ents, idx = {}, {}, 0
    for plat in ("sensor", "binary_sensor"):
        for key in TR["en"][plat]:
            eid = f"{plat}.my_heatpump_{idx}" if renamed else f"{plat}.{_oid(lang, plat, key)}"
            val = ("on" if idx % 2 else "off") if plat == "binary_sensor" else str(1.5 + idx / 4)
            attrs = {
                "configured_language": "en", "model": "erga08eav3", "family": "Altherma",
                "kw": 8, "refrigerant": "R32", "duration_min": 12.5, "n_samples": 40 + idx,
                "points": [{"t_out": t, "lwt": 30 + t / 3, "cop": 3 + t / 10} for t in range(-5, 15, 2)],
                "days": [{"date": f"2026-11-{d}", "cycles": d, "quality": 70 + d} for d in range(10, 18)],
                "days_available": 8, "bucket": "5..10", "buckets": {"5..10": {"n": 5}},
            }
            states[eid] = {"entity_id": eid, "state": val, "attributes": attrs}
            ents[eid] = {"entity_id": eid, "platform": "daikin_cycle_ml", "translation_key": key}
            idx += 1
    return {"states": states, "entities": ents}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("card", CARDS, ids=lambda p: p.parent.name)
def test_js_blocks_render_identically_across_languages(card: Path):
    scen = {k: _scenario(k) for k in LANGS}
    scen["renamed"] = _scenario("en", renamed=True)
    en_ids = list(scen["en"]["states"])
    maps = {k: dict(zip(scen[k]["states"], en_ids)) for k in ("nl", "fr", "renamed")}
    payload = json.dumps({"blocks": _js_blocks(card), "scen": scen, "maps": maps})
    proc = subprocess.run(
        ["node", "-e", NODE_RUNNER], input=payload, capture_output=True,
        text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for i, row in enumerate(json.loads(proc.stdout)):
        assert all(row.values()), f"{card.parent.name} block {i}: {row}"
