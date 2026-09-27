"""Batch 50d -- version contract + Silver IQS compliance."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(p: str) -> str:
    return (ROOT / p).read_text()


def test_version_1_0_0_in_const():
    src = _read("const.py")
    m = re.search(r'VERSION\s*=\s*"([^"]+)"', src)
    assert m, "VERSION not found in const.py"
    assert m.group(1) == "1.0.1"


def test_version_1_0_0_in_manifest():
    man = json.loads(_read("manifest.json"))
    assert man["version"] == "1.0.1"


def test_version_consistent_three_files():
    const_v = re.search(r'VERSION\s*=\s*"([^"]+)"', _read("const.py")).group(1)
    man_v = json.loads(_read("manifest.json"))["version"]
    proj_v = re.search(r'(?m)^version\s*=\s*"([^"]+)"', _read("pyproject.toml")).group(1)
    assert const_v == man_v == proj_v == "1.0.1"


def test_codeowners_present():
    man = json.loads(_read("manifest.json"))
    assert "codeowners" in man
    assert isinstance(man["codeowners"], list)
    assert len(man["codeowners"]) >= 1


def test_parallel_updates_in_platforms():
    for f in ["sensor.py", "binary_sensor.py"]:
        src = _read(f)
        assert "PARALLEL_UPDATES" in src, f"{f} mist PARALLEL_UPDATES"
        m = re.search(r"PARALLEL_UPDATES\s*=\s*([0-9]+)", src)
        assert m and m.group(1) == "0", f"{f} PARALLEL_UPDATES moet 0 zijn"


def test_iqs_manifest_exists():
    p = ROOT / "quality_scale.yaml"
    assert p.exists(), "quality_scale.yaml ontbreekt"


def test_ruff_clean_no_e501_churn_visible():
    # Sanity: E501 blijft geignoreerd (line-length=100, HA custom-component tolerantie)
    src = _read("pyproject.toml")
    assert "[tool.ruff" in src
    assert "E501" in src
    assert 'line-length = 100' in src or "line-length = 100" in src
