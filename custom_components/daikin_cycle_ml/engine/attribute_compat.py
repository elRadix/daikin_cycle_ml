"""ESPAltherma v1/v2 attribute compatibility.

v2 derives attribute names from English labels regardless of the device
language. v1 translated definitions produced translated names, and v2
normalises punctuation. Legacy keys are never removed: every member of an
alias group is materialised in the compat view as soon as one is present.
Lookup is also tolerant of punctuation and whitespace drift.
"""
from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from typing import Any

ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    # Canonical v2 label -> other known spellings/translations
    "Leaving water temp. before BUH (R1T)": (
        "Leaving water temp.(R1T)",
        "Leaving water temp. (R1T)",
        "Vorlauf vor BUH (R1T)",
        "[HPSU] Tv inflow Temp (R1T)",
        "Outlet Water Heat Exch. Temp. (R1T)",
        "[Hydrobox] Leaving water temp. (R1T)",
        "[Hydrobox] LWT",
    ),
    "Leaving water temp. after BUH (R2T)": (
        "Leaving water temp.(R2T)",
        "Leaving water temp. (R2T)",
        "D(C)",
        "Outlet Water Temp.",
        "Outlet Water BUH Temp. (R2T)",
        # v1.20.0 #281: ECH2O variants publish "after buffer/BUH" name
        "[HPSU] Tvbh inflow Temp after Buffer/BUH (R2T)",
    ),
    "Inlet water temp.(R4T)": (
        "Inlet water temp. (R4T)",
        "Inlet water temp.(C)",
        "[HPSU] Tr return Temp (R4T)",
        "Inlet temperature(R4T)",
        # v1.20.0 #281: EPSK publishes inlet via "water heat exchanger"
        "Inlet water temp. (water heat exchanger)",
        "[Hydrobox] Inlet water temp. (R4T)",
    ),
    "Outdoor air temp.(R1T)": (
        "R1T-Outdoor air temp.",
        "Outdoor air temp. (R1T)",
        "Outdoor air temp.(C)",
        # v1.20.0 #281: Hybrid model publishes without "(R1T)" suffix
        "Outdoor air temp.",
    ),
    # v1.20.0 #281: ESPAltherma publishes "BE_COP" (underscore) on some
    # firmware, which make_json_key slugifies to "becop". Our canonical
    # constant uses "BE COP" (space) -> "be_cop". Alias group makes both
    # variants resolve.
    "BE COP": (
        "BE_COP",
        "BECOP",
    ),
    "Refrig. Temp. liquid side (R3T)": (
        "Refrig. Temp. liquid side(R3T)",
    ),
    "DHW tank temp. (R5T)": (
        "DHW tank temp.(R5T)",
        "DHW temperature(R5T)",
        "DHW tank temp (R5T)",
    ),
    "Flow sensor (l/min)": (
        "Flow sensor(l/min)",
    ),
    "INV frequency (rps)": (
        "INV frequency(rps)",
        "[Hydrobox] Compressor frequency",
        "Compressor frequency",
        "Frequency (Hz)",
    ),
    "Operation Mode": ("Betriebsart", "Mode de fonctionnement"),
    "Thermostat ON/OFF": ("Thermostat EIN/AUS",),
    "Defrost Operation": ("Abtauung",),
    "Bivalent Operation": ("Bivalenter Betrieb",),

    "R6T (subcool hex gas)": ("20-4 (subcool hex gas?)",),
    "R3T (suction 1)": ("20-8 (suction 1?)",),
    "Heat exchanger liquid temp.": ("20-18 (liquid 2?)",),
    "Auxiliary sensor (R6T) - Room / Outdoor": ("Ext. indoor ambient sensor (R6T)", "Ext. outdoor ambient sensor (R6T)"),
    "SV (hot gas)": ("SV (hot gas)",),
}


# #413: ESPAltherma v2 publishes a name that exists on both the outdoor
# (< 0x60) and the indoor registries with its side ("I/U Thermostat
# ON/OFF", "O/U Thermostat ON/OFF"), see data/catalog_names.txt. v1 keeps
# the definition name. The indoor side is tried first: the values the
# integration reads (water, valve, pump, BUH) live on the hydro unit.
SIDE_PREFIXES: tuple[str, ...] = ("I/U ", "O/U ")




