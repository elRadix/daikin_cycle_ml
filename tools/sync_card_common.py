#!/usr/bin/env python3
"""Copy tools/card_common.js into every dashboard card (#427).

Every card carries the same language / theme / header block between
``/* DCM-COMMON-BEGIN`` and ``/* DCM-COMMON-END */``; the cards stay
self-contained (users paste one YAML file). Edit tools/card_common.js and
run::

    python3 tools/sync_card_common.py          # update the cards
    python3 tools/sync_card_common.py --check  # exit 1 when a card drifted
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMON = ROOT / "tools" / "card_common.js"
CARDS = sorted((ROOT / "dashboard" / "cards").glob("*/*.yaml"))
BLOCK = re.compile(r"^([ \t]*)/\* DCM-COMMON-BEGIN.*?/\* DCM-COMMON-END \*/[ \t]*$", re.S | re.M)


def common_block(indent: str) -> str:
    lines = COMMON.read_text(encoding="utf-8").rstrip("\n").split("\n")
    return "\n".join((indent + ln) if ln.strip() else "" for ln in lines)


def sync_text(text: str) -> tuple[str, int]:
    """Replace every common block in ``text``; returns (new text, count)."""
    newline = "\r\n" if "\r\n" in text else "\n"
    src = text.replace("\r\n", "\n")
    out, n = BLOCK.subn(lambda m: common_block(m.group(1)), src)
    return out.replace("\n", newline), n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    drift = []
    for card in CARDS:
        text = card.read_bytes().decode("utf-8")
        new, n = sync_text(text)
        if n == 0:
            drift.append(f"{card.relative_to(ROOT)}: no DCM-COMMON block")
            continue
        if new != text:
            if args.check:
                drift.append(f"{card.relative_to(ROOT)}: common block differs")
            else:
                card.write_bytes(new.encode("utf-8"))
                print(f"updated {card.relative_to(ROOT)} ({n} blocks)")
    for line in drift:
        print(line)
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
