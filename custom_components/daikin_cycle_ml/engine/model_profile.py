"""Model profile: the user's own values on top of the model's datasheet (#467).

The model is the one chosen in the setup wizard. Its bundled (or imported)
datasheet gives the spec COP and, for some points, the heating capacity.
The profile lets the user fill in what is missing (max heat at A-7/W35,
the compressor's speed range) or adjust a value to their installation.

apply_profile() runs on the one path every consumer reads the datasheet
through (coordinator._refresh_datasheet -> snapshot -> hp_specs), so a
value the user sets is used across the integration: COP against the
datasheet, the normalised A7/W35 COP, the "COP below datasheet" alert and
every card.

Every value carries its source: "datasheet", "learned" (compressor range
from the user's own history) or "manual". Manual wins, then datasheet,
then learned. A profile saved for another model is kept but not applied.

Pure helpers + a small HA Store wrapper; the helpers have no HA imports.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

PROFILE_STORE_VERSION = 1
_STORE_KEY_FMT = "daikin_cycle_ml.model_profile.{entry_id}"

# field -> (min, max). Ranges match the datasheet validation where they overlap.
FIELDS: dict[str, tuple[float, float]] = {
    "kw": (1.0, 40.0),
    "nom_cop": (1.0, 10.0),
    "scop_w35": (1.0, 8.0),
    "scop_w55": (1.0, 8.0),
    "lwt_min": (10.0, 40.0),
    "lwt_max": (40.0, 80.0),
    "rps_min": (1.0, 150.0),
    "rps_max": (5.0, 200.0),
}
POINT_FIELDS: dict[str, tuple[float, float]] = {
    # maximum heating capacity kW at the point: the user's value, or the
    # estimate below raised to every capacity the unit is known to reach
    "hmax": (0.5, 40.0),
    "cop": (0.5, 10.0),    # spec COP at the point
}
T_OUT_RANGE = (-30.0, 40.0)
T_LWC_RANGE = (10.0, 80.0)
SRC_DATASHEET, SRC_LEARNED, SRC_MANUAL, SRC_ESTIMATE = "datasheet", "learned", "manual", "estimate"
# #478 (reviewed by a Daikin application engineer): the EN 14511 capacities
# of a datasheet (hc) are rating points: Daikin picks the compressor speed
# per test point (EPRA08, 10 and 12 all list 6.17 kW at A7/W35 and more at
# A-7 than at A7). They are a lower bound of the maximum at that point, not
# the maximum. The maximum heat is estimated from the product-table maximum
# at A7/W35 (hc_max_a7, EPRA12 9.97 kW) or else the nominal kW, lowered in
# frost and at high water temperature, and never below a capacity the unit
# is known to reach there (datasheet hc, learned from this installation).
EST_OUT_PER_K = 0.01     # -1 % per K outdoor below 7 degC
EST_WATER_PER_K = 0.005  # -0.5 % per K leaving water above 35 degC


def capacity_anchor(entry: Mapping[str, Any]) -> tuple[float | None, str | None]:
    """Maximum heat at A7/W35 and its basis: "max" (product table) or
    "nominal" (datasheet kw, the number in the model name)."""
    for key, basis in (("hc_max_a7", "max"), ("kw", "nominal")):
        v = _num(entry.get(key))
        if v is not None and _in(v, POINT_FIELDS["hmax"]):
            return v, basis
    return None, None


def estimate_hmax(anchor: float, t_out: float, t_lwc: float) -> float:
    """Maximum heat at (t_out, t_lwc) estimated from the A7/W35 anchor."""
    f = (1 - EST_OUT_PER_K * max(0.0, 7 - t_out)) * (1 - EST_WATER_PER_K * max(0.0, t_lwc - 35))
    return round(max(0.5, anchor * f), 2)


def empty_profile() -> dict[str, Any]:
    return {"model": None, "fields": {}, "points": []}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _in(value: float, rng: tuple[float, float]) -> bool:
    return rng[0] <= value <= rng[1]


def point_key(t_out: float, t_lwc: float) -> tuple[float, float]:
    return (round(float(t_out), 1), round(float(t_lwc), 1))


def _fmt_t(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def _label(t_out: float, t_lwc: float) -> str:
    return f"A{_fmt_t(t_out)}/W{_fmt_t(t_lwc)}"


def normalize(raw: Any) -> dict[str, Any]:
    """A clean profile from stored or service data; invalid parts dropped."""
    out = empty_profile()
    if not isinstance(raw, Mapping):
        return out
    model = raw.get("model")
    out["model"] = str(model) if isinstance(model, str) and model else None
    fields = raw.get("fields")
    if isinstance(fields, Mapping):
        for k, rng in FIELDS.items():
            v = _num(fields.get(k))
            if v is not None and _in(v, rng):
                out["fields"][k] = v
    pts: dict[tuple[float, float], dict[str, Any]] = {}
    for p in raw.get("points") or []:
        if not isinstance(p, Mapping):
            continue
        t, w = _num(p.get("t_out")), _num(p.get("t_lwc"))
        if t is None or w is None or not _in(t, T_OUT_RANGE) or not _in(w, T_LWC_RANGE):
            continue
        vals = {k: v for k, rng in POINT_FIELDS.items()
                if (v := _num(p.get(k))) is not None and _in(v, rng)}
        if vals:
            key = point_key(t, w)
            pts[key] = {"t_out": key[0], "t_lwc": key[1], **vals}
    out["points"] = [pts[k] for k in sorted(pts)]
    return out


def validate_edit(fields: Any, points: Any) -> list[str]:
    """Errors for a service edit (None = clear that value)."""
    errs: list[str] = []
    if fields is not None and not isinstance(fields, Mapping):
        return ["fields must be a mapping"]
    for k, v in (fields or {}).items():
        if k not in FIELDS:
            errs.append(f"unknown field {k!r} (allowed: {', '.join(FIELDS)})")
        elif v is not None and ((n := _num(v)) is None or not _in(n, FIELDS[k])):
            errs.append(f"{k}={v!r} out of range {list(FIELDS[k])}")
    if points is not None and not isinstance(points, list):
        return errs + ["points must be a list"]
    for i, p in enumerate(points or []):
        if not isinstance(p, Mapping):
            errs.append(f"points[{i}]: not a mapping")
            continue
        t, w = _num(p.get("t_out")), _num(p.get("t_lwc"))
        if t is None or not _in(t, T_OUT_RANGE):
            errs.append(f"points[{i}].t_out={p.get('t_out')!r} out of range {list(T_OUT_RANGE)}")
        if w is None or not _in(w, T_LWC_RANGE):
            errs.append(f"points[{i}].t_lwc={p.get('t_lwc')!r} out of range {list(T_LWC_RANGE)}")
        for k in p:
            if k in ("t_out", "t_lwc"):
                continue
            if k not in POINT_FIELDS:
                errs.append(f"points[{i}]: unknown field {k!r} (allowed: hmax, cop)")
            elif p[k] is not None and ((n := _num(p[k])) is None or not _in(n, POINT_FIELDS[k])):
                errs.append(f"points[{i}].{k}={p[k]!r} out of range {list(POINT_FIELDS[k])}")
    return errs


def edit(profile: Mapping[str, Any], model: str, *, fields: Mapping[str, Any] | None = None,
         points: list[Mapping[str, Any]] | None = None, reset: bool = False) -> dict[str, Any]:
    """The profile after an edit. A None value removes that override; a point
    left without values is removed; reset starts from an empty profile.
    Editing for another model replaces the profile of the old model."""
    cur = normalize(profile)
    if reset or cur["model"] != model:
        cur = empty_profile()
    cur["model"] = model
    for k, v in (fields or {}).items():
        if v is None:
            cur["fields"].pop(k, None)
        elif (n := _num(v)) is not None and k in FIELDS and _in(n, FIELDS[k]):
            cur["fields"][k] = n
    by_key = {point_key(p["t_out"], p["t_lwc"]): dict(p) for p in cur["points"]}
    for p in points or []:
        t, w = _num(p.get("t_out")), _num(p.get("t_lwc"))
        if t is None or w is None:
            continue
        key = point_key(t, w)
        row = by_key.get(key, {"t_out": key[0], "t_lwc": key[1]})
        for k in POINT_FIELDS:
            if k not in p:
                continue
            if p[k] is None:
                row.pop(k, None)
            elif (n := _num(p[k])) is not None and _in(n, POINT_FIELDS[k]):
                row[k] = n
        if any(k in row for k in POINT_FIELDS):
            by_key[key] = row
        else:
            by_key.pop(key, None)
    cur["points"] = [by_key[k] for k in sorted(by_key)]
    return normalize(cur)


def apply_profile(entry: Mapping[str, Any] | None, profile: Mapping[str, Any] | None,
                  model: str, learned: Mapping[str, Any] | None = None,
                  hmax_learned: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """The model's datasheet with the user's values and the learned
    compressor range merged in per value, each with its source.
    None when there is neither a datasheet nor a profile value."""
    prof = normalize(profile)
    manual = prof if prof["model"] == model else empty_profile()
    base: dict[str, Any] = dict(entry or {})
    if not base and not manual["fields"] and not manual["points"]:
        return None
    sources: dict[str, str] = {}
    for k in FIELDS:
        if _num(base.get(k)) is not None:
            sources[k] = SRC_DATASHEET
    for k in ("rps_min", "rps_max"):
        v = _num((learned or {}).get(k))
        if k not in sources and v is not None and _in(v, FIELDS[k]):
            base[k] = round(v, 1)
            sources[k] = SRC_LEARNED
    for k, v in manual["fields"].items():
        base[k] = v
        sources[k] = SRC_MANUAL

    anchor, basis = capacity_anchor(base)
    points: dict[tuple[float, float], dict[str, Any]] = {}

    def _estimate(row: dict[str, Any], t: float, w: float, floor: float | None) -> None:
        """hmax = the estimate, raised to a capacity known at this point."""
        if anchor is None and floor is None:
            return
        est = estimate_hmax(anchor, t, w) if anchor is not None else 0.0
        at_anchor = basis == "max" and (t, w) == point_key(7, 35)
        if floor is not None and floor >= est:
            row["hmax"], row["src"]["hmax"] = floor, SRC_DATASHEET
        else:
            row["hmax"] = est
            row["src"]["hmax"] = SRC_DATASHEET if at_anchor else SRC_ESTIMATE

    for p in base.get("points") or []:
        if not isinstance(p, Mapping):
            continue
        t, w = _num(p.get("t_out")), _num(p.get("t_lwc"))
        if t is None or w is None:
            continue
        row = dict(p)
        row["src"] = {k: SRC_DATASHEET for k in POINT_FIELDS if _num(p.get(k)) is not None}
        key = point_key(t, w)
        if "hmax" not in row["src"]:
            hc = _num(p.get("hc"))
            _estimate(row, key[0], key[1], hc if hc is not None and _in(hc, POINT_FIELDS["hmax"]) else None)
        points[key] = row
    # every model has its anchor point A7/W35
    key = point_key(7, 35)
    if key not in points and anchor is not None:
        row = {"label": "A7/W35", "t_out": key[0], "t_lwc": key[1], "src": {}}
        _estimate(row, key[0], key[1], None)
        points[key] = row
    # #473/#478: what this installation delivered at high speed is a lower
    # bound too: it raises the maximum, never lowers it
    for b in (hmax_learned or {}).get("bands") or []:
        t, w, v = _num(b.get("t_out")), _num(b.get("t_lwc")), _num(b.get("hmax"))
        if t is None or w is None or v is None or not _in(v, POINT_FIELDS["hmax"]):
            continue
        key = point_key(t, w)
        if key not in points:
            fresh: dict[str, Any] = {"label": _label(*key), "t_out": key[0], "t_lwc": key[1], "src": {}}
            _estimate(fresh, key[0], key[1], None)
            points[key] = fresh
        row = points[key]
        cur = _num(row.get("hmax"))
        if cur is not None and cur >= v:   # manual values are merged after this
            continue
        row["hmax"] = round(v, 2)
        row["hmax_n"] = int(_num(b.get("n")) or 0)
        row["src"]["hmax"] = SRC_LEARNED
    for p in manual["points"]:
        key = point_key(p["t_out"], p["t_lwc"])
        row = points.get(key) or {"label": _label(*key), "t_out": key[0], "t_lwc": key[1], "src": {}}
        for k in POINT_FIELDS:
            if k in p:
                row[k] = p[k]
                row["src"][k] = SRC_MANUAL
                if k == "hmax":
                    row.pop("hmax_n", None)
        points[key] = row
    base["points"] = [points[k] for k in sorted(points)]
    base["value_sources"] = sources
    base["hmax_from_datasheet"] = basis == "max"
    base["hmax_basis"] = basis
    base["hmax_anchor"] = anchor
    base["profile"] = {
        "model": prof["model"],
        "applied": prof["model"] == model and bool(manual["fields"] or manual["points"]),
        "manual_fields": sorted(manual["fields"]),
        "manual_points": len(manual["points"]),
    }
    return base


LEARN_MIN_RUNS = 20
LEARN_DAYS = 60


def _pct(values: list[float], q: float) -> float:
    v = sorted(values)
    pos = (len(v) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def learn_rps(rows: list[tuple[Any, Any]]) -> dict[str, Any]:
    """Compressor speed range from steady runs of this installation:
    minimum = 5th percentile of the run averages (the speed it settles at
    under low load), maximum = 95th percentile of the run peaks. Empty
    until LEARN_MIN_RUNS runs are known, so a few odd runs never set it."""
    avgs = [v for a, _ in rows if (v := _num(a)) is not None and v > 0]
    maxs = [v for _, m in rows if (v := _num(m)) is not None and v > 0]
    if len(maxs) < LEARN_MIN_RUNS or len(avgs) < LEARN_MIN_RUNS:
        return {"runs": len(maxs)}
    lo, hi = round(_pct(avgs, 0.05), 1), round(_pct(maxs, 0.95), 1)
    if hi <= lo:
        return {"runs": len(maxs)}
    return {"rps_min": lo, "rps_max": hi, "runs": len(maxs)}


# ---------------------------------------------------------------- store

def _store(hass: Any, entry_id: str) -> Any:
    from homeassistant.helpers.storage import Store  # noqa: PLC0415 - keep helpers HA-free

    return Store(hass, PROFILE_STORE_VERSION, _STORE_KEY_FMT.format(entry_id=entry_id))


async def load(hass: Any, entry_id: str) -> dict[str, Any]:
    """The stored profile ({} parts dropped when invalid); empty when none."""
    data = await _store(hass, entry_id).async_load()
    return normalize(data)


async def save(hass: Any, entry_id: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    clean = normalize(profile)
    await _store(hass, entry_id).async_save(clean)
    return clean