def _id_key(name: str) -> str:
    """ESPAltherma makeJsonKey: the HA id part of a name (case-blind)."""
    return "".join(
        c.lower() if c.isascii() and c.isalnum() else ("_" if c == " " else "")
        for c in name
    )


@functools.cache
def _known_ids() -> frozenset[str]:
    """Id keys of every name the integration reads (labels + aliases).

    Lazy: tools/check_compat_contract.py loads this file on its own,
    without the package, and never calls the side-name helpers.
    """
    from ..const import (  # noqa: PLC0415 - const imports nothing from engine
        CONSUMED_ATTRIBUTES,
        OPTIONAL_ATTRIBUTES,
        REQUIRED_ATTRIBUTES,
    )
    names: set[str] = {*CONSUMED_ATTRIBUTES, *OPTIONAL_ATTRIBUTES, *REQUIRED_ATTRIBUTES}
    for canonical, aliases in ALIAS_GROUPS.items():
        names.update((canonical, *aliases))
    return frozenset(_id_key(n) for n in names)



def side_names(label: str) -> tuple[str, ...]:
    """v2 side names of a definition name (indoor first).

    None when the label already carries a side, and never a side name that
    is itself a name the integration reads ("Operation Mode" -> "I/U
    Operation Mode" is the id of the distinct "I/U operation mode").
    """
    if label.startswith(SIDE_PREFIXES):
        return ()
    return tuple(
        prefix + label for prefix in SIDE_PREFIXES
        if _id_key(prefix + label) not in _known_ids()
    )


def unsided_name(key: str) -> str | None:
    """Definition name of a v2 side name, or None (not sided / a real name)."""
    for prefix in SIDE_PREFIXES:
        if key.startswith(prefix) and _id_key(key) not in _known_ids():
            return key[len(prefix):]
    return None


_WS = re.compile(r"\s+")
_PAREN_OPEN = re.compile(r"\s+\(")
_PAREN_CLOSE = re.compile(r"\s+\)")
_DOT_SPACE = re.compile(r"\s*\.\s*")
_DASH = re.compile(r"\s*-\s*")


def normalize_key(key: str) -> str:
    """Matching-only normalisation. Never stored as an attribute key."""
    s = key.strip().lower()
    s = s.replace("3-way", "3way").replace("3 way", "3way")
    s = _PAREN_OPEN.sub("(", s)
    s = _PAREN_CLOSE.sub(")", s)
    s = _DOT_SPACE.sub(".", s)
    s = _DASH.sub("-", s)
    return _WS.sub(" ", s)


def build_compat_view(attrs: Mapping[str, Any]) -> dict[str, Any]:
    """Legacy attributes + all aliases materialised. Legacy values win.

    Bidirectional: if any member of an alias group is present, every
    member is added. Keeps ``missing_required`` working for v1 and v2
    canonical names.
    """
    view: dict[str, Any] = dict(attrs)
    # #413: a v2 side name also answers to its definition name (indoor
    # first; a published plain name always wins).
    for prefix in SIDE_PREFIXES:
        for key, val in attrs.items():
            plain = unsided_name(key) if key.startswith(prefix) else None
            if plain is not None:
                view.setdefault(plain, val)
    source: dict[str, Any] = dict(view)
    normalized_index: dict[str, str] = {}
    for key in source:
        normalized_index.setdefault(normalize_key(key), key)

    for canonical, aliases in ALIAS_GROUPS.items():
        group = (canonical, *aliases)
        found: bool = False
        value: Any = None
        for name in group:
            if name in source:
                value, found = source[name], True
                break
        if not found:
            for name in group:
                hit = normalized_index.get(normalize_key(name))
                if hit is not None:
                    value, found = source[hit], True
                    break
        if found:
            for name in group:
                view.setdefault(name, value)
    return view


_V2_MARKERS = (
    "Leaving water temp. before BUH (R1T)",
    "Leaving water temp. after BUH (R2T)",
    "Inlet water temp.(R4T)",
)


def detect_schema(attrs: Mapping[str, Any]) -> str:
    """Best-effort tag for diagnostics and tests. Never authoritative."""
    keys = {normalize_key(k) for k in attrs}
    if {normalize_key(m) for m in _V2_MARKERS} <= keys:
        return "espaltherma_v2"
    if any(
        normalize_key(a) in keys
        for group in ALIAS_GROUPS.values()
        for a in group
    ):
        return "espaltherma_v1"
    return "unknown"
