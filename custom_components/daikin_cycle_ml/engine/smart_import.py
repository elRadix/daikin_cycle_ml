"""Smart auto-import helpers for entity discovery + fuzzy attribute matching.

Implements issue #51 (target v1.8.0). Five layers:

- Laag 1: entity discovery via attribute-overlap scoring
- Laag 2: alias table + normalized matching
- Laag 3: fuzzy score fallback (Jaccard + register-code conflict guard)
- Laag 4: diagnostic builder (per-canonical status)
- Laag 5: register-value sanity check

Anti-alias (issue #51, case julG COP~11): the canonical
``Leaving water temp. after BUH (R2T)`` MUST NOT match ``Hydro Module LWT
(R1T)`` or any other ``R1T`` variant. Enforced via ``_has_register_conflict``
in both the normalized and fuzzy paths.

Scope note: 4 community attrs cited in issue #51 (DHW tank temp,
Thermostat ON/OFF, Refrigerant pressure sensor, Fan 1) are NOT in
``CORE_ATTRIBUTES`` and are therefore out of scope - they are never
mapping targets for this integration. Their mention in issue #51 is
evidence of ESPAltherma variance, not a request to alias them.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..const import (
    ATTR_3WAY_VALVE,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_LW_SETPOINT,
    ATTR_OUTDOOR_AIR_R1T,
    CORE_ATTRIBUTES,
)

_CORE_TUPLE: tuple[str, ...] = tuple(CORE_ATTRIBUTES)

# --- Normalization ------------------------------------------------------

_NORMALIZE_RE = re.compile(r"[\s\-_().,:]+")
_TOKEN_RE = re.compile(r"[ ._():\-]+")
_REGISTER_RE = re.compile(r"\bR\d+T\b", re.IGNORECASE)


def _normalize(s: str) -> str:
    """Lowercase + strip separator chars for structural comparison."""
    return _NORMALIZE_RE.sub("", s.lower())


def _tokens(s: str) -> set[str]:
    """Split into lowercase tokens; empty tokens removed."""
    return {t for t in _TOKEN_RE.split(s.lower()) if t}


def _register_codes(s: str) -> set[str]:
    """Extract upper-cased R#T register codes from a string."""
    return {m.group().upper() for m in _REGISTER_RE.finditer(s)}


def _has_register_conflict(canonical: str, candidate: str) -> bool:
    """Return True if both have R#T codes AND none overlap.

    Anti-alias guard for issue #51 (julG COP~11): the canonical
    ``Leaving water temp. after BUH (R2T)`` must never resolve to a
    ``(R1T)`` candidate, regardless of other token overlap.
    """
    c = _register_codes(canonical)
    cand = _register_codes(candidate)
    return bool(c) and bool(cand) and not (c & cand)


# --- Laag 2: alias table ------------------------------------------------

#: Known community variants from issue #51 (Tweakers ESPAltherma topic
#: analysis, dec 2022 - nov 2025). Only keys in ``CORE_ATTRIBUTES`` are
#: aliased. Community attrs not in ``CORE_ATTRIBUTES`` (DHW tank temp,
#: Thermostat ON/OFF, Refrigerant pressure, Fan 1) are out of scope.
ALIASES: dict[str, tuple[str, ...]] = {
    ATTR_3WAY_VALVE: (
        "3way valve (On:DHW_Off:Space)",
        "3way valve (On:DHW Off:Space)",
        "3-way valve (On:DHW Off:Space)",
        "3-way valve(On:DHW_Off:Space)",
    ),
    ATTR_INV_FREQUENCY_RPS: (
        "INV frequency (Hz)",
        "INV frequency",
        "Inverter frequency (rps)",
    ),
    ATTR_LW_SETPOINT: (
        "LW setpoint",
        "Leaving water setpoint",
    ),
    ATTR_INLET_WATER_R4T: (
        "Hydro Module Inlet water temp.(R4T)",
        "Inlet water temp (R4T)",
    ),
    ATTR_OUTDOOR_AIR_R1T: (
        "R1T-Outdoor air temp.",
        "Outdoor air temp (R1T)",
    ),
}


# --- Match result -------------------------------------------------------

MatchKind = Literal["exact", "alias", "fuzzy", "missing"]


@dataclass(frozen=True)
class AttrMatch:
    """Result of resolving one canonical attribute against available keys."""

    canonical: str
    actual_key: str | None
    kind: MatchKind
    score: float = 1.0


# --- Laag 2+3: similarity + resolver ------------------------------------

def similarity(a: str, b: str) -> float:
    """Combined Jaccard + register-code score in [0.0, 1.0].

    Register-code conflicts short-circuit to 0.0 (issue #51 case 15).
    Otherwise: ``0.7 * jaccard(tokens) + 0.3 * register_match``.
    """
    if a == b:
        return 1.0
    if _has_register_conflict(a, b):
        return 0.0
    ta, tb = _tokens(a), _tokens(b)
    union = ta | tb
    jaccard = len(ta & tb) / len(union) if union else 0.0
    ra, rb = _register_codes(a), _register_codes(b)
    register_match = 1.0 if (ra and rb and ra == rb) else 0.0
    return 0.7 * jaccard + 0.3 * register_match


