"""#435 / #198: resolve any Daikin model code a user knows to our model key.

Users often know only the code on their indoor unit or on the app
("EHBX08EF6V"), not the outdoor unit whose datasheet we hold
("ERGA06EAV3"). This module maps:

- outdoor codes and their variants (``ERGA06EAV3H7``, ``EPRA14DAV37``)
  to the model key, via the exact list, ``MODEL_ALIASES`` and a prefix
  match on the known keys;
- indoor / kit codes (wall-mounted, floor-standing, ECH2O, monobloc
  sub-variants) to the outdoor units they are sold with. One indoor size
  can pair with several outdoor sizes (an 08 indoor unit runs an ERGA06
  or an ERGA08): then the candidates are returned and the user picks.

Pairings follow the ESPAltherma definition names (data/as_numbers.json,
beta 3548ea2: "ERGA E EHV-EHB-EHVZ ... 04-08kW", "EPRA E ETV-ETB ...
8-12kW", ...) and Daikin's combination tables cited in datasheets.json.
Only datasheets not flagged as non-catalogue (``verified`` False) are
offered as candidates. Pure module: no Home Assistant imports.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..const import (
    MODEL_ALIASES,
    MODEL_BASISPROFIEL,
    MODEL_CHOICES,
    MODEL_CUSTOM,
)

# (indoor-code pattern, {size: candidate model keys}, series label)
# The pattern captures the indoor size; the series letter after the size
# (or after the tank / ECH2O part: S18, SU23, P30, ...) selects the range.
_TANK = r"(?:S\d{2}|SU\d{2}|P\d{2})?"
_INDOOR_RULES: list[tuple[re.Pattern[str], dict[str, list[str]], str]] = [
    # Altherma 3 R split, E series: EHBH/EHBX (wall), EHVH/EHVX/EHVZ
    # (floor-standing), EHSH/EHSX(B) (ECH2O) + ERGA04-08EAV3
    (
        re.compile(r"^[ER]H[BVS][HXZ]B?(04|08)" + _TANK + r"E"),
        {"04": ["erga04eav3"], "08": ["erga06eav3", "erga08eav3"]},
        "Altherma 3 R (ERGA E)",
    ),
    # Altherma 3 H MT, E series 8-12 kW: ETB/ETV/ETVZ/ETS, ELB/ELV/ELS
    (
        re.compile(r"^E[TL][BVS][HXZ]B?(12)" + _TANK + r"E"),
        {"12": ["epra08eav3", "epra10eav3", "epra12eav3"]},
        "Altherma 3 H MT (EPRA E 8-12 kW)",
    ),
    # Altherma 3 H HT, 14-18 kW (D and E indoor series): ETB/ETV/ETVZ/ETS 16
    (
        re.compile(r"^ET[BVS][HXZ]B?(16)" + _TANK + r"[DE]"),
        {"16": ["epra14dav3", "epra16dav3", "epra18dav3"]},
        "Altherma 3 H HT (EPRA 14-18 kW)",
    ),
    # Altherma 3 R high capacity: EABH/EABX, EAVH/EAVX/EAVZ 16 + EPGA D
    (
        re.compile(r"^EA[BV][HXZ](16)" + _TANK + r"D"),
        {"16": ["epga11dav3", "epga14dav3", "epga16dav3"]},
        "Altherma 3 R (EPGA D 11-16 kW)",
    ),
    # Altherma 3 R, D series 11-16 kW: EBB/EBV/EBVZ/EBS + ERLA D
    (
        re.compile(r"^EB[BVS][HXZ]B?(11|16)" + _TANK + r"D"),
        {"11": ["erla11dav3"], "16": ["erla14dav3", "erla16dav3"]},
        "Altherma 3 R (ERLA D 11-16 kW)",
    ),
]

# Monobloc units: the outdoor unit IS the model; map its sub-variants.
_MONOBLOC_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^EBLA0?(04|06|08)E2?3?V3"), "ebla{0}ev3"),
    # EBLA09 D: one datasheet (3-phase W1); the V3 variants share it
    (re.compile(r"^EBLA0?(09)DA3?(?:V3|W1)"), "ebla{0}da3w1"),
    (re.compile(r"^EDLA0?(09|11|14|16)DA?3?(?:V3|W1)"), "edla{0}d3v3"),
    (re.compile(r"^[ER]BLQ0?(05|07|11|14|16)C"), "eblq{0}cv3"),
    (re.compile(r"^[ER]DLQ0?(05|07|11|14|16)C"), "edlq{0}cv3"),
]

# Indoor families ESPAltherma knows but we hold no datasheet for: the user
# gets the basic profile (cycle analytics work; datasheet COP does not).
_NO_DATASHEET_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^[ER]H[BVS][HXZ]B?(04|08)" + _TANK + r"D"), "Altherma 3 R (ERGA D)"),
    (re.compile(r"^[ER]H[BVF][HXZ]B?\d{2}" + _TANK + r"C"), "Altherma LT (ERLQ / ERHQ)"),
    (re.compile(r"^EHFH|^EHFZ"), "Altherma 3 R (ERLA03 D)"),
    (re.compile(r"^EBLA(11|14|16)D|^EDLA0?(04|06|08)E"), "Altherma 3 H monobloc"),
    (re.compile(r"^[ER]GSQ|^THERMALIA"), "Altherma GEO2"),
    (re.compile(r"^EKHWET|^CKHWS"), "Altherma DHW heat pump"),
    (re.compile(r"^EGS|^EWS"), "Altherma 3 GEO"),
    (re.compile(r"^EW[AY][AQ]"), "Daikin mini chiller"),
    (re.compile(r"^EP[BSV][XZ]"), "Altherma 4 (indoor code; pick your EPSK outdoor unit)"),
]


@dataclass(frozen=True)
class ModelMatch:
    """Result of resolving free text to a model key."""

    kind: str  # "exact" | "alias" | "indoor" | "ambiguous" | "no_datasheet" | "unknown"
    key: str | None = None
    candidates: list[str] = field(default_factory=list)
    series: str = ""
    code: str = ""


# Datasheets flagged as non-catalogue (``verified: false`` in
# data/datasheets.json, #393): never suggested. Pinned against the JSON by
# tests/test_435_model_catalog.py (no file I/O in the config flow).
FLAGGED_NON_CATALOGUE: frozenset[str] = frozenset({
    "epga10dav3", "epra04eav3", "epra06eav3", "epra11eav3", "epra14eav3",
    "epra16eav3", "epra18eav3", "erla04dav3", "erla06dav3", "erla08dav3",
    "erla12dav3",
})


def _tokens(text: str) -> list[str]:
    """Upper-case alphanumeric tokens, longest first within the input order."""
    return [t for t in re.split(r"[^A-Z0-9]+", text.upper()) if len(t) >= 4]


def _outdoor_key(token: str) -> tuple[str, str] | None:
    """(key, kind) for an outdoor / monobloc code, or None."""
    low = token.lower()
    choices = [m for m in MODEL_CHOICES if m not in (MODEL_BASISPROFIEL, MODEL_CUSTOM)]
    if low in choices:
        return low, "exact"
    if low in MODEL_ALIASES:
        return MODEL_ALIASES[low], "alias"
    # longest known key the code starts with (ERGA06EAV3H7 -> erga06eav3)
    for key in sorted(choices + list(MODEL_ALIASES), key=len, reverse=True):
        if low.startswith(key):
            return MODEL_ALIASES.get(key, key), "alias"
    for pat, tmpl in _MONOBLOC_RULES:
        m = pat.match(token)
        if m:  # every template yields a model key (pinned by the tests)
            return tmpl.format(m.group(1)), "alias"
    return None


def resolve_model_text(text: str) -> ModelMatch:
    """Resolve what the user typed (indoor, outdoor or both) to a model."""
    tokens = _tokens(text or "")
    # An outdoor code anywhere in the text wins ("EHBX08EF6V + ERGA06EAV3").
    for tok in tokens:
        hit = _outdoor_key(tok)
        if hit is not None:
            return ModelMatch(kind=hit[1], key=hit[0], candidates=[hit[0]], code=tok)
    flagged = FLAGGED_NON_CATALOGUE
    for tok in tokens:
        for pat, sizes, series in _INDOOR_RULES:
            m = pat.match(tok)
            if not m:
                continue
            cands = [
                k for k in sizes.get(m.group(1), [])
                if k in MODEL_CHOICES and k not in flagged
            ]
            if len(cands) == 1:
                return ModelMatch(
                    kind="indoor", key=cands[0], candidates=cands,
                    series=series, code=tok,
                )
            if cands:
                return ModelMatch(
                    kind="ambiguous", candidates=cands, series=series, code=tok,
                )
        for pat, series in _NO_DATASHEET_RULES:
            if pat.match(tok):
                return ModelMatch(kind="no_datasheet", series=series, code=tok)
    return ModelMatch(kind="unknown", code=tokens[0] if tokens else "")


# Family dropdown hint: the indoor-unit prefixes sold with each outdoor
# family, so a user who only knows the indoor code finds the family.
INDOOR_HINT_BY_FAMILY: dict[str, str] = {
    "erga": "EHB/EHV/EHVZ/EHS (E series)",
    "epra": "ETB/ETV/ETVZ/ETS, ELB/ELV/ELS",
    "epga": "EAB/EAV/EAVZ",
    "erla": "EBB/EBV/EBVZ/EBS",
    "evlq": "EHYHBH/EHYHBX",
    "ekhbrd": "EKHBRD (hydrobox)",
}


def indoor_units_for(model_key: str) -> list[str]:
    """Indoor-unit code stems sold with this outdoor model (for labels)."""
    out: list[str] = []
    stems = {
        "Altherma 3 R (ERGA E)": "EHBH/EHBX, EHVH/EHVX/EHVZ, EHSH/EHSX",
        "Altherma 3 H MT (EPRA E 8-12 kW)": "ETBH/ETBX, ETVH/ETVX/ETVZ, ETSH/ETSX, ELBH/ELBX, ELVH/ELVX/ELVZ",
        "Altherma 3 H HT (EPRA 14-18 kW)": "ETBH/ETBX, ETVH/ETVX/ETVZ, ETSH/ETSX",
        "Altherma 3 R (EPGA D 11-16 kW)": "EABH/EABX, EAVH/EAVX/EAVZ",
        "Altherma 3 R (ERLA D 11-16 kW)": "EBBH/EBBX, EBVH/EBVX/EBVZ, EBSH/EBSX",
    }
    for pat, sizes, series in _INDOOR_RULES:
        for size, keys in sizes.items():
            if model_key in keys:
                out.append(f"{stems[series]} {size}")
    return out
