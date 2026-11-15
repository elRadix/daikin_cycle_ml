#!/usr/bin/env python3
"""G2 local CI gate - dual-mode (pre-commit + commit-msg).

Pre-commit: R826 ruff changed only, R830 new-vs-pre-existing, R857 Dutch
in CHANGELOG/README, R858 `|| echo 0`, R828 import gate.
Commit-msg: R857 English only, R846 Part-of vs Fixes consistency.

Exit codes: 0=OK 1=ruff 2=Dutch 3=R858 4=import 5=other 6=R846
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PYTHON = os.environ.get("DAIKIN_PYTHON") or sys.executable
DUTCH = ("geinvalideerd", "herberekening", "tijdens", "bevestigd",
         "aansloeg", "schreef", "nieuwe")
DUTCH_FILES = ("CHANGELOG.md", "README.md")
AUTOCLOSE = re.compile(r"\b(Fixes|Closes|Resolves)\s+#\d+", re.IGNORECASE)
PARTOF = re.compile(r"\bPart of\s+#\d+", re.IGNORECASE)
HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def fail(m, c):
    print(f"FAIL: {m}", file=sys.stderr)
    sys.exit(c)


def git(a):
    return subprocess.check_output(["git", *a], text=True)


def staged():
    return [f for f in git(["diff", "--cached", "--name-only",
                            "--diff-filter=ACMR"]).splitlines() if f]


def changed_py(fs):
    return [f for f in fs if f.endswith(".py")]


def check_dutch(files):
    hits = []
    for path in files:
        if not any(path.endswith(f) or path == f for f in DUTCH_FILES):
            continue
        p = Path(path)
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8",
                                             errors="replace").splitlines(), 1):
            low = line.lower()
            for w in DUTCH:
                if w in low:
                    hits.append((path, i, w))
    if hits:
        for path, ln, w in hits:
            print(f"  {path}:{ln}: '{w}'", file=sys.stderr)
        fail(f"Dutch in {len(hits)} locations (R857)", 2)


def check_r858(files):
    hits = []
    for path in files:
        if not path.endswith((".sh", ".bash")):
            continue
        p = Path(path)
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"\|\|\s*echo\s+0", text):
            ln = text[:m.start()].count("\n") + 1
            hits.append((path, ln, m.group(0)))
    if hits:
        for path, ln, mt in hits:
            print(f"  {path}:{ln}: {mt!r}", file=sys.stderr)
        fail("R858 unsafe '|| echo 0' - use 2>/dev/null + ${VAR:-0}", 3)


def added_lines(path):
    try:
        diff = git(["diff", "--cached", "-U0", "--", path])
    except subprocess.CalledProcessError:
        return set()
    out = set()
    for h in HUNK.finditer(diff):
        s = int(h.group(1))
        c = int(h.group(2) or 1)
        out.update(range(s, s + c))
    return out


def run_ruff(files):
    py = changed_py(files)
    if not py:
        return
    if not shutil.which("ruff"):
        print("WARN: ruff not in PATH, skip", file=sys.stderr)
        return
    r = subprocess.run(["ruff", "check", "--config", "pyproject.toml",
                        "--output-format", "json", *py],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return
    try:
        issues = json.loads(r.stdout) if r.stdout else []
    except json.JSONDecodeError:
        fail(f"ruff output not JSON: {r.stderr[:200]}", 1)
    new, pre = [], []
    for iss in issues:
        path = iss.get("filename", "")
        for p in py:
            if path.endswith(p):
                path = p
                break
        row = iss.get("location", {}).get("row", 0)
        (new if row in added_lines(path) else pre).append(iss)
    if pre:
        print(f"WARN: {len(pre)} pre-existing ruff issues (R830):",
              file=sys.stderr)
        for iss in pre[:5]:
            print(f"  {iss['filename']}:{iss['location']['row']} "
                  f"{iss.get('code')}", file=sys.stderr)
    if new:
        for iss in new:
            print(f"  {iss['filename']}:{iss['location']['row']} "
                  f"{iss.get('code')}: {iss.get('message')}",
                  file=sys.stderr)
        fail(f"{len(new)} NEW ruff issues (R830)", 1)


def run_import(files):
    for path in changed_py(files):
        if not path.startswith("custom_components/daikin_cycle_ml/"):
            continue
        if "/tests/" in path or path.startswith("tests/"):
            continue
        mod = path.replace("/", ".").removesuffix(".py")
        if mod.endswith(".__init__"):
            mod = mod.removesuffix(".__init__")
        r = subprocess.run([PYTHON, "-c", f"import {mod}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            fail(f"import gate R828: {mod}\n{r.stderr[:300]}", 4)


def pre_commit():
    fs = staged()
    if not fs:
        print("no staged files")
        return
    print(f"G2: {len(fs)} staged files")
    check_dutch(fs)
    check_r858(fs)
    run_ruff(fs)
    run_import(fs)
    print("G2 pre-commit PASS")


def commit_msg(path):
    p = Path(path)
    if not p.exists():
        fail(f"msg file missing: {path}", 5)
    text = "\n".join(
        l for l in p.read_text(encoding="utf-8", errors="replace").splitlines()
        if l and not l.startswith("#"))
    if not text:
        return
    dutch = [w for w in DUTCH if w in text.lower()]
    if dutch:
        fail(f"Dutch in commit msg (R857): {sorted(set(dutch))}", 2)
    has_p = bool(PARTOF.search(text))
    has_a = bool(AUTOCLOSE.search(text))
    if has_p and has_a:
        fail("Part of #N + Fixes/Closes #N together (R846)", 6)
    print("G2 commit-msg PASS")


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return
    if len(sys.argv) >= 2 and Path(sys.argv[1]).is_file():
        commit_msg(sys.argv[1])
    else:
        pre_commit()


if __name__ == "__main__":
    main()
