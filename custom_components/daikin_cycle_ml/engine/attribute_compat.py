"""ESPAltherma v1/v2 attribute compatibility.

v2 derives attribute names from English labels regardless of the device
language. v1 translated definitions produced translated names, and v2
normalises punctuation. Legacy keys are never removed: every member of an
alias group is materialised in the compat view as soon as one is present.
Lookup is also tolerant of punctuation and whitespace drift.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    # Canonical v2 label -> other known spellings/translations
    "Leaving water temp. before BUH (R1T)": (
        "Leaving water temp.(R1T)",
        "Leaving water temp. (R1T)",
        "Vorlauf vor BUH (R1T)",
    ),
    "Leaving water temp. after BUH (R2T)": (
        "Leaving water temp.(R2T)",
        "Leaving water temp. (R2T)",
        "D(C)",
        "Outlet Water Temp.",
    ),
    "Inlet water temp.(R4T)": (
        "Inlet water temp. (R4T)",
        "Inlet water temp.(C)",
    ),
    "Outdoor air temp.(R1T)": (
        "R1T-Outdoor air temp.",
        "Outdoor air temp. (R1T)",
        "Outdoor air temp.(C)",
    ),
    "Refrig. Temp. liquid side (R3T)": (
        "Refrig. Temp. liquid side(R3T)",
    ),
    "DHW tank temp. (R5T)": (
        "DHW tank temp.(R5T)",
    ),
    "Flow sensor (l/min)": (
        "Flow sensor(l/min)",
    ),
    "INV frequency (rps)": (
        "INV frequency(rps)",
    ),
    "Operation Mode": ("Betriebsart", "Mode de fonctionnement"),
    "Thermostat ON/OFF": ("Thermostat EIN/AUS",),
    "Defrost Operation": ("Abtauung",),
}

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
    normalized_index: dict[str, str] = {}
    for key in attrs:
        normalized_index.setdefault(normalize_key(key), key)

    for canonical, aliases in ALIAS_GROUPS.items():
        group = (canonical, *aliases)
        found: bool = False
        value: Any = None
        for name in group:
            if name in attrs:
                value, found = attrs[name], True
                break
        if not found:
            for name in group:
                hit = normalized_index.get(normalize_key(name))
                if hit is not None:
                    value, found = attrs[hit], True
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
