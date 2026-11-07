"""ESPAltherma v2 (beta) attribute resolution — issue #281.

Joins discovered v2 entities (sensor.espaltherma_*) back into the canonical
attribute dict the coordinator consumes. Model-aware in two layers:

1. Discovery layer (this module): read whatever exists under the prefix,
   normalize state values, report what's missing for the user's install.
2. Model bridge (this module): helpers to translate between upstream .h
   filenames and canonical labels, so future work can narrow the required
   set per model instead of the blanket REQUIRED_ATTRIBUTES.

Model-awareness rationale: not every Daikin model publishes every label
(e.g. BUH Step1 only exists on units with a backup heater). Requiring
BUH Step1 on a non-BUH model would raise a permanent repair issue. The
coordinator-side fix for this shipped in #280 (tick runs during freeze),
so the resolver can safely surface per-label misses without blocking the
integration.

Future work (follow-up issue): wire ``labels_for_model`` into a
model→.h bridge backed by ``docs/MODEL_ATTRIBUTES.json`` and
``engine/model_datasheets.py``, so ``resolve_attrs`` accepts a ``model``
hint and reports ``not_applicable`` separately from ``missing``.
"""
from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant

from ...const import REQUIRED_ATTRIBUTES
from ..attribute_reader import _normalize  # reuse tested normalization
from .discovery import build_slug_index
from .slug import DEFAULT_PREFIX, make_json_key

_MODEL_ATTRIBUTES_PATH = pathlib.Path(__file__).resolve().parents[4] / (
    "docs/MODEL_ATTRIBUTES.json"
)


@dataclass(frozen=True)
class ResolveResult:
    """Outcome of resolve_attrs().

    attrs: canonical label -> normalized value for every resolved entity.
    missing_required: REQUIRED_ATTRIBUTES labels without a matching entity.
    collisions: slugs matched by >1 entity_id (case-only typos in upstream;
        still resolvable, but surfaced for diagnostics).
    discovered_count: total v2 entities found under the prefix.
    """

    attrs: dict[str, Any] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)
    discovered_count: int = 0


def _read_entity_state(hass: HomeAssistant, entity_id: str) -> Any:
    """Return normalized value for one v2 entity, or None if absent."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    raw = state.state
    if raw is None:
        return None
    return _normalize(raw)


def resolve_attrs(
    hass: HomeAssistant,
    prefix: str = DEFAULT_PREFIX,
    custom_map: Mapping[str, str] | None = None,
) -> ResolveResult:
    """Resolve canonical attributes from ESPAltherma v2 individual entities.

    Parameters
    ----------
    hass : HomeAssistant
        Running HA instance.
    prefix : str
        Entity prefix including the domain (``sensor.espaltherma_``).
    custom_map : Mapping[str, str] | None
        Optional {canonical_label: actual_label_or_slug} override. When the
        user's ESPAltherma .h file uses a variant spelling, this forces
        that label to be resolved from the given target. Both canonical
        and target are matched through ``make_json_key`` so the caller can
        pass either raw labels or already-slugged values.
    """
    index = build_slug_index(hass, prefix=prefix)

    # Detect collisions among REQUIRED labels: a collision is a slug shared
    # by 2+ distinct required labels (case-only variants in upstream .h files).
    # At SHA 714ad016 no REQUIRED pair collides; the guard remains for future
    # upstream drift. Placeholder labels (makeJsonKey -> "") are excluded.
    slugs_by_label: dict[str, list[str]] = {}
    for label in REQUIRED_ATTRIBUTES:
        slug = make_json_key(label)
        if not slug:
            continue
        slugs_by_label.setdefault(slug, []).append(label)
    collisions: list[str] = sorted(
        s for s, ls in slugs_by_label.items() if len(ls) > 1
    )

    # Override map: user says canonical_X should come from slug Y
    overrides: dict[str, str] = {}
    if custom_map:
        for canonical, actual in custom_map.items():
            overrides[canonical] = make_json_key(actual)

    attrs: dict[str, Any] = {}
    missing: list[str] = []
    for label in REQUIRED_ATTRIBUTES:
        slug = overrides.get(label) or make_json_key(label)
        if not slug:
            missing.append(label)
            continue
        entity_id = index.get(slug)
        if entity_id is None:
            missing.append(label)
            continue
        value = _read_entity_state(hass, entity_id)
        if value is None:
            # Present but unusable (unknown/unavailable/placeholder string).
            missing.append(label)
            continue
        attrs[label] = value

    return ResolveResult(
        attrs=attrs,
        missing_required=missing,
        collisions=collisions,
        discovered_count=len(index),
    )


# ---------- model bridge helpers (used by future follow-up) ----------


def load_model_attributes(
    path: pathlib.Path | None = None,
) -> dict[str, list[str]]:
    """Load {label: [model_h_filename, ...]} from docs/MODEL_ATTRIBUTES.json.

    Returns {} if the file is missing or malformed. The mapping is exactly
    the upstream structure under the ``labels`` key (label -> list of
    filenames); the top-level ``models`` list is intentionally ignored here.
    """
    p = path or _MODEL_ATTRIBUTES_PATH
    try:
        data = json.loads(p.read_text())
    except (FileNotFoundError, OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    labels_obj = data.get("labels")
    if not isinstance(labels_obj, dict):
        return {}
    out: dict[str, list[str]] = {}
    for label, models in labels_obj.items():
        if isinstance(label, str) and isinstance(models, list):
            out[label] = [m for m in models if isinstance(m, str)]
    return out


def labels_for_model(model_h: str, path: pathlib.Path | None = None) -> list[str]:
    """Return sorted labels that the given upstream .h file publishes."""
    mapping = load_model_attributes(path)
    return sorted(
        label for label, models in mapping.items() if model_h in models
    )


def models_for_label(label: str, path: pathlib.Path | None = None) -> list[str]:
    """Return sorted model .h filenames that publish the given label."""
    mapping = load_model_attributes(path)
    return sorted(mapping.get(label, []))
