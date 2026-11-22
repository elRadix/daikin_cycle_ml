"""Keep the version dropdown of the bug report form current.

The options are rebuilt from the integration's own version
(manifest.json, marked "latest") and the releases before it in
CHANGELOG.md, so the form never offers a version that is long gone as
"latest" (#487 arrived with "1.22.1 (latest)" while 1.29.1 was out).

    python tools/sync_issue_template.py          # rewrite the options
    python tools/sync_issue_template.py --check  # exit 1 when out of date

tests/test_issue_template.py runs the check, so a release PR that bumps
the version fails until this tool has been run.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml"
MANIFEST = ROOT / "custom_components/daikin_cycle_ml/manifest.json"
CHANGELOG = ROOT / "CHANGELOG.md"
BEGIN, END = "        # VERSIONS:BEGIN (tools/sync_issue_template.py)\n", "        # VERSIONS:END\n"
PREVIOUS = 5      # releases listed after the latest
OLDER = "Older (type the exact version under Anything else)"


def versions() -> list[str]:
    """The current version first, then the releases before it, newest first."""
    current = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    released = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", CHANGELOG.read_text(encoding="utf-8"), re.M)
    older = [v for v in released if v != current]
    return [current, *older[:PREVIOUS]]


def options_block() -> str:
    vs = versions()
    lines = [f'        - "{vs[0]} (latest)"\n', *(f'        - "{v}"\n' for v in vs[1:]), f'        - "{OLDER}"\n']
    return BEGIN + "".join(lines) + END


def render(text: str) -> str:
    start, stop = text.index(BEGIN), text.index(END) + len(END)
    return text[:start] + options_block() + text[stop:]


def main(argv: list[str]) -> int:
    text = FORM.read_text(encoding="utf-8")
    new = render(text)
    if "--check" in argv:
        if new != text:
            print("bug_report.yml version list is out of date: run tools/sync_issue_template.py")
            return 1
        return 0
    FORM.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
