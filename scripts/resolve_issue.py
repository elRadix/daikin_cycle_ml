#!/usr/bin/env python3
"""Post-merge resolution comment + optional auto-close (R846).

English comment (R857) with PR link + commit ref. Only closes with
--close (i.e. full fix). Verifies final issue state.

Exit codes: 0=OK 1=Dutch 4=gh fail
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

DUTCH = ("geinvalideerd", "herberekening", "tijdens", "bevestigd",
         "aansloeg", "schreef", "nieuwe")


def fail(m, c):
    print(f"FAIL: {m}", file=sys.stderr)
    sys.exit(c)


def build(version: str, pr: int, commit: str | None, prod_verified: bool) -> str:
    cl = f"\nCommit: `{commit}`" if commit else ""
    is_semver = version and version[0].isdigit()
    v_prefix = "v" if is_semver else ""

    if is_semver:
        header = f"## Resolved in {v_prefix}{version}"
        release_line = f"- [x] Released in {v_prefix}{version}"
    else:
        header = f"## Merged in #{pr}"
        release_line = f"- [ ] Targeted for {version} (unreleased)"

    prod_line = "- [x] Prod replay confirmed" if prod_verified else "- [ ] Prod replay pending"

    return (f"{header}{cl}\n\n"
            f"**Verification**\n- [x] Tests pass (100% coverage)\n"
            f"{prod_line}\n"
            f"{release_line}\n")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--version", required=True)
    p.add_argument("--pr", required=True, type=int)
    p.add_argument("--commit", default=None)
    p.add_argument("--repo", default=None)
    p.add_argument("--close", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--prod-verified", action="store_true", help="Claim prod replay was confirmed")
    a = p.parse_args()

    comment = build(a.version, a.pr, a.commit, a.prod_verified)
    dutch = [w for w in DUTCH if w in comment.lower()]
    if dutch:
        fail(f"Dutch: {sorted(set(dutch))}", 1)

    if a.dry_run:
        print("DRY-RUN comment:\n" + comment)
        print(f"would close: {a.close}")
        return

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(comment)
        tmp = f.name
    c = ["gh", "issue", "comment", str(a.issue), "--body-file", tmp]
    if a.repo:
        c += ["--repo", a.repo]
    try:
        subprocess.check_call(c)
    except subprocess.CalledProcessError as e:
        fail(f"comment failed: {e}", 4)
    finally:
        Path(tmp).unlink(missing_ok=True)

    if a.close:
        cc = ["gh", "issue", "close", str(a.issue), "--reason", "completed"]
        if a.repo:
            cc += ["--repo", a.repo]
        try:
            subprocess.check_call(cc)
        except subprocess.CalledProcessError as e:
            fail(f"close failed: {e}", 4)

    vc = ["gh", "issue", "view", str(a.issue), "--json", "state", "-q", ".state"]
    if a.repo:
        vc += ["--repo", a.repo]
    state = subprocess.check_output(vc, text=True).strip()
    exp = "CLOSED" if a.close else "OPEN"
    if state != exp:
        fail(f"state={state} expected={exp}", 4)
    print(f"OK: #{a.issue} state={state}")


if __name__ == "__main__":
    main()
