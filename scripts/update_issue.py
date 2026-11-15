#!/usr/bin/env python3
"""Section-replacement in issue body (R860 line-anchored).

Pattern MUST start with ^. Replaces up to next H2 (## ...) or EOF.
Requires exactly one match unless --allow-multi. Refuses Dutch (R857).

Exit codes: 0=OK 1=Dutch 2=pattern fail 3=multi-match 4=gh fail
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DUTCH = ("geinvalideerd", "herberekening", "tijdens", "bevestigd",
         "aansloeg", "schreef", "nieuwe")
H2 = re.compile(r"^## ", re.MULTILINE)


def fail(m, c):
    print(f"FAIL: {m}", file=sys.stderr)
    sys.exit(c)


def fetch(issue, repo):
    c = ["gh", "issue", "view", str(issue),
         "--json", "body", "-q", ".body"]
    if repo:
        c += ["--repo", repo]
    try:
        return subprocess.check_output(c, text=True)
    except subprocess.CalledProcessError as e:
        fail(f"view failed: {e}", 4)


def replace(body, pat, blk, multi):
    ms = list(re.compile(pat, re.MULTILINE).finditer(body))
    if not ms:
        fail(f"pattern not found: {pat!r}", 2)
    if len(ms) > 1 and not multi:
        fail(f"pattern matched {len(ms)}x", 3)
    out = body
    for m in reversed(ms):
        tail = body[m.end():]
        nx = H2.search(tail)
        end = m.end() + (nx.start() if nx else len(tail))
        out = out[:m.start()] + blk.rstrip() + "\n\n" + out[end:]
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--pattern", required=True)
    p.add_argument("--new-block-file", required=True, type=Path)
    p.add_argument("--repo", default=None)
    p.add_argument("--allow-multi", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true")
    a = p.parse_args()

    if not a.pattern.startswith(("^", "(?m)^")):
        fail("pattern must be line-anchored (start with ^) per R860", 2)
    if not a.new_block_file.exists():
        fail(f"block missing: {a.new_block_file}", 2)
    blk = a.new_block_file.read_text(encoding="utf-8")
    if not blk.strip():
        fail("block empty", 2)
    dutch = [w for w in DUTCH if w in blk.lower()]
    if dutch:
        fail(f"Dutch (R857): {sorted(set(dutch))}", 1)

    body = fetch(a.issue, a.repo)
    new = replace(body, a.pattern, blk, a.allow_multi)
    if new == body:
        print("no change", file=sys.stderr)
        return
    if a.dry_run:
        print(f"DRY-RUN: would update #{a.issue}")
        return
    if not a.yes:
        ans = input(f"Apply to #{a.issue}? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("aborted", file=sys.stderr)
            return

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as f:
        f.write(new)
        tmp = f.name
    c = ["gh", "issue", "edit", str(a.issue), "--body-file", tmp]
    if a.repo:
        c += ["--repo", a.repo]
    try:
        subprocess.check_call(c)
    except subprocess.CalledProcessError as e:
        fail(f"edit failed: {e}", 4)
    finally:
        Path(tmp).unlink(missing_ok=True)

    if fetch(a.issue, a.repo).rstrip() != new.rstrip():
        fail("post-edit mismatch", 4)
    print(f"OK: #{a.issue} updated")


if __name__ == "__main__":
    main()
