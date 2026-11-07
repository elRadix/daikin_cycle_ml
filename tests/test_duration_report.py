"""Tests for scripts/duration_report.py (R656 duration tracker).

R670-compliant: no sys.path manipulation. Uses importlib.util.
spec_from_file_location for granular function tests, plus one real
subprocess end-to-end CLI test to prove the script works standalone.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


def _load_module():
    """Load scripts/duration_report.py as a module (no sys.path changes)."""
    spec = importlib.util.spec_from_file_location(
        "duration_report",
        Path(__file__).parent.parent / "scripts" / "duration_report.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()

# 4 tests: pass, fail, error, skip. Durations: 0.5, 1.2, 0.3, 0.1 -> total 2.1s
# 2 files: test_a (0.5+1.2=1.7), test_b (0.3+0.1=0.4)
BASIC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1">
  <testcase classname="tests.test_a" name="test_pass" time="0.5"/>
  <testcase classname="tests.test_a" name="test_fail" time="1.2">
    <failure message="assert False"/>
  </testcase>
  <testcase classname="tests.test_b" name="test_err" time="0.3">
    <error message="boom"/>
  </testcase>
  <testcase classname="tests.test_b" name="test_skip" time="0.1">
    <skipped/>
  </testcase>
</testsuite>"""


def _write_xml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "junit.xml"
    p.write_text(content)
    return p


# ---------- parse_junit_xml ----------


def test_parse_junit_xml_basic(tmp_path):
    data = _mod.parse_junit_xml(_write_xml(tmp_path, BASIC_XML))
    assert data["total_s"] == pytest.approx(2.1)
    assert len(data["tests"]) == 4


def test_parse_junit_xml_outcome_detection(tmp_path):
    data = _mod.parse_junit_xml(_write_xml(tmp_path, BASIC_XML))
    outcomes = {n: o for n, _, o in data["tests"]}
    assert outcomes["tests.test_a::test_pass"] == "passed"
    assert outcomes["tests.test_a::test_fail"] == "failed"
    assert outcomes["tests.test_b::test_err"] == "error"
    assert outcomes["tests.test_b::test_skip"] == "skipped"


def test_parse_junit_xml_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        _mod.parse_junit_xml(tmp_path / "nope.xml")


def test_parse_junit_xml_malformed_raises(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text("<not-valid-xml")
    with pytest.raises(ET.ParseError):
        _mod.parse_junit_xml(p)


def test_parse_junit_xml_testsuites_root(tmp_path):
    multi = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="a"><testcase classname="tests.test_x" name="t1" time="0.5"/></testsuite>
  <testsuite name="b"><testcase classname="tests.test_y" name="t2" time="1.5"/></testsuite>
</testsuites>"""
    data = _mod.parse_junit_xml(_write_xml(tmp_path, multi))
    assert data["total_s"] == pytest.approx(2.0)
    assert len(data["tests"]) == 2


# ---------- summarize ----------


def test_summarize_per_file_and_top(tmp_path):
    data = _mod.parse_junit_xml(_write_xml(tmp_path, BASIC_XML))
    s = _mod.summarize(data, top_n=2)
    assert s["total_s"] == pytest.approx(2.1)
    assert s["count"] == 4
    assert s["per_file_s"]["tests.test_a"] == pytest.approx(1.7)
    assert s["per_file_s"]["tests.test_b"] == pytest.approx(0.4)
    assert len(s["top_slowest"]) == 2
    assert s["top_slowest"][0]["nodeid"] == "tests.test_a::test_fail"
    assert s["top_slowest"][0]["duration_s"] == pytest.approx(1.2)


# ---------- check_baseline ----------


def _empty_summary(total_s: float) -> dict:
    return {"total_s": total_s, "count": 100, "per_file_s": {}, "top_slowest": []}


def test_check_baseline_empty_total_returns_0(tmp_path):
    baseline = tmp_path / "b.json"
    baseline.write_text(json.dumps({"total_s": 0, "count": 0}))
    assert _mod.check_baseline(_empty_summary(5.0), baseline, 50.0) == 0


def test_check_baseline_missing_returns_2(tmp_path):
    assert _mod.check_baseline(
        _empty_summary(5.0), tmp_path / "nope.json", 50.0,
    ) == 2


def test_check_baseline_within_tolerance_returns_0(tmp_path):
    baseline = tmp_path / "b.json"
    baseline.write_text(json.dumps({"total_s": 10.0, "count": 100}))
    # 12 <= 10 + 50% = 15 -> OK
    assert _mod.check_baseline(_empty_summary(12.0), baseline, 50.0) == 0


def test_check_baseline_exceeds_tolerance_returns_1(tmp_path):
    baseline = tmp_path / "b.json"
    baseline.write_text(json.dumps({"total_s": 10.0, "count": 100}))
    # 20 > 10 * 1.5 = 15 -> REGRESSION
    assert _mod.check_baseline(_empty_summary(20.0), baseline, 50.0) == 1


# ---------- main (CLI) ----------


def test_main_with_json_out(tmp_path):
    p = _write_xml(tmp_path, BASIC_XML)
    out = tmp_path / "summary.json"
    rc = _mod.main([str(p), "--top", "2", "--json-out", str(out)])
    assert rc == 0
    assert out.is_file()
    s = json.loads(out.read_text())
    assert s["total_s"] == pytest.approx(2.1)
    assert s["count"] == 4


def test_main_invalid_xml_returns_2(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text("<not-xml")
    assert _mod.main([str(p)]) == 2


def test_main_with_baseline_ok(tmp_path):
    p = _write_xml(tmp_path, BASIC_XML)
    baseline = tmp_path / "b.json"
    baseline.write_text(json.dumps({"total_s": 2.0, "count": 4}))
    # 2.1 is within 2.0 * 1.5 = 3.0
    rc = _mod.main([str(p), "--baseline", str(baseline)])
    assert rc == 0


def test_cli_subprocess_end_to_end(tmp_path):
    """End-to-end: real subprocess, verify exit code + output format."""
    p = _write_xml(tmp_path, BASIC_XML)
    repo_root = Path(__file__).parent.parent
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "duration_report.py"),
            str(p),
            "--top", "2",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    assert "Total: 2.10s" in proc.stdout
    assert "test_fail" in proc.stdout
    assert "Per-file totals" in proc.stdout
