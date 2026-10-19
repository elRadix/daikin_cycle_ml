#!/usr/bin/env bash
# Daikin Cycle ML — dev environment bootstrap.
# Idempotent. Run inside dev container as root.
# Rebuilds /opt/mypy-ci-venv pinned to HA 2026.9.3 and installs pre-push hook.
set -euo pipefail

MYPY_VENV=/opt/mypy-ci-venv
HA_PIN="2026.9.3"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[bootstrap] repo root: $REPO_ROOT"

need_venv=0
if [[ ! -x "$MYPY_VENV/bin/python" ]]; then
  need_venv=1
elif ! "$MYPY_VENV/bin/python" -c "from homeassistant.const import __version__; import sys; sys.exit(0 if __version__ == '$HA_PIN' else 1)" 2>/dev/null; then
  need_venv=1
fi

if [[ $need_venv -eq 1 ]]; then
  echo "[bootstrap] rebuilding $MYPY_VENV (HA $HA_PIN)"
  rm -rf "$MYPY_VENV"
  python3 -m venv "$MYPY_VENV"
  "$MYPY_VENV/bin/pip" install --quiet --upgrade pip
  "$MYPY_VENV/bin/pip" install --quiet mypy "homeassistant==$HA_PIN"
  echo "[bootstrap] venv ready: $("$MYPY_VENV/bin/mypy" --version)"
else
  echo "[bootstrap] venv OK: $("$MYPY_VENV/bin/mypy" --version), HA $HA_PIN"
fi

HOOK="$REPO_ROOT/.git/hooks/pre-push"
if [[ ! -L "$HOOK" ]] || [[ "$(readlink -f "$HOOK")" != "$REPO_ROOT/scripts/pre-push" ]]; then
  echo "[bootstrap] wiring pre-push hook"
  ln -sf "../../scripts/pre-push" "$HOOK"
  echo "[bootstrap] hook: $HOOK -> $(readlink "$HOOK")"
else
  echo "[bootstrap] pre-push hook already wired"
fi

echo "[bootstrap] DONE"
