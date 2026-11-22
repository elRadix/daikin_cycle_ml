#!/usr/bin/env bash
# Daikin Cycle ML: fast local gate (#500 D1), for the pre-push hook.
# ruff (CI-parity) and mypy strict on the changed files, plus the markdown
# check; under a minute. The full suite (pytest, 100 % coverage) runs in CI
# and in scripts/ci-local.sh.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

BASE="${CI_FAST_BASE:-origin/main}"
FAIL=0
mapfile -t PY < <(git diff --name-only --diff-filter=ACMR "$BASE"...HEAD -- '*.py' 2>/dev/null
                  git diff --name-only --diff-filter=ACMR -- '*.py'
                  git ls-files --others --exclude-standard -- '*.py')
mapfile -t PY < <(printf '%s\n' "${PY[@]}" | sort -u | grep -v '^$' || true)
mapfile -t COMP < <(printf '%s\n' "${PY[@]}" | grep '^custom_components/' || true)

if [[ ${#PY[@]} -gt 0 ]]; then
    echo "[ci-fast] ruff on ${#PY[@]} changed file(s)"
    ruff check --no-fix --select E,F,W --ignore E501,E402,F401 "${PY[@]}" || { echo "[ci-fast] FAIL ruff"; FAIL=1; }
else
    echo "[ci-fast] no .py changes: ruff skipped"
fi

MYPY="${MYPY:-mypy}"
[[ -x /opt/mypy-ci-venv/bin/mypy ]] && MYPY=/opt/mypy-ci-venv/bin/mypy
if [[ ${#COMP[@]} -gt 0 ]]; then
    echo "[ci-fast] mypy strict on ${#COMP[@]} changed integration file(s)"
    "$MYPY" --strict "${COMP[@]}" || { echo "[ci-fast] FAIL mypy"; FAIL=1; }
fi

echo "[ci-fast] markdown"
bash scripts/check-markdown.sh || { echo "[ci-fast] FAIL markdown"; FAIL=1; }

if [[ $FAIL -eq 0 ]]; then echo "[ci-fast] PASS"; else echo "[ci-fast] FAIL"; fi
exit $FAIL
