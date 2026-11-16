"""Tests for create_issue.py: label normalization."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "create_issue", ROOT / "scripts" / "create_issue.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def test_normalize_single():
    assert ci.normalize_labels(["bug"]) == ["bug"]


def test_normalize_comma():
    assert ci.normalize_labels(["bug,chore"]) == ["bug", "chore"]


def test_normalize_comma_space():
    assert ci.normalize_labels(["bug, chore"]) == ["bug", "chore"]


def test_normalize_repeatable():
    assert ci.normalize_labels(["bug", "chore"]) == ["bug", "chore"]


def test_normalize_dedupe():
    assert ci.normalize_labels(["bug,chore", "bug"]) == ["bug", "chore"]


def test_normalize_empty():
    assert ci.normalize_labels([]) == []
    assert ci.normalize_labels([""]) == []
    assert ci.normalize_labels([",,"]) == []
