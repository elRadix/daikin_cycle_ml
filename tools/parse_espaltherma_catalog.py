#!/usr/bin/env python3
"""ESPAltherma v2 catalog -> docs/ESPALTHERMA_V2_CATALOG.json (#413).

ESPAltherma v2 (beta.30+) ships ``data/catalog_names.txt``: the names of
every value per definition, which are the MQTT keys and the Home
Assistant ids (``sensor.espaltherma_<key>``). v2 publishes some values
under another name than the definition file (``I/U ...`` / ``O/U ...``
when a name exists on both sides), so the v2 source is checked against
this catalog. v1 keeps using the definition names (MODEL_ATTRIBUTES.json).

Firmware-computed values (``Stats: ...``, ``Unit model``) are not in the
catalog; they are collected from the ``{"<name>", ESP_SENSOR_...}`` tables
in ``src/`` and ``include/``.

Usage:
    python3 tools/parse_espaltherma_catalog.py --source /tmp/espaltherma \\
        --branch beta --out docs/ESPALTHERMA_V2_CATALOG.json
    python3 tools/parse_espaltherma_catalog.py --diff OLD.json NEW.json
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

CATALOG_FILE = "data/catalog_names.txt"
_EXTRA_RE = re.compile(r'\{\s*"([^"]+)"\s*,\s*ESP_SENSOR_[A-Z_]+\s*\}')
# A section header is "[<definition name>]"; value names may also start
# with "[" ("[HPSU] Tv inflow Temp  (R1T)") but never end with "]" after
# a "] " (the bracketed prefix is followed by text).
_SECTION_RE = re.compile(r"^\[(.+)\]$")


def _git(repo: Path, *args: str, default: str = "unknown") -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return default


def parse_catalog_text(text: str) -> dict[str, list[str]]:
    """Return {definition: sorted names} from catalog_names.txt content."""
    out: dict[str, set[str]] = {}
    section: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        m = _SECTION_RE.match(line)
        if m and "] " not in line:
            section = m.group(1)
            out.setdefault(section, set())
            continue
        if section is None:
            raise ValueError(f"value before the first section: {line!r}")
        out[section].add(line)
    return {k: sorted(v) for k, v in sorted(out.items())}


def parse_extras(source: Path) -> list[str]:
    """Names of the firmware-computed values (Stats etc.)."""
    names: set[str] = set()
    for sub in ("src", "include"):
        base = source / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix in {".cpp", ".h"} and path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                names.update(_EXTRA_RE.findall(text))
    return sorted(names)


def build(source: Path, branch: str) -> dict[str, Any]:
    path = source / CATALOG_FILE
    if not path.is_file():
        raise SystemExit(f"missing {CATALOG_FILE} in {source} (needs ESPAltherma v2 beta.30+)")
    return {
        "_meta": {
            "source": "raomin/ESPAltherma",
            "branch": branch,
            "commit": _git(source, "rev-parse", "HEAD"),
            "commit_date": _git(source, "log", "-1", "--format=%cs"),
            "file": CATALOG_FILE,
            "note": "ESPAltherma v2 names (MQTT keys / HA ids). v1 uses MODEL_ATTRIBUTES.json.",
        },
        "definitions": parse_catalog_text(path.read_text(encoding="utf-8")),
        "extras": parse_extras(source),
    }


def all_names(catalog: dict[str, Any]) -> set[str]:
    names: set[str] = set(catalog.get("extras", []))
    for values in catalog.get("definitions", {}).values():
        names.update(values)
    return names


def diff(old: dict[str, Any], new: dict[str, Any], consumed: set[str]) -> dict[str, Any]:
    """Names removed / added between two snapshots; consumed ones flagged."""
    o, n = all_names(old), all_names(new)
    removed, added = sorted(o - n), sorted(n - o)
    per_def: dict[str, list[str]] = {}
    old_defs, new_defs = old.get("definitions", {}), new.get("definitions", {})
    for name in sorted(set(old_defs) & set(new_defs)):
        gone = sorted(set(old_defs[name]) - set(new_defs[name]))
        if gone:
            per_def[name] = gone
    return {
        "removed": removed,
        "added": added,
        "removed_consumed": sorted(set(removed) & consumed),
        "removed_per_definition": per_def,
        "definitions_removed": sorted(set(old_defs) - set(new_defs)),
        "definitions_added": sorted(set(new_defs) - set(old_defs)),
    }


def diff_markdown(d: dict[str, Any]) -> str:
    def lst(items: list[str]) -> str:
        return "\n".join(f"- `{x}`" for x in items) or "- none"

    parts = [
        "### Removed names the integration reads (action needed)",
        lst(d["removed_consumed"]),
        "### Removed names (all)",
        lst(d["removed"]),
        "### Added names",
        lst(d["added"]),
        "### Definitions removed / added",
        lst(d["definitions_removed"]),
        lst(d["definitions_added"]),
    ]
    return "\n\n".join(parts) + "\n"


def _module_assign(path: Path, name: str) -> Any:
    """Literal value of a top-level assignment, without importing the
    integration (the CI drift job has no Home Assistant installed)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == name and node.value is not None:
            return ast.literal_eval(node.value)
    raise KeyError(f"{name} not in {path}")


def consumed_names(repo: Path) -> set[str]:
    """Consumed labels, their aliases and v2 side names (what v2 reads)."""
    base = repo / "custom_components" / "daikin_cycle_ml"
    spec = importlib.util.spec_from_file_location("_dcml_const", base / "const.py")
    if spec is None or spec.loader is None:  # pragma: no cover - file is in the repo
        raise SystemExit("cannot load const.py")
    const = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(const)  # const.py imports only typing
    consumed = const.CONSUMED_ATTRIBUTES
    aliases = _module_assign(base / "engine" / "attribute_compat.py", "ALIAS_GROUPS")
    prefixes = _module_assign(base / "engine" / "attribute_compat.py", "SIDE_PREFIXES")
    out: set[str] = set()
    for label in consumed:
        for name in (label, *aliases.get(label, ())):
            out.add(name)
            out.update(p + name for p in prefixes)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--source", type=Path)
    ap.add_argument("--branch", default="beta")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--diff", nargs=2, type=Path, metavar=("OLD", "NEW"))
    args = ap.parse_args(argv)
    if args.diff:
        old, new = (json.loads(p.read_text(encoding="utf-8")) for p in args.diff)
        repo = Path(__file__).resolve().parent.parent
        sys.stdout.write(diff_markdown(diff(old, new, consumed_names(repo))))
        return 0
    if not args.source or not args.out:
        ap.error("--source and --out are required (or use --diff)")
    data = build(args.source, args.branch)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: {len(data['definitions'])} definitions, "
          f"{len(all_names(data))} names, commit {data['_meta']['commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
