"""Batch 51b -- translation key consistency."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ISSUES = ["db_corrupt", "notify_failed", "migration_failed"]


def _load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


@pytest.mark.parametrize("rel", ["strings.json", "translations/en.json", "translations/nl.json"])
def test_issue_keys_present(rel):
    data = _load(rel)
    issues = data.get("issues", {})
    for key in ISSUES:
        assert key in issues, rel + " missing issue " + key
        assert "title" in issues[key]
        assert "description" in issues[key]
