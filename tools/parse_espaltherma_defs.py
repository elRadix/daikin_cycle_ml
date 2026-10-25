#!/usr/bin/env python3
"""Parse ESPAltherma .h files into MODEL_ATTRIBUTES.json.

Both commented (//{...}) and uncommented ({...}) struct-init lines are parsed;
the union is the compatibility set.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LABEL_RE = re.compile(r'\{[^{}"]*"([^{}"]+)"[^{}"]*\}')
_DEFS_DIR = "definitions"


def _git(repo: Path, *args: str, default: str = "unknown") -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), *args],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return default


def _parse_file(path: Path) -> set[str]:
    return set(_LABEL_RE.findall(path.read_text(encoding="utf-8", errors="replace")))


def _collect(source: Path) -> tuple[dict[str, list[str]], list[str]]:
    defs = source / _DEFS_DIR
    if not defs.is_dir():
        raise SystemExit(f"missing definitions dir: {defs}")
    models = sorted(p.name for p in defs.glob("*.h") if p.is_file())
    labels: dict[str, list[str]] = {}
    for name in models:
        for label in _parse_file(defs / name):
            labels.setdefault(label, []).append(name)
    for label in labels:
        labels[label] = sorted(labels[label])
    return labels, models


def _ordered_labels(new: dict[str, list[str]], prior: dict[str, Any] | None) -> dict[str, list[str]]:
    if not prior:
        return dict(sorted(new.items()))
    order = list(prior.get("labels", {}).keys())
    out = {k: new[k] for k in order if k in new}
    for k in sorted(new):
        if k not in out:
            out[k] = new[k]
    return out


def _build(source: Path, branch: str | None, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    labels, models = _collect(source)
    ordered = _ordered_labels(labels, prior)
    return {
        "_meta": {
            "source": "https://github.com/raomin/ESPAltherma",
            "branch": branch or _git(source, "rev-parse", "--abbrev-ref", "HEAD"),
            "commit": _git(source, "rev-parse", "HEAD"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "note": (
                "ESPAltherma definitions are TEMPLATES. Users uncomment the labels "
                "they need. This index includes both active and commented labels — "
                "the union is the compatibility set the resolver must accept."
            ),
            "root_model_count": len(models),
            "unique_labels": len(ordered),
        },
        "models": models,
        "labels": ordered,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("docs/MODEL_ATTRIBUTES.json"))
    ap.add_argument("--branch", default=None)
    args = ap.parse_args(argv)
    if not args.source.is_dir():
        print(f"error: source not a directory: {args.source}")
        return 2
    prior = None
    if args.out.exists():
        prior = json.loads(args.out.read_text(encoding="utf-8"))
    payload = _build(args.source, args.branch, prior=prior)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.out} — {payload['_meta']['unique_labels']} labels, "
        f"{payload['_meta']['root_model_count']} models, "
        f"commit={payload['_meta']['commit'][:8]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
