# Development

How the project is built and checked: scope, environment, tests, quality
gates, CI, workflow, the Integration Quality Scale and releases.

## Contents

- [1. Scope](#1-scope)
- [2. Environment](#2-environment)
- [3. Tests](#3-tests)
- [4. Quality gates](#4-quality-gates)
- [5. CI workflows](#5-ci-workflows)
- [6. Local CI scripts](#6-local-ci-scripts)
- [7. Workflow](#7-workflow)
- [8. Integration Quality Scale](#8-integration-quality-scale)
- [9. Release procedure](#9-release-procedure)

## 1. Scope

**In scope:** cycle detection and quality, COP / SPF / degradation,
datasheets and model profiles, runtime and energy, heating-curve advice,
the ML layer, alerts, the setup and options flows, diagnostics, and the
native cards in `custom_components/daikin_cycle_ml/frontend/`.

**Out of scope:** a cloud API, writing setpoints from the integration
(the Efficiency card can call a climate entity the user links), cost
tracking, forecasting, exporting to other databases.

**Layout:**

| Path | Contents |
|---|---|
| `custom_components/daikin_cycle_ml/` | The integration: `coordinator.py`, platforms, `config_flow.py`, `services.py`, `diagnostics.py` |
| `.../engine/` | Pure logic without Home Assistant imports (detector, COP analysis, alerts, model catalog, physics) |
| `.../ml/` | Baseline, adaptive thresholds, clusters, features |
| `.../storage/` | SQLite schema, queries and migrations |
| `.../frontend/` | Native cards (plain web components) |
| `.../data/datasheets.json` | Bundled datasheets |
| `dashboard/cards/` | YAML cards with their docs and screenshots |
| `tests/` | pytest suite, card tests (Node, Chromium), diagnostics corpus |
| `tools/`, `scripts/` | Generators and local checks |

## 2. Environment

- Python 3.13 or 3.14, Home Assistant 2026.9 or newer (`hacs.json`).
- `scripts/bootstrap.sh` creates the environment from
  `requirements_test.txt` and installs the pre-push hook.
- Card tests need Node and Playwright with Chromium.
- In the dev container the CI mypy environment lives in
  `/opt/mypy-ci-venv` (Home Assistant pinned like CI).

## 3. Tests

```bash
pytest -q                       # full suite, 100 % coverage required
pytest --no-cov tests/<file>    # one file, no coverage
```

- **Coverage** must stay at 100.00 % (`fail_under = 100`). Never add
  `# pragma: no cover` to hide a gap.
- **A fix gets a replay test** of the reported data that fails on the old
  code.
- **Diagnostics corpus:** every diagnostics file users send is anonymised
  into `tests/fixtures/diagnostics/` with `tools/ingest_diagnostics.py` and
  replayed by `test_diagnostics_corpus.py` and
  `test_corpus_native_cards.py`.
- **Fixtures come from production code**, not typed by hand (card states:
  the generator in `test_427_cards_live_states.py`).
- **Native cards** are rendered under Node in English, Dutch and French
  and in Chromium; look at a screenshot before committing a card change.
- Long simulations: `--timeout=0`.

## 4. Quality gates

| Gate | Command |
|---|---|
| Tests | `pytest -q` (100 % coverage) |
| Ruff | `ruff check --no-fix --select E,F,W --ignore E501,E402,F401 custom_components tests` |
| Mypy | `mypy --strict custom_components/daikin_cycle_ml` |
| Pylint | 10.00 / 10 on the integration code |
| Markdown | `bash scripts/check-markdown.sh` (fenced code, no HTML in `docs/`) |

## 5. CI workflows

Eight workflows run on every pull request (`.github/workflows/`): `ruff`,
`mypy`, `pylint`, `coverage` (full suite), `hassfest`, `hacs`, `markdown`
and `model-compat` (the ESPAltherma attribute snapshot and catalog, plus a
weekly upstream drift check). CodeQL runs as well. CI is the final gate.

## 6. Local CI scripts

Two scripts, both run from the repository root:

| Script | What it runs | Time |
|---|---|---|
| `scripts/ci-fast.sh` | ruff (CI-parity) and mypy strict on the changed files, the markdown check | seconds |
| `scripts/ci-local.sh` | the four CI gates: full pytest with 100 % coverage, ruff, mypy strict, markdown | minutes |

`ci-fast.sh` checks files changed since `origin/main` (set `CI_FAST_BASE`
to compare with another branch), uncommitted and untracked `.py` files.
Run `ci-local.sh` before opening a PR; CI is the final gate.

### 6.1 Pre-push hook

Wired by `scripts/bootstrap.sh` (symlinked to `.git/hooks/pre-push`). On
every `git push` it runs `scripts/ci-fast.sh` within 120 s and blocks the
push when it fails. Pushes that only delete a branch are skipped.

### 6.2 Session rules R813-R816

- **R813**: `git push --no-verify` skips every local check, ruff and mypy
  included. If you use it, run `bash scripts/ci-fast.sh` yourself first.
- **R814**: `cmd | tail; echo $?` gives the exit code of `tail`, not of
  `cmd`. Never pipe `git rebase`, `git push` or `git merge`; use
  `cmd; RC=$?`.
- **R815**: check the dev container's name with `docker ps` at the start
  of a session; never take it from an old handoff.
- **R816**: after a failing gate, either commit the fix or revert; never
  leave written but uncommitted files behind.

## 7. Workflow

1. Branch from `origin/main`; one commit per deliverable, the subject
   names its issue (`fix: ... (#N)`).
2. Run `scripts/ci-fast.sh` while working and `scripts/ci-local.sh`
   before the pull request.
3. Pull request body: summary, changes, test plan, `Part of #N` for
   reported issues (they close when the release ships) or `Fixes #N`.
4. Merge with squash when CI is green.
5. `CHANGELOG.md` is append-only: add entries under `## [Unreleased]`,
   never restructure history.
6. User-facing changes update the docs in the same pull request.

## 8. Integration Quality Scale

Status: **Platinum** (declared in `manifest.json`, every rule done or
exempt in `custom_components/daikin_cycle_ml/quality_scale.yaml`).
Home Assistant awards IQS levels only to core integrations; for this
custom integration the level is self-declared and checked by
`tests/test_iqs_rules.py`, which reads `quality_scale.yaml` and checks the
claimed rules in the code (see 8.5).

### 8.1 Bronze

| Rule | Status | Notes |
|---|---|---|
| `config-flow` | ✅ | Setup wizard, options and reconfigure |
| `config-flow-test-coverage` | ✅ | All steps tested |
| `action-setup` | ✅ | Services registered in `async_setup` |
| `appropriate-polling` | ✅ | 30 s coordinator |
| `dependency-transparency` | ✅ | `aiosqlite` declared in `requirements` |
| `runtime-data` | ✅ | Typed `DaikinCycleMLConfigEntry` (`ConfigEntry[DaikinCycleMLCoordinator]`) |
| `entity-unique-id` | ✅ | Stable UIDs |
| `has-entity-name` | ✅ | All entities named by `translation_key` |
| `brands` | ✅ | `brand/icon.png` + `brand/logo.png` |
| `test-before-setup` | ✅ | Source checked in the config flow; missing at runtime: `source_stale` repair |
| `docs-*` | ✅ | Full doc set |

### 8.2 Silver

| Rule | Status | Notes |
|---|---|---|
| `parallel-updates` | ✅ | `PARALLEL_UPDATES = 0` (read-only platforms) |
| `integration-owner` | ✅ | `codeowners: ["@elRadix"]` |
| `test-coverage` | ✅ | 100.00% |
| `config-entry-unloading` | ✅ | Full unload path; returns `False` when a platform does not unload |
| `action-exceptions` | ✅ | `HomeAssistantError` / `ServiceValidationError` (invalid input) |
| `reauthentication-flow` | ⚪ | Exempt — no credentials |
| `entity-unavailable` / `log-when-unavailable` | ✅ | `source_stale` binary sensor + repair issue |

### 8.3 Gold

| Rule | Status | Notes |
|---|---|---|
| `devices` | ✅ | Single device per config entry |
| `diagnostics` | ✅ | Full diagnostics download, redacted |
| `repair-issues` | ✅ | 12 repair issues |
| `entity-translations` | ✅ | EN / NL / FR for all entities |
| `exception-translations` | ✅ | Every raised error has `translation_domain` + `translation_key`; `exceptions` in `strings.json` and EN / NL / FR |
| `icon-translations` | ✅ | `icons.json` next to `manifest.json`: every entity icon and the 14 service icons; no icon is set in code |
| `entity-disabled-by-default` | ✅ | `dhw_installed`, `boiler_operation_demand`, `boiler_dhw_demand` start disabled on new installs (no card or alert reads them) |
| `reconfiguration-flow` | ✅ | Basic + full reconfigure |
| `entity-device-class` | ✅ | `device_class` where one fits |
| `entity-category` | ✅ | Diagnostic entities marked (sensors and binary sensors) |
| `discovery`, `discovery-update-info` | ⚪ | Exempt — calculated source, nothing to discover |
| `dynamic-devices` | ⚪ | Exempt — one device per entry |
| `stale-devices` | ⚪ | Exempt — the device is removed with its entry |

### 8.4 Platinum

| Rule | Status | Notes |
|---|---|---|
| `strict-typing` | ✅ | `mypy --strict` in CI (HA pin), `py.typed` included |
| `async-dependency` | ✅ | The only library, `aiosqlite`, is async |
| `inject-websession` | ⚪ | Exempt — no HTTP calls |

### 8.5 Maintaining IQS status

Any PR that changes the entity surface, adds a service, or modifies the config flow must update `quality_scale.yaml`. `tests/test_iqs_rules.py` fails when a rule claimed as done is not met (an icon set in code, an entity or service without an icon, a raised error without translation, an undeclared library, a missing exception text).

Checklist for IQS-impacting changes:

- [ ] New entity → add to `quality_scale.yaml` if it affects a rule
- [ ] New service → update `services.yaml` and translations
- [ ] New repair → add to `repairs.py` and `strings.json`
- [ ] New config option → update `strings.json` and translations
- [ ] New diagnostic field → verify `TO_REDACT` still covers sensitive fields

## 9. Release procedure

A release pull request contains only the version bump, in one commit:

1. `const.py` `VERSION`, `manifest.json` `version`, `pyproject.toml`
   `version` (all equal; `tests/test_50d_version_contract.py` checks).
2. README badges: version and test count.
3. `python tools/sync_issue_template.py` (bug-report version list).
4. `CHANGELOG.md`: `## [X.Y.Z] - YYYY-MM-DD` under `## [Unreleased]`.

After the merge: tag `vX.Y.Z` on the merge commit, publish the GitHub
release (what's new for users, after-updating steps including cards to
re-paste, card gallery, thanks to reporters by handle, technical notes),
then comment on and close the issues it ships.
