"""R327 (candidate) - Hassfest rejects leading/trailing whitespace in
all translation string values (\\n counts as whitespace).

Local R290 guard checks ICU braces only; this test catches the
whitespace case that Hassfest's translations validator enforces.
"""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_FILES = [
    "custom_components/daikin_cycle_ml/strings.json",
    "custom_components/daikin_cycle_ml/translations/en.json",
    "custom_components/daikin_cycle_ml/translations/nl.json",
]


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def test_no_leading_or_trailing_whitespace_in_translations():
    for rel in _FILES:
        data = json.loads((_ROOT / rel).read_text(encoding="utf-8"))
        for path, val in _walk(data):
            assert val == val.strip(), (
                f"{rel}:{path} has leading/trailing whitespace: {val!r}"
            )
