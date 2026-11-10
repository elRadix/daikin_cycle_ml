"""#322: dashboard cards must not reference `hass.` from Jinja.

HA 2026.11.1 removed `hass` from the template render context in some
cases, so Jinja blocks that read `hass.language` throw
``UndefinedError: 'hass' is undefined``. JavaScript blocks (card_mod
styles) are safe because they run in the browser and have an explicit
``typeof hass !== 'undefined'`` guard.
"""

from __future__ import annotations

import glob
from pathlib import Path


def _is_js_line(line: str) -> bool:
    stripped = line.strip()
    return (
        "typeof hass" in line
        or stripped.startswith("var ")
        or "|| hass." in line
        or stripped.startswith("? String(hass.")
    )


def test_no_jinja_hass_reference_in_dashboard_cards():
    """#322: no Jinja `hass.` in dashboard/*/*.yaml (JS allowed)."""
    hits = []
    for f in glob.glob("dashboard/cards/*/*.yaml"):
        for i, line in enumerate(Path(f).read_text().splitlines(), 1):
            if "hass." not in line:
                continue
            if _is_js_line(line):
                continue
            hits.append(f"{f}:{i}: {line.strip()[:120]}")
    assert not hits, (
        "Jinja `hass.*` references in dashboard cards "
        "(use state_attr fallback):\n  " + "\n  ".join(hits)
    )


def test_daily_summary_tabbed_uses_configured_language():
    """#322: template must fall back to configured_language, not hass."""
    src = Path(
        "dashboard/cards/daily-summary-tabbed/daily-summary-tabbed.yaml"
    ).read_text()
    assert (
        "{% set l = state_attr(ns.state, 'configured_language') or 'en' -%}"
        in src
    ), "daily-summary-tabbed template not updated"
