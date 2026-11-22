"""Ingest a Daikin Cycle ML diagnostics file into the anonymised corpus.

Every diagnostics file a user or a test install sends goes through this
tool before it is kept. It:

- loads the JSON leniently: control characters inside strings, and the
  stray bracket lines a paste into an issue or chat often leaves, are
  repaired; the "Download diagnostics" file loads as is;
- removes personal data:
  - entry / device ids are replaced by a stable anonymous id;
  - every entity id that is not one of the integration's own is
    replaced by a placeholder (``sensor.user_1``), consistently in the file;
  - IP / MAC / e-mail addresses, the time-zone name, `friendly_name`
    and Wi-Fi details are dropped; notify targets and paths are dropped;
- keeps what analysis, simulation and tests need:
  - the source attributes;
  - options and resolution;
  - coordinator state, last cycle and daily summaries;
  - model states (baseline, k-means);
  - COP analysis and alert history;
  - entity states with their attributes;
- writes ``tests/fixtures/diagnostics/<model>_<version>_<anon>_<time>.json``
  and updates ``INDEX.json`` (one row per file, the same file twice
  replaces its row).

Usage:
    python tools/ingest_diagnostics.py FILE [FILE ...] [--origin user|maintainer]
        [--note TEXT] [--out DIR]

Names of reporters are never stored; ``--note`` must not contain one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "tests" / "fixtures" / "diagnostics"

# source attributes that identify the network or the board, not the heat pump
DROP_ATTRS = {"IP", "WifiRSSI", "FreeMem", "Uptime", "friendly_name"}
DROP_ATTR_PREFIX = ("M5",)
DROP_KEYS = {"friendly_name", "icon", "notify_service", "path", "timezone",
             "setup_times", "redaction_keys", "id", "identifiers", "area_id"}
ENTITY_ATTR_DROP = {"icon", "friendly_name", "unit_of_measurement", "device_class"}

_ENTITY_RE = re.compile(
    r"\b(sensor|binary_sensor|switch|input_number|input_boolean|climate|"
    r"water_heater|number|select|notify|light|button|counter|utility_meter)"
    r"\.([a-z0-9_]+)\b"
)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
_MAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_ULID_RE = re.compile(r"\b[0-9A-HJKMNP-TV-Z]{26}\b")
_BRACKET_LINE = re.compile(r'^\s*"?\s*[\]\}]+\s*,?\s*$')


# ---------------------------------------------------------------- loading

def _drop_line(lines: list[str], idx: int) -> str:
    """Remove a bracket-only line; keep its comma on the line before."""
    gone = lines.pop(idx)
    if gone.rstrip().endswith(",") and idx > 0 and not lines[idx - 1].rstrip().endswith(","):
        lines[idx - 1] = lines[idx - 1].rstrip() + ","
    return "\n".join(lines)


def load_lenient(text: str, max_repairs: int = 10) -> dict[str, Any]:
    """Parse diagnostics JSON, repairing paste damage line by line.

    Only lines that hold nothing but closing brackets / a stray quote are
    removed, and only where the parser fails: data is never invented.
    """
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    text = text[start:]
    for _ in range(max_repairs + 1):
        try:
            obj, _end = json.JSONDecoder(strict=False).raw_decode(text)
        except json.JSONDecodeError as err:
            lines = text.splitlines()
            bad = err.lineno - 1
            # the damage is on the failing line or the line before it
            for idx in (bad, bad - 1):
                if 0 <= idx < len(lines) and _BRACKET_LINE.match(lines[idx]):
                    text = _drop_line(lines, idx)
                    break
            else:
                raise
            continue
        if isinstance(obj, dict) and "data" in obj:
            return obj
        # parsed only a prefix (an extra closing bracket ended the object
        # early): drop the first bracket-only line after it and retry
        lines = text.splitlines()
        upto = text[:_end].count("\n")  # index of the line that ended it
        for idx in range(upto, min(upto + 3, len(lines))):
            if _BRACKET_LINE.match(lines[idx]):
                text = _drop_line(lines, idx)
                break
        else:
            raise ValueError("diagnostics object without a 'data' section")
    raise ValueError("too many repairs needed")


# ---------------------------------------------------------------- anonymising

class Anonymiser:
    """Consistent replacement of ids within one diagnostics file."""

    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id
        self.anon = hashlib.sha256(entry_id.encode()).hexdigest()[:10] if entry_id else "unknown"
        self._entities: dict[str, str] = {}

    def entity(self, match: re.Match[str]) -> str:
        domain, obj = match.group(1), match.group(2)
        if obj.startswith("daikin_cycle_ml"):
            return match.group(0)
        key = match.group(0)
        if key not in self._entities:
            self._entities[key] = f"{domain}.user_{len(self._entities) + 1}"
        return self._entities[key]

    def text(self, value: str) -> str:
        if self.entry_id:
            value = value.replace(self.entry_id, self.anon)
        value = _ULID_RE.sub("anon", value)
        value = _ENTITY_RE.sub(self.entity, value)
        value = _IP_RE.sub("x.x.x.x", value)
        value = _MAC_RE.sub("xx:xx:xx:xx:xx:xx", value)
        return _MAIL_RE.sub("redacted@example", value)

    def walk(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if k in DROP_KEYS:
                    continue
                out[self.text(str(k))] = self.walk(v)
            return out
        if isinstance(obj, list):
            return [self.walk(v) for v in obj]
        if isinstance(obj, str):
            return self.text(obj)
        return obj


# ---------------------------------------------------------------- trimming

def _source(src: dict[str, Any]) -> dict[str, Any]:
    attrs = {
        k: v for k, v in (src.get("attributes_full") or {}).items()
        if k not in DROP_ATTRS and not k.startswith(DROP_ATTR_PREFIX)
    }
    keep = {k: src.get(k) for k in ("state", "available", "attribute_count", "age_s")}
    return {**keep, "attributes": attrs}


def _entities(ents: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for e in ents.get("entries") or []:
        eid = str(e.get("entity_id") or "")
        # everything up to "daikin_cycle_ml_" goes: HA puts the area name in
        # front of the object id when the device has an area (#487: "garden_")
        key = eid.split(".", 1)[-1].split("daikin_cycle_ml_", 1)[-1]
        attrs = {k: v for k, v in (e.get("attributes") or {}).items()
                 if k not in ENTITY_ATTR_DROP}
        out[f"{eid.split('.', 1)[0]}:{key}"] = {"state": e.get("state"), "attributes": attrs}
    return out


def trim(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep the sections analysis and tests use, in a fixed layout."""
    d = raw.get("data") or {}
    ha = raw.get("home_assistant") or {}
    meta = d.get("meta") or {}
    db = d.get("database") or {}
    entry = d.get("entry") or {}
    return {
        "corpus_format": 1,
        "home_assistant": {k: ha.get(k) for k in ("version", "installation_type", "arch",
                                                 "python_version")},
        "integration_version": meta.get("integration_version")
        or (raw.get("integration_manifest") or {}).get("version"),
        "generated_at": meta.get("generated_at"),
        "utc_offset_s": meta.get("utc_offset_s"),
        "entry": {"data": entry.get("data") or {}, "options": entry.get("options") or {}},
        "source": _source(d.get("source") or {}),
        "source_resolution": d.get("source_resolution"),
        "coordinator": d.get("coordinator"),
        "detector": d.get("detector"),
        "store": d.get("store"),
        "baseline": d.get("baseline"),
        "adaptive": d.get("adaptive"),
        "clusters": d.get("clusters"),
        "cop_analysis": d.get("cop_analysis"),
        "database": {
            "counts": db.get("counts"),
            "integrity_ok": db.get("integrity_ok"),
            "daily_summary": (db.get("extra") or {}).get("daily_summary"),
            "model_state": {k: v for k, v in (db.get("extra") or {}).items()
                            if k != "daily_summary"},
            "per_entry_counts": [v.get("counts") for v in (db.get("per_entry") or {}).values()
                                 if isinstance(v, dict)],
        },
        "alerts": d.get("alerts"),
        "bivalent": d.get("bivalent"),
        "defrost": d.get("defrost"),
        "buh": d.get("buh"),
        "sampling": d.get("sampling"),
        "coordinator_timing": d.get("coordinator_timing"),
        "entities": _entities(d.get("entities") or {}),
        "repairs": d.get("repairs"),
    }


