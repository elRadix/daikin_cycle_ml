#!/usr/bin/env bash
# Daikin Cycle ML — local CI parity gate.
# Runs the same 3 checks as CI: pytest (100% cov), ruff, mypy strict.
# Exit 0 on all-pass, 1 on any fail.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

MYPY_VENV=/opt/mypy-ci-venv
FAIL=0
LOG=/tmp/ci-local-pytest.log

echo "[ci-local] 1/4 pytest (full suite, 100% cov)"
pytest -q --no-header > "$LOG" 2>&1
PYTEST_RC=$?
grep -E '[0-9]+ (passed|failed|skipped)' "$LOG" | tail -1 || true
if [[ $PYTEST_RC -ne 0 ]]; then
    echo "[ci-local] FAIL pytest exit=$PYTEST_RC"
    FAIL=1
fi
if ! grep -q 'Required test coverage of 100% reached' "$LOG"; then
    echo "[ci-local] FAIL coverage 100% gate not met"
    FAIL=1
fi

echo "[ci-local] 2/4 ruff (CI-parity)"
if ! ruff check --no-fix --select E,F,W --ignore E501,E402,F401 \
    custom_components/daikin_cycle_ml tests; then
    echo "[ci-local] FAIL ruff"
    FAIL=1
fi

echo "[ci-local] 3/4 mypy strict"
if [[ ! -x "$MYPY_VENV/bin/mypy" ]]; then
    echo "[ci-local] FAIL $MYPY_VENV missing — run scripts/bootstrap.sh"
    FAIL=1
elif ! "$MYPY_VENV/bin/mypy" --strict --python-version 3.14 \
    custom_components/daikin_cycle_ml; then
    echo "[ci-local] FAIL mypy"
    FAIL=1
fi

echo "[ci-local] 4/4 markdown"
if ! bash scripts/check-markdown.sh; then
    echo "[ci-local] FAIL markdown"
    FAIL=1
fi

echo
if [[ $FAIL -eq 0 ]]; then
    echo "[ci-local] PASS"
    exit 0
else
    echo "[ci-local] FAIL"
    exit 1
fi
