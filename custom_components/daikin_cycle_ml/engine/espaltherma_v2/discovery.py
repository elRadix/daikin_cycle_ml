"""ESPAltherma v2 (beta) entity discovery.

Scans hass.states for entities matching the v2 prefix
(`sensor.espaltherma_` by default) and builds a slug -> entity_id index.

The index is the join point between v2's individual entities and the
canonical attribute names our integration consumes via attribute_reader.

Design notes:
- Pure function of hass state; caller re-invokes on demand (cheap).
- Non-sensor domains are ignored (v2 publishes binary_sensor.espaltherma_*
  for on/off values; those live in a separate discovery result).
- Collisions: HA entity_ids are unique globally, so within `sensor.` domain
  a slug collision cannot occur. If a future prefix scheme allowed it,
  "last wins" (deterministic given async_all order).
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .slug import DEFAULT_PREFIX

DEFAULT_DOMAIN = "sensor"


def build_slug_index(
    hass: HomeAssistant,
    prefix: str = DEFAULT_PREFIX,
) -> dict[str, str]:
    """Return {slug: entity_id} for every entity under `prefix`.

    `prefix` includes the domain (`sensor.espaltherma_`). Entities that
    do not start with it are skipped. Empty slugs (entity_id == prefix,
    which should not occur in practice) are skipped.
    """
    index: dict[str, str] = {}
    for state in hass.states.async_all(DEFAULT_DOMAIN):
        eid: str = state.entity_id
        if not eid.startswith(prefix):
            continue
        slug = eid[len(prefix):]
        if not slug:
            continue
        index[slug] = eid
    return index


def discover_entity_ids(
    hass: HomeAssistant,
    prefix: str = DEFAULT_PREFIX,
) -> list[str]:
    """Return sorted list of matching entity_ids. Stable for diffing/logging."""
    return sorted(
        state.entity_id
        for state in hass.states.async_all(DEFAULT_DOMAIN)
        if isinstance(state.entity_id, str)
        and state.entity_id.startswith(prefix)
        and state.entity_id != prefix
    )
