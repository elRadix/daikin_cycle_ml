"""ESPAltherma v2 (beta) entity discovery.

Scans hass.states for entities matching the v2 prefix
(`sensor.espaltherma_` by default) and builds a slug -> entity_id index.

The index is the join point between v2's individual entities and the
canonical attribute names our integration consumes via attribute_reader.

Design notes:
- Pure function of hass state; caller re-invokes on demand (cheap).
- Both `sensor.` and `binary_sensor.` domains are scanned. ESPAltherma v2
  publishes numeric values on `sensor.espaltherma_*` and on/off values on
  `binary_sensor.espaltherma_*`. The alternate-domain prefix is derived
  automatically from the primary one (see `_alternate_prefixes`).
- Collisions: if the same slug exists in BOTH domains (misconfiguration —
  ESPAltherma should publish either-or), the primary domain (from `prefix`)
  wins deterministically. Ordering is explicit: primary pass first, then
  alternate pass with `not in index` guard.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .slug import DEFAULT_PREFIX

DEFAULT_DOMAIN = "sensor"  # kept for backwards compat
DEFAULT_DOMAINS: tuple[str, ...] = ("sensor", "binary_sensor")


def _alternate_prefixes(prefix: str) -> list[str]:
    """Return alternate-domain variants of `prefix`.

    ESPAltherma v2 publishes numeric values as `sensor.espaltherma_*` and
    on/off values as `binary_sensor.espaltherma_*`. To resolve ALL
    consumed attributes we scan both domains, deriving the alternate
    prefix from the primary one.

    Examples:
      - "sensor.espaltherma_"       -> ["binary_sensor.espaltherma_"]
      - "binary_sensor.espaltherma_" -> ["sensor.espaltherma_"]
      - "sensor.custom_prefix_"     -> ["binary_sensor.custom_prefix_"]
      - any other domain             -> []
    """
    alt: list[str] = []
    if prefix.startswith("sensor."):
        alt.append("binary_sensor." + prefix[len("sensor."):])
    elif prefix.startswith("binary_sensor."):
        alt.append("sensor." + prefix[len("binary_sensor."):])
    return alt


def build_slug_index(
    hass: HomeAssistant,
    prefix: str = DEFAULT_PREFIX,
) -> dict[str, str]:
    """Return {slug: entity_id} for every entity under `prefix` (and its
    alternate-domain variant).

    Two-pass scan:
      1. Primary domain (from `prefix`) — builds the index.
      2. Alternate domain (sensor <-> binary_sensor) — adds only missing
         slugs, so primary wins on collision.

    Empty slugs (entity_id == prefix, which should not occur in practice)
    are skipped.
    """
    index: dict[str, str] = {}

    # Pass 1: primary domain (from `prefix`)
    primary_domain = prefix.split(".", 1)[0] if "." in prefix else DEFAULT_DOMAIN
    for state in hass.states.async_all(primary_domain):
        eid: str = state.entity_id
        if not eid.startswith(prefix):
            continue
        slug = eid[len(prefix):]
        if slug:
            index[slug] = eid

    # Pass 2: alternate domains (sensor <-> binary_sensor) — do not override
    for alt_prefix in _alternate_prefixes(prefix):
        alt_domain = alt_prefix.split(".", 1)[0]
        for state in hass.states.async_all(alt_domain):
            eid: str = state.entity_id
            if not eid.startswith(alt_prefix):
                continue
            slug = eid[len(alt_prefix):]
            if slug and slug not in index:
                index[slug] = eid

    return index


def discover_entity_ids(
    hass: HomeAssistant,
    prefix: str = DEFAULT_PREFIX,
) -> list[str]:
    """Return sorted list of matching entity_ids across both domains.

    Includes both `sensor.espaltherma_*` and `binary_sensor.espaltherma_*`
    (or the corresponding alternate domain for custom prefixes). Stable
    for diffing/logging.
    """
    seen: set[str] = set()
    for p in [prefix, *_alternate_prefixes(prefix)]:
        domain = p.split(".", 1)[0]
        for state in hass.states.async_all(domain):
            eid = state.entity_id
            if (
                isinstance(eid, str)
                and eid.startswith(p)
                and eid != p
            ):
                seen.add(eid)
    return sorted(seen)
