#!/usr/bin/env python3
"""Safe issue creation with body-file verification (R841).

Body via --body-file only (never --body). Verifies content post-create.
Labels: --label/--labels accept comma-separated, repeatable.
Pre-validated against gh labels unless --skip-label-check.
Exit: 0=OK 2=body missing 3=gh fail 4=verify mismatch 5=unknown label
"""
import argparse
import subprocess
import sys
from pathlib import Path


def fail(m, c):
    print(f"FAIL: {m}", file=sys.stderr)
    sys.exit(c)


def normalize_labels(entries):
    seen = []
    for e in entries or []:
        for x in e.split(","):
            x = x.strip()
            if x and x not in seen:
                seen.append(x)
    return seen


def fetch_valid_labels(repo=None):
    cmd = ["gh", "label", "list", "--limit", "200",
           "--json", "name", "-q", ".[].name"]
    if repo:
        cmd += ["--repo", repo]
    try:
        out = subprocess.check_output(cmd, text=True)
        return sorted({ln.strip() for ln in out.splitlines() if ln.strip()})
    except subprocess.CalledProcessError:
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--title", default=None)
    p.add_argument("--body-file", default=None, type=Path)
    p.add_argument("--label", "--labels", dest="labels",
                   action="append", default=[])
    p.add_argument("--list-labels", action="store_true")
    p.add_argument("--skip-label-check", action="store_true")
    p.add_argument("--repo", default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.list_labels:
        valid = fetch_valid_labels(a.repo)
        if valid is None:
            fail("cannot fetch labels via gh", 3)
        for name in valid:
            print(name)
        return

    if not a.title or not a.body_file:
        fail("--title and --body-file required (unless --list-labels)", 2)
    if not a.body_file.exists():
        fail(f"body-file not found: {a.body_file}", 2)
    body = a.body_file.read_text(encoding="utf-8")
    if not body.strip():
        fail("body-file empty", 2)

    labels = normalize_labels(a.labels)
    if labels and not a.skip_label_check:
        valid = fetch_valid_labels(a.repo)
        if valid is not None:
            unknown = [x for x in labels if x not in valid]
            if unknown:
                print(f"FAIL: unknown labels: {unknown}", file=sys.stderr)
                print(f"valid labels: {', '.join(valid)}", file=sys.stderr)
                sys.exit(5)

    if a.dry_run:
        print(f"DRY-RUN: create '{a.title}' labels={labels} ({len(body)}B)")
        return

    cmd = ["gh", "issue", "create", "--title", a.title,
           "--body-file", str(a.body_file)]
    for label in labels:
        cmd += ["--label", label]
    if a.repo:
        cmd += ["--repo", a.repo]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
    except subprocess.CalledProcessError:
        fail("gh create failed", 3)

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
