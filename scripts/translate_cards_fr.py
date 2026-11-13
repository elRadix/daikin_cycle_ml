"""Add French (fr) to the dashboard cards (azsono03 fork).

Run from the repo root:  python3 scripts/translate_cards_fr.py
Idempotent: a card that already contains the FR marker is skipped.

How it works (no change for EN/NL users):
- a French dictionary FRM (English text -> French) and a helper FR(x)
  are injected next to each card's language detection; FR(x) returns
  the French text only when LANG === 'fr', otherwise x unchanged;
- LANG becomes 'fr' when the integration's notification language is
  French (or lang_override: 'fr');
- every English literal of a `LANG==='nl' ? <nl> : <en>` ternary is
  wrapped in FR(...);  `{nl:..., en:...}` tables and STR/T dictionaries
  get their French through FR / a translated copy of the `en` table;
- Jinja headers get an `{% elif l == 'fr' %}` branch.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from translate_cards_fr_map import FRM

MARK = "/* FR-I18N (azsono03) */"
QRE = re.compile(r"'((?:[^'\\]|\\.)*)'")
CARDS = Path("dashboard/cards")


def helper(indent: str) -> str:
    frm = json.dumps(FRM, ensure_ascii=False, separators=(",", ":"))
    return (
        f"{indent}{MARK}\n"
        f"{indent}var FRM={frm};\n"
        f"{indent}var FR=function(x){{ return (LANG==='fr' && typeof x==='string' && Object.prototype.hasOwnProperty.call(FRM,x)) ? FRM[x] : x; }};\n"
        f"{indent}var FRO=function(o){{ if(typeof o==='string') return Object.prototype.hasOwnProperty.call(FRM,o)?FRM[o]:o; if(o&&typeof o==='object'){{ var r=Array.isArray(o)?[]:{{}}; for(var k in o){{ r[k]=FRO(o[k]); }} return r; }} return o; }};\n"
    )


def _skip_str(s: str, i: int) -> int:
    q = s[i]
    i += 1
    while s[i] != q:
        if s[i] == "\\":
            i += 1
        i += 1
    return i + 1


def wrap_ternaries(s: str) -> str:
    """Wrap English literals of LANG==='nl' ? A : B in FR(...)."""
    spans = []
    for m in re.finditer(r"LANG\s*===?\s*'nl'\s*\?", s):
        i, depth, n = m.end(), 0, len(s)
        while i < n:
            c = s[i]
            if c in "'\"":
                i = _skip_str(s, i)
                continue
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == ":" and depth == 0:
                break
            i += 1
        start = i = i + 1
        depth = 0
        while i < n:
            c = s[i]
            if c in "'\"":
                i = _skip_str(s, i)
                continue
            if c in "([{":
                depth += 1
            elif c in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif c in ",;\n" and depth == 0:
                break
            i += 1
        spans.append((start, i))
    for a, b in reversed(spans):
        seg = s[a:b]

        def repl(m, seg=seg):
            after = seg[m.end():m.end() + 2].lstrip()
            before = seg[max(0, m.start() - 3):m.start()]
            if after.startswith(":") or before.endswith("FR("):
                return m.group(0)
            if not re.search("[A-Za-z]{2}", m.group(1)):
                return m.group(0)
            return f"FR({m.group(0)})"

        s = s[:a] + QRE.sub(repl, seg) + s[b:]
    return s


def insert_before(s: str, needle: str, extra_fn) -> str:
    idx = s.index(needle)
    line_start = s.rfind("\n", 0, idx) + 1
    indent = re.match(r"\s*", s[line_start:]).group(0)
    return s[:line_start] + extra_fn(indent) + s[line_start:]


def insert_after_stmt(s: str, needle: str, extra_fn) -> str:
    idx = s.index(needle)
    end = s.index(";", idx) + 1
    end = s.index("\n", end) + 1
    line_start = s.rfind("\n", 0, idx) + 1
    indent = re.match(r"\s*", s[line_start:]).group(0)
    return s[:end] + extra_fn(indent) + s[end:]


def jinja_fr(s: str, fr_text: str) -> str:
    """Add {% elif l == 'fr' %} before the first {% else %} after {% if l == 'nl' %}."""
    i = s.index("{% if l == 'nl' %}")
    m = re.compile(r"\{%\s*else\s*%\}").search(s, i)
    return s[:m.start()] + "{% elif l == 'fr' %}" + fr_text + s[m.start():]


def simple_card(s: str) -> str:
    s = s.replace("in ['nl','en'] else", "in ['nl','en','fr'] else")
    s = jinja_fr(s, "Cycle en direct · COP · qualité · alertes")
    s = s.replace("var LANG_OVERRIDE = 'EN';", "var LANG_OVERRIDE = '';")
    s = s.replace("/* LANG_OVERRIDE: '' = auto from integration, 'nl' = force NL, 'en' = force EN */",
                  "/* LANG_OVERRIDE: '' = auto from integration, 'nl' / 'en' / 'fr' = force */")
    s = s.replace(
        "            : (cfgLangRaw === 'nl' ? 'nl' : 'en');",
        "            : (cfgLangRaw === 'nl' ? 'nl' : 'en');\n"
        "          if (LANG_OVERRIDE === 'fr' || (LANG_OVERRIDE === '' && cfgLangRaw === 'fr')) { LANG = 'fr'; }",
    )
    s = insert_before(s, "var t = function(k){ return (STR[LANG]",
                      lambda ind: helper(ind) + f"{ind}STR.fr = FRO(STR.en);\n")
    return wrap_ternaries(s)


def heating_curve(s: str) -> str:
    s = jinja_fr(s, "📈 Loi d'eau — départ / extérieur · carte COP · modes · bilan")
    s = s.replace("var LANG = (cfgLang === 'nl') ? 'nl' : 'en';",
                  "var LANG = (cfgLang === 'nl') ? 'nl' : (cfgLang === 'fr' ? 'fr' : 'en');")
    s = insert_before(s, "var t = function(k){ return (STR[LANG]",
                      lambda ind: helper(ind) + f"{ind}STR.fr = FRO(STR.en);\n")
    s = insert_before(s, "var t = function(k){ return (T[LANG]",
                      lambda ind: helper(ind) + f"{ind}T.fr = FRO(T.en);\n")
    return wrap_ternaries(s)


def _lang_block_fr(s: str) -> str:
    s = s.replace(
        "if (cfgLangOvr === 'nl' || cfgLangOvr === 'en') { LANG = cfgLangOvr; }",
        "if (cfgLangOvr === 'nl' || cfgLangOvr === 'en' || cfgLangOvr === 'fr') { LANG = cfgLangOvr; }",
    )
    s = s.replace(
        "else if (cfgLang === 'nl') { LANG = 'nl'; }",
        "else if (cfgLang === 'nl') { LANG = 'nl'; }\n"
        "            else if (cfgLang === 'fr' || haLang.indexOf('fr') === 0) { LANG = 'fr'; }",
    )
    s = insert_after_stmt(s, "else if (cfgLang === 'fr' || haLang", lambda ind: helper(ind))
    s = s.replace(
        "var t = function(k){ var e=I18N[k]; if(!e) return k; return e[LANG] || e.en || e.nl; };",
        "var t = function(k){ var e=I18N[k]; if(!e) return k; if(LANG==='fr') return e.fr || FR(e.en || e.nl); return e[LANG] || e.en || e.nl; };",
    )
    return s


def tabbed(s: str) -> str:
    s = s.replace("📅 DAIKIN CYCLE ML — SUMMARY",
                  "📅 DAIKIN CYCLE ML — {{ 'RÉSUMÉ' if state_attr('sensor.daikin_cycle_ml_cycle_state','configured_language') == 'fr' else 'SUMMARY' }}")
    s = jinja_fr(s, "Cycles · durée · qualité · événements")
    s = _lang_block_fr(s)
    s = s.replace("['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][d.getDay()]",
                  "(LANG==='fr'?['dim','lun','mar','mer','jeu','ven','sam']:['Sun','Mon','Tue','Wed','Thu','Fri','Sat'])[d.getDay()]")
    s = s.replace("tile('🔄', 'Starts', String(startsT)", "tile('🔄', FR('Starts'), String(startsT)")
    return wrap_ternaries(s)


def pattern(s: str) -> str:
    s = s.replace("🎯 DAIKIN CYCLE ML — PATTERN ANALYSIS",
                  "🎯 DAIKIN CYCLE ML — {{ 'ANALYSE DES CYCLES' if state_attr('sensor.daikin_cycle_ml_cycle_state','configured_language') == 'fr' else 'PATTERN ANALYSIS' }}")
    s = jinja_fr(s, "Répartition · cycles / durée · efficacité COP")
    s = _lang_block_fr(s)
    s = s.replace("['zo','ma','di','wo','do','vr','za'][d.getDay()]",
                  "(LANG==='fr'?['dim','lun','mar','mer','jeu','ven','sam']:['zo','ma','di','wo','do','vr','za'])[d.getDay()]")
    return wrap_ternaries(s)


def cop_energy(s: str) -> str:
    ind = "            "
    s = s.replace(
        "var T=function(n,e){return NL?n:e;};",
        "var A0=function(e,k){var x=states[e];return (x&&x.attributes)?x.attributes[k]:null;};\n"
        + ind + "var LANG=NL?'nl':((lv==='fr'||(lv===''&&(hl.indexOf('fr')===0||String(A0('sensor.daikin_cycle_ml_cycle_state','configured_language'))==='fr')))?'fr':'en');\n"
        + helper(ind)
        + ind + "var T=function(n,e){return NL?n:FR(e);};",
    )
    s = s.replace("toLocaleString(NL?'nl-BE':'en-US')", "toLocaleString(NL?'nl-BE':(LANG==='fr'?'fr-FR':'en-US'))")
    s = s.replace("COP & Energie{%- else -%}COP · Energie · live",
                  "{{ 'COP et énergie' if state_attr('sensor.daikin_cycle_ml_cycle_state','configured_language') == 'fr' else 'COP & Energie' }}{%- else -%}COP · Energie · live")
    return s


EXTRA = {
    "cop-energy/cop-energy.yaml": [
        ("'+C.mu+'\">30d <b", "'+C.mu+'\">'+T('30d','30d')+' <b"),
        ("{ic:'💧',nm:'DHW',", "{ic:'💧',nm:T('SWW','DHW'),"),
        ("cm==='dhw'?'DHW':", "cm==='dhw'?T('SWW','DHW'):"),
        ("lastMode==='dhw'?'DHW':", "lastMode==='dhw'?T('SWW','DHW'):"),
        ("renderModeCard('💧', 'DHW',", "renderModeCard('💧', T('SWW','DHW'),"),
        ("'\">week <b", "'\">'+T('week','week')+' <b"),
        ("'\">365d <b", "'\">'+T('365d','365d')+' <b"),
    ],
    "daily-summary-tabbed/daily-summary-tabbed.yaml": [
        ("+' cycli · '+fmtBigHours", "+(LANG==='fr'?' cycles · ':' cycli · ')+fmtBigHours"),
        ("dhw:{ic:'🚿', col:C.dhw, nm:'DHW'}", "dhw:{ic:'🚿', col:C.dhw, nm:FR('DHW')}"),
        ("name:'DHW',", "name:FR('DHW'),"),
    ],
    "pattern-analysis/pattern-analysis.yaml": [
        ("'SHORT 20-60m')", "FR('SHORT 20-60m'))"),
        ("'GOOD 60-180m')", "FR('GOOD 60-180m'))"),
        ("'LONG >180m')", "FR('LONG >180m'))"),
        ("{t:'kv',k:'Last 7d',", "{t:'kv',k:FR('Last 7d'),"),
        ("{label:'PENDEL', sub:'<20m'", "{label:(LANG==='fr'?'TROP COURT':'PENDEL'), sub:'<20m'"),
        ("{label:'KORT', sub:'20-60m'", "{label:(LANG==='fr'?'COURT':'KORT'), sub:'20-60m'"),
        ("{label:'GOED', sub:'60-180m'", "{label:(LANG==='fr'?'BON':'GOED'), sub:'60-180m'"),
        ("{label:'LANG', sub:'>180m'", "{label:(LANG==='fr'?'LONG':'LANG'), sub:'>180m'"),
    ],
}

JOBS = {
    "simple-card/simple-card.yaml": simple_card,
    "heating-curve/heating-curve.yaml": heating_curve,
    "daily-summary-tabbed/daily-summary-tabbed.yaml": tabbed,
    "pattern-analysis/pattern-analysis.yaml": pattern,
    "cop-energy/cop-energy.yaml": cop_energy,
}

if __name__ == "__main__":
    for rel, fn in JOBS.items():
        p = CARDS / rel
        raw = p.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        src = raw.replace("\r\n", "\n")
        if MARK in src:
            print("skip (already FR):", rel)
            continue
        out = fn(src)
        if rel.startswith(("daily-summary-tabbed", "pattern-analysis")):
            out = re.sub(r"\+'d'", "+(LANG==='fr'?' j':'d')", out)
            out = re.sub(r"\+(\w+(?:\.\w+)?)\+'d<", r"+\1+(LANG==='fr'?' j':'d')+'<", out)
        for old, new in EXTRA.get(rel, []):
            if old not in out:
                raise SystemExit(f"pattern not found in {rel}: {old}")
            out = out.replace(old, new)
        if crlf:
            out = out.replace("\n", "\r\n")
        p.write_bytes(out.encode("utf-8"))
        print("FR added:", rel)
