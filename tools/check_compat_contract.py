#!/usr/bin/env python3
"""Verify the model-compatibility contract.

Called by .github/workflows/model-compat.yml (pr-gate). Compares the
tracked docs/MODEL_ATTRIBUTES.json against a freshly parsed upstream
tree and asserts the engine can resolve every canonical label.

ALIAS_GROUPS is loaded by file path, not by package import: importing
custom_components.daikin_cycle_ml runs __init__.py, which requires Home
Assistant. attribute_compat.py is intentionally dependency-free, and this
loader enforces that invariant.

Exit codes: 0 contract holds, 1 violation, 2 usage/IO error.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

EXPECTED_MODEL_COUNT = 39

# Attributes that LOOK canonical but are not. Mirrors DECOYS in
# tests/test_model_compat.py.
DECOYS: tuple[str, ...] = (
    "Heat exchanger mid-temp.(R5T)",
    "O/U Heat Exch. Temp.(R4T)",
    "Indoor ambient temp. (R1T)",
)


def load_alias_groups(compat_path: Path) -> dict[str, tuple[str, ...]]:
    """Load ALIAS_GROUPS without importing the integration package."""
    spec = importlib.util.spec_from_file_location("_compat_probe", compat_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"error: cannot load {compat_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw: Any = getattr(module, "ALIAS_GROUPS", None)
    if not isinstance(raw, dict) or not raw:
        raise SystemExit(f"error: ALIAS_GROUPS missing in {compat_path}")
    groups: dict[str, tuple[str, ...]] = {
        str(k): tuple(str(v) for v in vals) for k, vals in raw.items()
    }
    return groups


def check(
    tracked: dict[str, Any],
    regen: dict[str, Any],
    groups: dict[str, tuple[str, ...]],
) -> list[str]:
    """Return a list of human-readable contract violations (empty = OK)."""
    failures: list[str] = []
    labels = set(tracked["labels"])
    regen_labels = set(regen["labels"])

    only_tracked = sorted(labels - regen_labels)
    only_regen = sorted(regen_labels - labels)
    if only_tracked or only_regen:
        failures.append(
            f"label set drift: {len(only_tracked)} only-tracked, "
            f"{len(only_regen)} only-regen"
        )
        for lbl in only_tracked[:5]:
            failures.append(f"  only tracked: {lbl!r}")
        for lbl in only_regen[:5]:
            failures.append(f"  only regen:   {lbl!r}")

    models = tracked["models"]
    if len(models) != EXPECTED_MODEL_COUNT:
        failures.append(f"model count {len(models)} != {EXPECTED_MODEL_COUNT}")
    if tracked["_meta"].get("root_model_count") != len(models):
        failures.append("_meta.root_model_count disagrees with models list")

    for canonical in sorted(groups):
        variants = (canonical, *groups[canonical])
        if not any(v in labels for v in variants):
            failures.append(
                f"canonical {canonical!r} unresolvable; tried {list(variants)}"
            )

    for decoy in DECOYS:
        if decoy in groups:
            failures.append(f"decoy {decoy!r} promoted to canonical")

    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tracked", type=Path, required=True)
    ap.add_argument("--regen", type=Path, required=True)
    ap.add_argument("--compat", type=Path, required=True)
    args = ap.parse_args(argv)

    try:
        tracked: dict[str, Any] = json.loads(args.tracked.read_text(encoding="utf-8"))
        regen: dict[str, Any] = json.loads(args.regen.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        print(f"error: {err}")
        return 2

    groups = load_alias_groups(args.compat)
    failures = check(tracked, regen, groups)

    if failures:
        print("::error::compatibility contract violated")
        for line in failures:
            print(line)
        return 1

    print(
        f"OK: {len(tracked['labels'])} labels, {len(tracked['models'])} models, "
        f"{len(groups)} canonical labels, {len(DECOYS)} decoys clean"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