def _best_fuzzy(
    canonical: str,
    available: set[str],
    threshold: float,
) -> tuple[str, float] | None:
    """Return best (key, score) if the top score >= threshold, else None."""
    best: tuple[str, float] | None = None
    for candidate in available:
        score = similarity(canonical, candidate)
        if score >= threshold and (best is None or score > best[1]):
            best = (candidate, score)
    return best


def resolve_canonical(
    canonical: str,
    available: set[str],
    *,
    fuzzy_threshold: float = 0.75,
) -> AttrMatch:
    """Resolve one canonical attr to the actual key on the sensor.

    Order: exact -> alias-table -> normalized -> fuzzy.
    Register-code conflicts block the fuzzy path (issue #51 anti-alias).
    """
    if canonical in available:
        return AttrMatch(canonical, canonical, "exact")
    for alias in ALIASES.get(canonical, ()):
        if alias in available:
            return AttrMatch(canonical, alias, "alias")
    norm = _normalize(canonical)
    for attr in available:
        if _normalize(attr) == norm:
            return AttrMatch(canonical, attr, "alias")
    fuzzy = _best_fuzzy(canonical, available, fuzzy_threshold)
    if fuzzy is not None:
        return AttrMatch(canonical, fuzzy[0], "fuzzy", fuzzy[1])
    return AttrMatch(canonical, None, "missing", 0.0)


# --- Laag 1: entity discovery -------------------------------------------

@dataclass(frozen=True)
class CandidateSensor:
    """A sensor entity scored by overlap with canonical attributes."""

    entity_id: str
    overlap_count: int
    matched: tuple[str, ...]


def find_candidate_sensors(
    states: Iterable[tuple[str, Mapping[str, Any]]],
    canonical_attrs: tuple[str, ...] = _CORE_TUPLE,
    *,
    min_overlap: int = 3,
) -> list[CandidateSensor]:
    """Return sensor entities sorted by overlap with canonical attrs.

    Laag 1 of issue #51: auto-detect the user's ESPAltherma source sensor
    even when the entity_id is not the default ``sensor.althermasensors``.

    ``states`` is an iterable of ``(entity_id, attributes)`` pairs, so this
    function stays pure (no HomeAssistant import).
    """
    scored: list[CandidateSensor] = []
    for entity_id, attrs in states:
        available = set(attrs.keys())
        matched = [c for c in canonical_attrs if c in available]
        if len(matched) >= min_overlap:
            scored.append(CandidateSensor(
                entity_id=entity_id,
                overlap_count=len(matched),
                matched=tuple(matched),
            ))
    scored.sort(key=lambda c: (-c.overlap_count, c.entity_id))
    return scored


# --- Laag 4+5: diagnostic + sanity check --------------------------------

#: Suspicious constant values from issue #51 case 3 (wrong .h file):
#: ``0`` (unconnected register), ``-51.18`` (converter 105 vs 405),
#: ``255`` (uint8 sentinel), ``-40.7`` and ``-31.9`` (nodri2000 report).
SUSPICIOUS_VALUES: frozenset[float] = frozenset(
    {0.0, -51.18, 255.0, -40.7, -31.9}
)

#: Laag 5 hint for 3-phase installs (SirLikeAlot, issue #51): the
#: ``Inverter usage`` attr may need a *400 multiplier on 3-phase units.
PHASE_HINT = (
    "3-phase installs (ERGA/EPRA 3F): Inverter usage may need a *400 "
    "multiplier (issue #51, SirLikeAlot)"
)


@dataclass(frozen=True)
class DiagnosticReport:
    """Structured diagnose output for the wizard step (Laag 4)."""

    matches: tuple[AttrMatch, ...]
    missing: tuple[str, ...]
    warnings: tuple[str, ...]


def check_sanity(
    attrs: Mapping[str, Any],
    resolved: Mapping[str, str],
) -> list[str]:
    """Return warning strings for suspicious constant attr values (Laag 5)."""
    warnings: list[str] = []
    for canonical, actual_key in resolved.items():
        value = attrs.get(actual_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if float(value) in SUSPICIOUS_VALUES:
                warnings.append(
                    f"{canonical!r} -> {actual_key!r} has suspicious "
                    f"constant value {value!r} - possible wrong .h file"
                )
    return warnings


def build_diagnostic(
    canonicals: tuple[str, ...] = _CORE_TUPLE,
    available: set[str] | None = None,
    *,
    attrs: Mapping[str, Any] | None = None,
    fuzzy_threshold: float = 0.75,
) -> DiagnosticReport:
    """Build a full diagnostic report for the wizard (Laag 4 + 5)."""
    available = available or set()
    matches = tuple(
        resolve_canonical(c, available, fuzzy_threshold=fuzzy_threshold)
        for c in canonicals
    )
    missing = tuple(m.canonical for m in matches if m.kind == "missing")
    resolved_map = {
        m.canonical: m.actual_key
        for m in matches
        if m.actual_key is not None
    }
    warnings: list[str] = []
    if attrs is not None:
        warnings = list(check_sanity(attrs, resolved_map))
    if any("Inverter usage" in k for k in available):
        warnings.append(PHASE_HINT)
    return DiagnosticReport(
        matches=matches,
        missing=missing,
        warnings=tuple(warnings),
    )
