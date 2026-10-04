"""Datasheet loader for Daikin heat pump specs.

Two sources:
  * bundled JSON in custom_components/daikin_cycle_ml/data/datasheets.json
  * user override via .storage (managed by services.py import_datasheet)

Per-model replace semantics: a user entry fully replaces the bundled entry
for the same model key. Empty `points` = "not usable" -> consumers see None.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

KNOWN_SCHEMA_VERSION = 1

_BUNDLED_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "datasheets.json"
)

_T_OUT_MIN, _T_OUT_MAX = -30.0, 40.0
_T_LWC_MIN, _T_LWC_MAX = 10.0, 70.0
_COP_MIN, _COP_MAX = 0.5, 10.0

_REQUIRED_MODEL_KEYS = {"family", "kw", "lwt_min", "lwt_max", "nom_cop"}
_REQUIRED_POINT_KEYS = {"label", "t_out", "t_lwc", "cop"}


def _validate_model(key: str, entry: Any) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errs: list[str] = []
    if not isinstance(entry, dict):
        return [f"{key}: not a dict"]
    missing = _REQUIRED_MODEL_KEYS - set(entry)
    if missing:
        errs.append(f"{key}: missing {sorted(missing)}")
    pts = entry.get("points", [])
    if not isinstance(pts, list):
        errs.append(f"{key}: points not a list")
        return errs
    for i, p in enumerate(pts):
        if not isinstance(p, dict):
            errs.append(f"{key}.points[{i}]: not a dict")
            continue
        miss = _REQUIRED_POINT_KEYS - set(p)
        if miss:
            errs.append(f"{key}.points[{i}]: missing {sorted(miss)}")
            continue
        for fname, lo, hi in (
            ("t_out", _T_OUT_MIN, _T_OUT_MAX),
            ("t_lwc", _T_LWC_MIN, _T_LWC_MAX),
            ("cop", _COP_MIN, _COP_MAX),
        ):
            v = p.get(fname)
            if not isinstance(v, (int, float)) or not (lo <= v <= hi):
                errs.append(
                    f"{key}.points[{i}].{fname}={v!r} out of range [{lo},{hi}]"
                )
    return errs


def _parse_payload(raw: Any, origin: str) -> dict[str, Any]:
    """Validate root + per-model, drop invalid models. Never raises."""
    if not isinstance(raw, dict):
        _LOGGER.error("%s datasheet: root not dict", origin)
        return {}
    if raw.get("schema_version") != KNOWN_SCHEMA_VERSION:
        _LOGGER.error(
            "%s datasheet: schema %r != %d",
            origin, raw.get("schema_version"), KNOWN_SCHEMA_VERSION,
        )
        return {}
    models = raw.get("models", {})
    if not isinstance(models, dict):
        _LOGGER.error("%s datasheet: models not dict", origin)
        return {}
    clean: dict[str, Any] = {}
    for k, v in models.items():
        errs = _validate_model(k, v)
        if errs:
            _LOGGER.warning("%s datasheet %s invalid: %s", origin, k, errs)
            continue
        clean[k] = v
    return clean


def load_defaults(path: Path | None = None) -> dict[str, Any]:
    """Load JSON-level defaults (defrost <, off >, outdoor range, buh offset).

    Returns {} on any failure; callers must apply their own fallbacks.
    """
    p = path or _BUNDLED_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    d = raw.get("defaults", {})
    return d if isinstance(d, dict) else {}


def load_bundled(path: Path | None = None) -> dict[str, Any]:
    """Load + validate bundled JSON. Returns {} on any failure."""
    p = path or _BUNDLED_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _LOGGER.error("Bundled datasheet missing: %s", p)
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        _LOGGER.error("Bundled datasheet unreadable: %s", exc)
        return {}
    return _parse_payload(raw, "Bundled")


def parse_user_payload(raw: Any) -> dict[str, Any]:
    """Validate a user-supplied JSON object (already parsed). Returns clean models."""
    return _parse_payload(raw, "User")


def merge(
    bundled: dict[str, Any], user: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Per-model replace: user wins on key collision. Adds 'source' field."""
    out: dict[str, dict[str, Any]] = {}
    for k, v in bundled.items():
        out[k] = {**v, "source": "bundled"}
    for k, v in user.items():
        out[k] = {**v, "source": "user"}
    return out


def get_datasheet(
    merged: dict[str, Any], model: str
) -> dict[str, Any] | None:
    """Return datasheet for model, or None when missing or points empty."""
    entry = merged.get(model)
    if not isinstance(entry, dict):
        return None
    if not entry.get("points"):
        return None
    return entry