def _summary(doc: dict[str, Any]) -> dict[str, Any]:
    opts = doc["entry"]["options"]
    data = doc["entry"]["data"]
    biv = doc.get("bivalent") or {}
    coord = doc.get("coordinator") or {}
    counts = (doc.get("database") or {}).get("counts") or {}
    return {
        "model": data.get("model"),
        "unit_model": (doc["source"]["attributes"] or {}).get("Unit model"),
        "integration_version": doc.get("integration_version"),
        "ha_version": doc["home_assistant"].get("version"),
        "source_type": data.get("source_type") or data.get("attribute_mode"),
        "source_chosen": (doc.get("source_resolution") or {}).get("chosen"),
        "is_hybrid": biv.get("is_hybrid"),
        "is_bivalent": biv.get("is_bivalent"),
        "dhw_present": coord.get("dhw_present"),
        "power_meter": bool(opts.get("power_sensor_entity")),
        "cycles": counts.get("cycles"),
        "cop_samples": counts.get("cop_samples"),
        "generated_at": doc.get("generated_at"),
    }


# ---------------------------------------------------------------- writing

def ingest(text: str, *, origin: str, note: str = "", out_dir: Path = OUT_DIR) -> Path:
    raw = load_lenient(text)
    entry_id = str(((raw.get("data") or {}).get("entry") or {}).get("entry_id") or "")
    anon = Anonymiser(entry_id)
    doc = anon.walk(trim(raw))
    doc["anon_id"] = anon.anon
    stamp = re.sub(r"[^0-9]", "", str(doc.get("generated_at") or ""))[:12] or "undated"
    model = re.sub(r"[^a-z0-9]", "", str(doc["entry"]["data"].get("model") or "unknown").lower())
    version = str(doc.get("integration_version") or "x").replace(".", "_")
    name = f"{model}_{version}_{anon.anon}_{stamp}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / name).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    index_path = out_dir / "INDEX.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else []
    index = [row for row in index if row.get("file") != name]
    index.append({"file": name, "anon_id": anon.anon, "origin": origin,
                  "note": note, **_summary(doc)})
    index.sort(key=lambda r: (r["anon_id"], str(r.get("generated_at"))))
    index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n")
    return out_dir / name


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--origin", choices=("user", "maintainer"), default="user")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args(argv)
    for f in args.files:
        path = ingest(Path(f).read_text(encoding="utf-8"), origin=args.origin,
                      note=args.note, out_dir=Path(args.out))
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
