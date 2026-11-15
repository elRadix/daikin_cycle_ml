#!/usr/bin/env python3
"""Safe issue creation with body-file verification (R841).

Body via --body-file only (never --body). Verifies content post-create.
Refuses if Dutch detected (R857).

Exit codes: 0=OK 1=Dutch 2=body missing 3=gh create fail 4=verify mismatch
"""
import argparse
import subprocess
import sys
from pathlib import Path

DUTCH = ("geinvalideerd", "herberekening", "tijdens", "bevestigd",
         "aansloeg", "schreef", "nieuwe")


def fail(m, c):
    print(f"FAIL: {m}", file=sys.stderr)
    sys.exit(c)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--title", required=True)
    p.add_argument("--body-file", required=True, type=Path)
    p.add_argument("--labels", default="")
    p.add_argument("--repo", default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if not a.body_file.exists():
        fail(f"body-file not found: {a.body_file}", 2)
    body = a.body_file.read_text(encoding="utf-8")
    if not body.strip():
        fail("body-file empty", 2)

    dutch = [w for w in DUTCH if w in body.lower()]
    if dutch:
        fail(f"Dutch detected (R857): {sorted(set(dutch))}", 1)

    if a.dry_run:
        print(f"DRY-RUN: would create '{a.title}' ({len(body)}B)")
        return

    cmd = ["gh", "issue", "create", "--title", a.title,
           "--body-file", str(a.body_file)]
    if a.labels:
        cmd += ["--label", a.labels]
    if a.repo:
        cmd += ["--repo", a.repo]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
    except subprocess.CalledProcessError as e:
        fail(f"gh create failed: {e}", 3)

    try:
        n = int(out.rstrip("/").rsplit("/", 1)[-1])
    except ValueError:
        fail(f"cannot parse issue # from: {out}", 3)

    view_cmd = ["gh", "issue", "view", str(n),
                "--json", "body", "-q", ".body"]
    if a.repo:
        view_cmd += ["--repo", a.repo]
    view = subprocess.check_output(view_cmd, text=True)
    if view.rstrip() != body.rstrip():
        fail(f"body mismatch (sent {len(body)}B got {len(view)}B)", 4)
    print(n)


if __name__ == "__main__":
    main()
