"""R299 - structural contract test.

Every CopSample(...) construction in custom_components/ MUST pass
data_quality= explicitly. The dataclass default is 'unknown', which
fails CopSample.valid and silently drops the sample from bucket_summary.

Audit (2026-10-06): two sites, both safe (cop_analyzer.py:132 reads from
attrs with default 'unknown' by design; coordinator.py:1461 sets 'Good').
This test freezes the contract so future construction sites cannot
silently omit the field.
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent / "custom_components"


def _cop_sample_calls():
    for py in ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None
            )
            if name == "CopSample":
                yield py, node


def test_every_cop_sample_construction_sets_data_quality() -> None:
    missing: list[str] = []
    for py, node in _cop_sample_calls():
        kwargs = {kw.arg for kw in node.keywords}
        if "data_quality" not in kwargs:
            rel = py.relative_to(ROOT.parent)
            missing.append(f"{rel}:{node.lineno}")
    assert not missing, (
        "CopSample() without data_quality= (silently drops from "
        f"bucket_summary): {missing}"
    )
