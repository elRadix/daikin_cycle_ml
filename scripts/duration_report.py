#!/usr/bin/env python3
"""Test duration reporter (R656).

Parses pytest JUnit XML and prints:
  - total wall-clock time from XML (sum of test times)
  - per-file aggregated duration, sorted desc
  - top-N slowest individual tests (default 25)
  - optional baseline comparison (regression = exit 1)

JUnit XML is produced by pytest's built-in --junit-xml option:
    pytest --junit-xml=/tmp/pytest.xml

Usage:
    python3 scripts/duration_report.py /tmp/pytest.xml
    python3 scripts/duration_report.py /tmp/pytest.xml --top 25
    python3 scripts/duration_report.py /tmp/pytest.xml \\
        --baseline tests/duration_baseline.json --tolerance-pct 50

Exit codes:
    0  OK, no regression
    1  Regression exceeded tolerance
    2  Bad input (missing/malformed XML, missing baseline)
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_junit_xml(xml_path: Path) -> dict:
    """Return {'total_s': float, 'tests': [(nodeid, duration_s, outcome)]}."""
    if not xml_path.is_file():
        raise FileNotFoundError(f"XML not found: {xml_path}")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = list(root.iter("testsuite"))
    else:
        suites = list(root.iter("testsuite"))
    tests: list[tuple[str, float, str]] = []
    for suite in suites:
        for tc in suite.iter("testcase"):
            classname = tc.get("classname") or ""
            name = tc.get("name") or "?"
            nodeid = f"{classname}::{name}" if classname else name
            try:
                duration = float(tc.get("time") or "0")
            except ValueError:
                duration = 0.0
            outcome = "passed"
            if tc.find("failure") is not None:
                outcome = "failed"
            elif tc.find("error") is not None:
                outcome = "error"
            elif tc.find("skipped") is not None:
                outcome = "skipped"
            tests.append((nodeid, duration, outcome))
    total_s = sum(t[1] for t in tests)
    return {"total_s": total_s, "tests": tests}


def summarize(data: dict, top_n: int = 25) -> dict:
    """Compute per-file aggregation and top-N slowest tests."""
    tests = data["tests"]
    per_file: dict[str, float] = {}
    for nodeid, dur, _ in tests:
        fname = nodeid.split("::", 1)[0]
        per_file[fname] = per_file.get(fname, 0.0) + dur
    top = sorted(tests, key=lambda t: t[1], reverse=True)[:top_n]
    return {
        "total_s": round(data["total_s"], 3),
        "count": len(tests),
        "per_file_s": {
            k: round(v, 3)
            for k, v in sorted(per_file.items(), key=lambda kv: kv[1], reverse=True)
        },
        "top_slowest": [
            {"nodeid": n, "duration_s": round(d, 3), "outcome": o}
            for n, d, o in top
        ],
    }


def print_report(summary: dict, top_n: int) -> None:
    print(f"Total: {summary['total_s']:.2f}s over {summary['count']} tests")
    print()
    print(f"Top {top_n} slowest tests:")
    for i, t in enumerate(summary["top_slowest"], 1):
        print(f"  {i:2d}. {t['duration_s']:7.3f}s  [{t['outcome']:7s}]  {t['nodeid']}")
    print()
    print("Per-file totals (top 20):")
    for i, (f, s) in enumerate(list(summary["per_file_s"].items())[:20], 1):
        print(f"  {i:2d}. {s:7.3f}s  {f}")


def check_baseline(summary: dict, baseline_path: Path, tolerance_pct: float) -> int:
    if not baseline_path.is_file():
        print(f"FATAL: baseline not found: {baseline_path}", file=sys.stderr)
        return 2
    baseline = json.loads(baseline_path.read_text())
    base_total = float(baseline.get("total_s", 0.0))
    if base_total <= 0:
        print()
        print("Baseline has no total_s yet; skipping comparison.")
        print("Fill it with a clean full-suite run and commit.")
        return 0
    current = summary["total_s"]
    delta = current - base_total
    delta_pct = (delta / base_total) * 100.0 if base_total else 0.0
    limit = base_total * (1 + tolerance_pct / 100.0)
    print()
    print(f"Baseline total: {base_total:.2f}s")
    print(f"Current total:  {current:.2f}s")
    print(f"Delta:          {delta:+.2f}s ({delta_pct:+.1f}%)")
    print(f"Tolerance:      +{tolerance_pct:.0f}% (limit {limit:.2f}s)")
    if current > limit:
        print("REGRESSION: current total exceeds baseline + tolerance", file=sys.stderr)
        return 1
    print("OK: within tolerance.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Report pytest durations from JUnit XML (R656).",
    )
    ap.add_argument("xml", type=Path, help="Path to pytest --junit-xml output")
    ap.add_argument("--top", type=int, default=25, help="Top-N slowest tests")
    ap.add_argument("--baseline", type=Path, default=None,
                    help="Optional baseline JSON for regression check")
    ap.add_argument("--tolerance-pct", type=float, default=50.0,
                    help="Regression tolerance (%%, default 50)")
    ap.add_argument("--json-out", type=Path, default=None,
                    help="Optionally dump structured summary here")
    args = ap.parse_args(argv)
    try:
        data = parse_junit_xml(args.xml)
    except (FileNotFoundError, ET.ParseError) as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    summary = summarize(data, top_n=args.top)
    print_report(summary, top_n=args.top)
    if args.json_out:
        args.json_out.write_text(json.dumps(summary, indent=2))
    if args.baseline is not None:
        return check_baseline(summary, args.baseline, args.tolerance_pct)
    return 0


if __name__ == "__main__":
    sys.exit(main())
