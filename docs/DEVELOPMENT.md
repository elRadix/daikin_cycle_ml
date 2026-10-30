# Development

Contribution guide, testing, CI gates, IQS status, and scope boundaries for Daikin Cycle ML.

- **Covers:** local dev setup, test suite, CI workflows, code quality gates, IQS compliance, scope boundaries, release procedure
- **For:** contributors, forks, maintainers
- **Version:** v1.14.0

Cross-references: [CONFIGURATION.md](CONFIGURATION.md) (options), [ENTITIES.md](ENTITIES.md) (entity surface), [DATABASE.md](DATABASE.md) (schema), [ML.md](ML.md) (ML internals), [ALERTS.md](ALERTS.md) (alert pipeline).

---

## Contents

- [1. Scope boundaries](#1-scope-boundaries)
- [2. Dev environment](#2-dev-environment)
- [3. Test suite](#3-test-suite)
- [4. Code quality gates](#4-code-quality-gates)
- [5. CI workflows](#5-ci-workflows)
- [6. Local CI script](#6-local-ci-script)
- [7. Standard workflow](#7-standard-workflow)
- [8. Integration Quality Scale](#8-integration-quality-scale)
- [9. Release procedure](#9-release-procedure)
- [10. Ruleset and branch protection](#10-ruleset-and-branch-protection)

---

## 1. Scope boundaries

### 1.1 In scope

The integration covers:

- **Cycle detection** — compressor start/stop transitions from a single ESPAltherma source sensor
- **Quality scoring** — per-cycle 0-100 score from runtime, dT, off-time, BUH, defrost
- **Pendulum detection** — 8 patterns across heating / cooling / DHW, hourly and daily
- **COP analysis** — per-mode COP, SPF / SCOP, weather-normalized degradation
- **Daikin datasheets** — 15 bundled models, user-importable specs, normalized COP comparison
- **Runtime & energy accounting** — daily accumulators that survive HA restart
- **LWT advice** — heat-curve advice with comfort guardrails
- **ML** — per-mode baseline, adaptive thresholds, k-means clustering, anomaly detection
- **Alerts** — 19 alert types with dedup, quiet hours, per-alert toggles, bilingual templates
- **Setup wizard + OptionsFlow** — full UI configuration without YAML
- **Diagnostics + repairs** — HA-native observability

### 1.2 Out of scope

The integration explicitly does **not** cover:

- **Daikin cloud API** — never. The integration is 100% local. No calls to `daikin.eu` or `daikin.com`.
- **Setpoint writes** — the integration is read-only toward the heat pump. All advice requires user action (or user automation).
- **Cost tracking / € calculations** — planned for a future release but not in scope for v1.9.
- **Verbruiksprognose** — no forecasting of future consumption.
- **HA Energy dashboard integration** — the integration exposes energy sensors compatible with the dashboard, but does not populate it directly.
- **Brine circuits** — EPRA12 is air-water, not brine. Brine monitoring is out of scope.
- **Web UI / cycle explorer** — no additional dashboards beyond HA Lovelace.
- **InfluxDB export** — use HA's built-in recorder or the InfluxDB integration.
- **Webhook push** — use HA notify targets.
- **HACS publication (default store)** — the integration is HACS-compatible via custom repository, not yet submitted to HACS default store.
- **Supervised ML** — no label-based training. Labels collected by `label_cycle` are not used for training (yet).

### 1.3 File boundaries

| Directory | In scope for changes |
|---|---|
| `custom_components/daikin_cycle_ml/` | ✅ Yes |
| `tests/` | ✅ Yes |
| `.github/workflows/` | ✅ Yes (new workflows need maintainer approval) |
| `translations/` | ✅ Yes (must be parity-checked) |
| `docs/` | ✅ Yes |
| `scripts/` | ✅ Yes |
| `.pylintrc`, `pyproject.toml` | 🟡 Requires maintainer review |
| `dashboard/` | ✅ Yes (Lovelace cards) |
| `AGENTS.md` | 🟡 Rule changes require discussion |
| `README.md` | ✅ Yes (landing page only after v1.9 split) |

**Anything outside the repo** (HA supervisor config, Proxmox settings, network config) is out of scope for any PR.

### 1.4 Design principles

Every PR should respect these:

1. **Local-only** — no cloud dependency, ever
2. **Read-only** — no writes to the heat pump
3. **Fail-safe** — a component failure should never block the coordinator
4. **Deterministic** — same input produces same output (ML is exception, by design)
5. **100% coverage** — no new code without tests
6. **Bilingual** — every user-facing string has EN + NL
7. **Backward-compatible** — migrations for schema changes, deprecations for entity renames
8. **Documented** — new features update docs/ in the same PR

---

## 2. Dev environment

### 2.1 Requirements

| Tool | Version | Notes |
|---|---|---|
| Python | 3.14 | Matches HA 2026.9 baseline |
| Home Assistant Core | 2026.9+ | For dev testing |
| pytest | 9.0.3 | Pinned |
| pytest-cov | 7.1.0 | Pinned |
| pytest-asyncio | 1.4.0 | Pinned |
| pytest-homeassistant-custom-component | 0.13.373 | Pinned |
| pytest-timeout | 2.4.0 | Pinned |
| hypothesis | 6.170.1 | For property-based tests |
| syrupy | 6.1.1 | Snapshot tests |
| ruff | 0.17.1 | Pinned |
| mypy | 2.4.0 | Pinned |

Full list in `pyproject.toml`.

### 2.2 Dev container (recommended)

The project has a dev container (`daikin_cycle_dev`) based on `python:3.14`. Mount:

- Host: `/homeassistant/daikin_cycle_ml_dev/`
- Container: `/workspace/daikin_cycle_ml/`

Inside the container:

```bash
cd /workspace/daikin_cycle_ml
scripts/bootstrap.sh
```

`bootstrap.sh` does:
1. Rebuilds `/opt/mypy-ci-venv` pinned to `homeassistant==2026.9.3` (idempotent)
2. Symlinks `scripts/pre-push` to `.git/hooks/pre-push`
3. Verifies both are executable

After bootstrap, all quality gates run automatically before every push.

### 2.3 Manual environment

If you don't use the dev container:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r requirements-dev.txt
```

Then run pytest from the repo root. Ensure `PYTHONPATH` includes the repo root when running from outside the container.

---

## 3. Test suite

### 3.1 Structure

```
tests/
├── conftest.py                    # Shared fixtures
├── test_*.py                       # ~130 test files
└── snapshots/                     # Syrupy snapshots
```

**Total:** ~6724 tests, 4 skipped, 100.00% coverage.

### 3.2 Running tests

**Full suite:**

```bash
pytest -q
```

Takes ~2 minutes on a 2-core container. Requires 100.00% coverage.

**Single file:**

```bash
pytest -q tests/test_v190_p3_kmeans_stale.py
```

**Single test:**

```bash
pytest -q tests/test_v190_p3_kmeans_stale.py::test_basic_flow
```

**Without coverage** (faster, useful during dev):

```bash
pytest -q --no-cov tests/your_file.py
```

**With verbose output:**

```bash
pytest -v tests/your_file.py
```

**With a specific asyncio mode:**

The suite uses `asyncio_mode = "auto"`. Async tests are auto-detected, no marker needed.

### 3.3 Fixtures

Key fixtures in `conftest.py`:

| Fixture | Purpose |
|---|---|
| `hass` | HA test instance (from pytest-homeassistant-custom-component) |
| `coordinator` | Fully initialized coordinator with a mock source sensor |
| `mock_source` | Mock ESPAltherma sensor with all required attributes |
| `snap` | A `DataSnapshot` with realistic values |
| `db` | Initialized SQLite DB (in-memory) |
| `entry` | A configured `ConfigEntry` |

Custom fixtures per test file are common. Copy from a nearby test rather than reinventing.

### 3.4 Test patterns

**Behavior tests, not implementation tests** (per R343):

```python
# GOOD: tests behaviour
def test_short_run_alert_fires(coordinator, snap):
    snap.duration_s = 10 * 60  # 10 min
    snap.short_run_threshold_min = 20
    states = coordinator._alert_binary_states(snap)
    assert states["short_run"] is True

# BAD: tests implementation detail
def test_short_run_alert(coordinator, snap):
    assert hasattr(coordinator, "_check_short_run")
```

**One assertion per concept** — a test can have multiple asserts if they verify one concept.

**No time.sleep()** in tests. Use `hass.async_fire()` + `await hass.async_block_till_done()` for time-based tests.

**No network calls** — mock all outbound HTTP.

**Use `asyncio.sleep(0)` sparingly** — prefer `hass.async_block_till_done()`.

### 3.5 Flaky test handling

Known flaky tests (should fix, not retry):

- `test_29_scenarios.py::test_scenario_cycles_rollup_math` — order-dependent
- `test_c5_sensors.py::test_duty_cycle_computes_pct` — timing-sensitive
- `test_cop_sensors.py::test_refresh_cop_today_valid` — order-dependent

If you see a new flaky test, **do not add `@pytest.mark.skip`**. Debug the underlying issue or file a bug.

---

## 4. Code quality gates

Every commit must pass all four gates. Any one failure blocks the push.

### 4.1 Gate 1 — pytest

**What:** full test suite + 100.00% coverage

**Command:**
```bash
pytest -q
```

**Must produce:**
```
Required test coverage of 100% reached. Total coverage: 100.00%
```

**If it fails:**
- Missing coverage → add tests for the new code path
- Test failure → fix the code (never fix the test to pass)
- Order-dependent failure → file as flaky test bug, don't skip

### 4.2 Gate 2 — ruff (CI-parity)

**What:** linting with the same config as CI

**Command:**
```bash
ruff check --no-fix --select E,F,W --ignore E501,E402,F401 \
    custom_components/daikin_cycle_ml tests
```

**Must produce:**
```
All checks passed!
```

**Key rules enforced:**
- E7xx: no semicolons, no bare except
- F: no unused imports, undefined names, f-string issues
- W: no trailing whitespace, no deprecated
- Ignored: E501 (line length, handled by 100-char config), E402 (module-level imports after code, needed for HA), F401 (unused imports, needed for HA entity platform registration)

**If it fails:**
```bash
ruff check --select E,F,W --ignore E501,E402,F401 \
    custom_components/daikin_cycle_ml tests
```
Auto-fix available for most issues. Review the diff before committing.

### 4.3 Gate 3 — mypy strict

**What:** static type checking

**Command:**
```bash
/opt/mypy-ci-venv/bin/mypy --strict --python-version 3.14 \
    custom_components/daikin_cycle_ml
```

**Must produce:**
```
Success: no issues found in 35 source files
```

**If it fails:**
- `Missing return type annotation` → add `-> ReturnType`
- `Need type annotation for variable` → add explicit type
- `has no attribute` → check the actual type; use `getattr` with default if the attribute is optional
- `Argument 1 has incompatible type` → check the signature at the call site

**Do not use `# type: ignore`.** If mypy complains, the type is wrong or the code needs restructuring. Fix the root cause.

**Exception:** `# type: ignore[no-untyped-call]` for third-party libs without type stubs. This should be rare.

### 4.4 Gate 4 — markdown guard

**What:** markdown formatting (files in `docs/`, `README.md`, `AGENTS.md`, `CHANGELOG.md`, `dashboard/*/README.md`)

**Command:**
```bash
bash scripts/check-markdown.sh
```

**Must produce:**
```
[md] PASS
```

**Catches:**
- Tabs (use spaces)
- Trailing whitespace (1 or 3+; 2 = hard break, allowed)
- CRLF line endings
- Missing final newline
- 3+ consecutive blank lines
- Unclosed code fences
- Heading-level jumps
- Over-indented bullets/lists
- HTML tags outside code fences
- Raw RST markers
- Non-ASCII whitespace (NBSP, zero-width)
- Mixed fence styles (backtick + tilde)
- Unbalanced bold markers
- Mixed bullet indent

**If it fails:**
```bash
bash scripts/check-markdown.sh
```
Each FAIL shows file:line. Fix with `sed` or editor. Re-run to confirm.

---

## 5. CI workflows

Eight GitHub Actions workflows run on every push and PR to `main`. **All must pass before merge.**

### 5.1 Overview

| Workflow | What it checks | Typical duration | File |
|---|---|---|---|
| **Ruff** | Lint (same as gate 2) | ~5 s | `.github/workflows/ruff.yml` |
| **Pylint** | `--fail-under=8.0` on integration code | ~20 s | `.github/workflows/pylint.yml` |
| **Hassfest** | Official HA integration validator | ~25 s | `.github/workflows/hassfest.yml` |
| **HACS Validation** | `hacs/action@main`, category `integration` | ~40 s | `.github/workflows/hacs.yml` |
| **Mypy** | `mypy --strict`, Python 3.14, HA 2026.9 stubs | ~65 s | `.github/workflows/mypy.yml` |
| **Coverage** | Full suite + `--cov-fail-under=100` | ~135 s | `.github/workflows/coverage.yml` |
| **CodeQL** | Security scanning | ~50 s | auto (dynamic) |
| **Markdown** | Guard for `.md` files | ~5 s | `.github/workflows/markdown.yml` |

### 5.2 What runs when

Ruff, Pylint, Hassfest, HACS, Mypy, CodeQL run on every push and PR.

Coverage runs on push to `main` and PRs (not on feature branch pushes only).

Markdown runs only when a `.md` file or the guard script changes (path filter).

### 5.3 CI-parity rules

**Never run these locally with different flags than CI uses:**

| Task | CI command | Local parity |
|---|---|---|
| ruff | `--no-fix --select E,F,W --ignore E501,E402,F401` | Use exact same flags |
| mypy | `/opt/mypy-ci-venv/bin/mypy --strict --python-version 3.14` | Use `/opt/mypy-ci-venv` (HA 2026.9.3 pinned) |
| coverage | `--cov-fail-under=100` | Same |

**Why:** local ruff run with different flags can pass while CI fails. Local mypy with a different HA version can produce 46 pre-existing errors (dev container mypy without pin has this issue — this is why `/opt/mypy-ci-venv` exists).

### 5.4 CI polling behavior

When you push and then check CI:

1. **Run immediately**: `gh run list --branch main --limit 3`
2. **Check specific commit**: `gh run list --commit <sha> --limit 20` (needs full 40-char SHA in gh 2.97+)
3. **Check PR checks**: `gh pr checks <num>`

**If CI seems stuck > 10 min:**
- Check the run status page directly via the URL from `gh run list`
- If hung, `gh run cancel <run-id>` then `gh run rerun <run-id>`
- Never amend a commit to "kick" CI — that resets history for no reason

**If CI fails:**
- Reproduce locally with the exact CI command
- Fix the code, don't change the CI config
- Push the fix as a new commit (never force-push to main)

---

## 6. Local CI script

`scripts/ci-local.sh` runs all four gates in sequence:

```bash
bash scripts/ci-local.sh
```

Output:

```
[ci-local] 1/4 pytest (full suite, 100% cov)
6724 passed, 4 skipped in 90s
[ci-local] 2/4 ruff (CI-parity)
All checks passed!
[ci-local] 3/4 mypy strict
Success: no issues found in 35 source files
[ci-local] 4/4 markdown
[md] PASS

[ci-local] PASS
```

This is what the pre-push hook runs. If `ci-local.sh` passes, push will succeed.

### 6.1 Pre-push hook

Wired by `scripts/bootstrap.sh`. Symlinked to `.git/hooks/pre-push`.

**What it does on every `git push`:**

1. Runs `scripts/ci-local.sh`
2. If exit 0: pushes normally
3. If exit 1: **blocks the push**, shows the failure output

**Bypass:** `git push --no-verify`

**Never use `--no-verify`** unless you are pushing a docs-only branch with a pre-approved CI failure (rare). Even then, mention it in the PR description.

### 6.2 Why the pre-push hook

Local `ci-local.sh` catches ~90% of CI failures before the push. Benefits:

- Saves CI minutes
- Saves the 8-minute CI round-trip
- Forces you to see failures as they happen, not "CI failed, let me fix"

**Trade-off:** every push takes ~2 minutes. This is intentional — the cost is worth it.

---

## 7. Standard workflow

### 7.1 Session start

```bash
cd /workspace/daikin_cycle_ml
git checkout main
git pull --ff-only
git status                           # verify clean
scripts/bootstrap.sh                 # verify env
pytest -q --no-cov --collect-only | tail -1  # verify test suite loads
```

If bootstrap or test collection fails, environment is broken — fix before making changes.

### 7.2 Feature branch

```bash
git checkout -b feat/your-change
```

Branch naming:
- `feat/<short-name>` — new feature
- `fix/<short-name>` — bug fix
- `chore/<short-name>` — tooling, deps
- `docs/<short-name>` — documentation
- `refactor/<short-name>` — restructuring without behaviour change

### 7.3 Implementation

1. **Recon first** — `grep -r "symbol" .` over the whole repo before changing anything
2. **Small commits** — one logical change per commit
3. **Commit message** — imperative subject, ≤72 chars, no period, `(#66)` suffix if part of tracker
4. **Update tests as you go** — do not accumulate test debt
5. **Update docs in the same PR** — features without docs are incomplete

### 7.4 Commit discipline

**Commit format:**

```
<type>(<scope>): <subject> (#66)

<body explaining what and why>
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`

Scope (optional): `alerts`, `ml`, `sensor`, `db`, `config`, `ci`, `docs`

**Examples:**

```
feat(alerts): v1.9.0 I6 — energy_daily_anomaly (#66) (#79)
fix(ml): cluster assignment uses nearest_centroid on empty state (#66)
chore(ci): v1.9.0 K — QA-pipeline (#66)
docs: split README into docs/ (#66)
```

**Do not** put more than 5 files in one commit unless they are thematically related.

**Do not** amend pushed commits (R91).

### 7.5 Push

```bash
git push -u origin feat/your-change
```

Pre-push hook runs `scripts/ci-local.sh`. Takes ~2 min. If it fails, the push is blocked.

**If the hook fails:**

1. Read the failure output
2. Fix the code (not the test, not the CI config)
3. Commit the fix
4. Push again

**Do not use `--no-verify`** to bypass. If you do, CI will fail on the same gates.

### 7.6 PR creation

```bash
gh pr create --base main --head feat/your-change \
    --title "feat: your change (#66)" \
    --body-file /tmp/pr_body.md
```

**PR body template:**

```markdown
Refs #66

## Summary

One paragraph explaining what changed and why.

## Changes

- Bullet points of specific changes
- Each item should be testable/verifiable

## Testing

- Full suite: 6724 passed, 4 skipped, 100.00%
- Manual verification: describe what you checked in HA UI
- Any new tests added

## Documentation

- Updated docs/XXX.md with new section Y
- README badges unaffected (or updated)

## Breaking changes

- None (or description of what breaks and migration path)
```

**Rules:**

- PR body line 1 = `Refs #<tracker>` for tracker-linked PRs
- No backticks in `--body-file` heredocs (use Python writer if needed)
- Verify `headRefOid` matches local HEAD after `gh pr create`

### 7.7 CI wait

```bash
gh pr checks <num>
```

Wait for all workflows to pass. If a workflow fails, see §5.4.

Typical CI round-trip: **8-10 minutes** (Coverage is the slowest at ~135 s).

### 7.8 Merge

```bash
gh pr merge <num> --squash --delete-branch
```

**Rules:**

- Always `--squash` (not merge commit, not rebase)
- Always `--delete-branch` (cleanup remote)
- **Never** `--admin` — respect the ruleset

If merge is blocked by ruleset, the CI gates are not all green. Fix and re-push.

### 7.9 Post-merge

```bash
git checkout main
git pull --ff-only
```

Update tracker (if applicable): tick the checkbox, comment with merge SHA.

---

## 8. Integration Quality Scale

Status: **Bronze + Silver + Gold**.

Partial Platinum (strict typing passes, py.typed included).

Full status in `quality_scale.yaml` at repo root.

### 8.1 Bronze

| Rule | Status | Notes |
|---|---|---|
| `config-flow` | ✅ | 8-step wizard |
| `config-flow-test-coverage` | ✅ | All steps tested |
| `test-coverage` | ✅ | 100.00% |
| `action-setup` | ✅ | All services validate |
| `runtime-data` | ✅ | Coordinator-based |
| `entity-unique-id` | ✅ | Stable UIDs |
| `has-entity-name` | ✅ | All entities named |
| `brands` | ✅ | logo + icon in HACS metadata |
| `docs-*` (10 rules) | ✅ | Full doc set |

### 8.2 Silver

| Rule | Status | Notes |
|---|---|---|
| `parallel-updates` | ✅ | `PARALLEL_UPDATES = 0` (single coordinator) |
| `integration-owner` | ✅ | `codeowners: ["elRadix"]` |
| `test-coverage` | ✅ | 100.00% |
| `config-entry-unloading` | ✅ | Full unload path |
| `action-exceptions` | ✅ | All service calls raise `HomeAssistantError` on failure |
| `reauthentication-flow` | ⚪ | Exempt — local source, no auth |
| `entity-unavailable` | ✅ | Binary sensor when source is stale |

### 8.3 Gold

| Rule | Status | Notes |
|---|---|---|
| `devices` | ✅ | Single device per config entry |
| `diagnostics` | ✅ | Full diagnostics download |
| `repair-issues` | ✅ | 8 repair issues |
| `entity-translations` | ✅ | EN + NL for all entities |
| `reconfiguration-flow` | ✅ | Basic + full reconfigure |
| `entity-device-class` | ✅ | All entities with `device_class` set appropriately |
| `entity-category` | ✅ | Diagnostic entities marked |
| `discovery` | ⚪ | Exempt — calculated source |
| `dynamic-devices` | ⚪ | Exempt — fixed device |
| `stale-devices` | ⚪ | Exempt — fixed device |

### 8.4 Platinum (not targeted in full)

| Rule | Status | Notes |
|---|---|---|
| `strict-typing` | ✅ | `mypy --strict`, 0 errors, 35 files |
| `py.typed` | ✅ | Included in package |
| `async-dependency` | 🟡 | `aiosqlite` is async, most dependencies are sync |
| `inject-websession` | ⚪ | Exempt — no HTTP calls |

Full Platinum is not targeted because the integration has no HTTP dependencies to inject.

### 8.5 Maintaining IQS status

Any PR that changes the entity surface, adds a service, or modifies the config flow must update `quality_scale.yaml`. Otherwise, Hassfest CI will warn (but not fail).

Checklist for IQS-impacting changes:

- [ ] New entity → add to `quality_scale.yaml` if it affects a rule
- [ ] New service → update `services.yaml` and translations
- [ ] New repair → add to `repairs.py` and `strings.json`
- [ ] New config option → update `strings.json` and translations
- [ ] New diagnostic field → verify `TO_REDACT` still covers sensitive fields

---

## 9. Release procedure

### 9.1 Pre-release checklist

Before tagging a release:

- [ ] All PRs for the release are merged to `main`
- [ ] Full suite green: 6724 passed, 4 skipped, 100.00%
- [ ] Ruff CI-parity clean
- [ ] Mypy strict clean (35 files)
- [ ] Markdown guard clean
- [ ] All 8 CI workflows green on `main`
- [ ] CHANGELOG `[x.y.z]` section written
- [ ] Version bumped in 3 files:
  - `custom_components/daikin_cycle_ml/manifest.json`
  - `custom_components/daikin_cycle_ml/const.py` (`VERSION`)
  - `pyproject.toml`
- [ ] README badges updated (version, tests count, coverage)
- [ ] Documentation updated for new features
- [ ] Tracker issue completed (all boxes ticked)

### 9.2 Version bump

Three files must match:

```bash
# manifest.json
"version": "1.9.0"

# const.py
VERSION = "1.9.0"

# pyproject.toml
version = "1.9.0"
```

Verify with:

```bash
grep -nE '"?1\.9\.0"?' \
    custom_components/daikin_cycle_ml/manifest.json \
    custom_components/daikin_cycle_ml/const.py \
    pyproject.toml
```

All three must show `1.9.0`.

### 9.3 CHANGELOG format

```markdown
## [1.9.0] - 2026-10-20

### Added

- New features (grouped by theme)

### Changed

- Breaking changes (with migration notes)
- Behaviour changes

### Fixed

- Bug fixes (with issue numbers)

### Removed

- Anything removed

### Breaking changes

If any, list them explicitly with migration steps:

> **`cop_today` is now heating-only.** If your automation expects the blended
> value, switch to `sensor.cop_combined_today`.
```

### 9.4 Tag and release

```bash
git checkout main
git pull --ff-only

# Verify HEAD
git rev-parse HEAD

# Create annotated tag
git tag -a v1.9.0 -m "v1.9.0 — Alerts v2 + 3 P3 alerts + J + I7 + I8"

# Verify tag points to HEAD
[ "$(git rev-parse v1.9.0^{})" = "$(git rev-parse HEAD)" ] && echo "TAG OK"

# Push tag
git push origin v1.9.0

# Create GitHub release
gh release create v1.9.0 \
    --title "v1.9.0 — Alerts v2" \
    --notes-file /tmp/v190_notes.md \
    --verify-tag \
    --latest
```

**Always use `v1.9.0^{}` for tag deref.** Annotated tags point to a tag object, not a commit; `^{}` dereferences to the commit.

### 9.5 Verify release

```bash
# Verify release is not draft
gh release view v1.9.0 --json tagName,isDraft,isPrerelease,publishedAt \
    -q '"tag=\(.tagName) draft=\(.isDraft) pre=\(.isPrerelease) pub=\(.publishedAt)"'

# Verify it's the latest
gh release list --limit 1
```

**Note:** `isLatest` is NOT a field in `gh 2.54` or `gh 2.97`. Use `gh release list --limit 1` or `gh api repos/elRadix/daikin_cycle_ml/releases/latest -q '.tag_name'`.

### 9.6 Deploy to prod

1. Copy the new `custom_components/daikin_cycle_ml/` to `/config/custom_components/daikin_cycle_ml/`
2. Restart HA Core
3. Verify entity count, no errors in logs
4. Run Test-all from OptionsFlow to verify alerts
5. Post release notes

### 9.7 Post-release

- Update tracker #66 with release summary
- Close any completed issues
- Comment on any related issues with "shipped in v1.9.0"
- Update README version badge

---

## 10. Ruleset and branch protection

`main` is protected by ruleset `id=24465625` with 6 required contexts.

### 10.1 Required status checks

All 6 must pass before merge:

1. Ruff
2. Pylint
3. Hassfest
4. HACS Validation
5. Mypy
6. Coverage

Markdown is not required (path-filtered), but should pass when triggered.

CodeQL is not required (dynamic, may not run on every push).

### 10.2 Ruleset rules

- **Require pull request** before merging
- **Require status checks** (6 above)
- **Require branches to be up to date** before merging (rebase if stale)
- **Do not allow force push** to `main`
- **Do not allow deletion** of `main`
- **Do not allow admin override** — must go through PR flow

### 10.3 What this means for you

- **Never push directly to `main`** — always PR
- **Never `--admin` merge** — even for hotfixes
- **Never `--force-push`** — rebase instead
- **Rebase onto latest main** if "branches must be up to date" blocks merge

If a rule absolutely must be bypassed (rare), open a discussion rather than using `--admin`.

### 10.4 Bypassing in emergencies

If `main` is broken and requires an urgent fix:

1. Open a discussion to get maintainer approval
2. Fix in a branch, push, PR
3. CI must still pass — no admin override even for hotfixes
4. Merge normally after CI

The ruleset exists because CI failures are always catchable locally. If CI fails, it means `ci-local.sh` was bypassed. Fix the local environment, do not bypass the ruleset.

---

## 11. Session rules R548–R565 (v1.15.0)

Consolidated rules from the v1.15.0 hardening session. Each encodes a
hard-won lesson from a bug that 100% line coverage did NOT catch: a
silently dead alert-suppression feature, and schema drift between two
CREATE TABLE sources.

### 11.1 Verification (AST, not regex)

**R548 — AST for signature verification.** Never `grep 'def name\([^)]*kwarg'`
— fails silently on multi-line signatures (Black-wrapped). Use
`python3 -c 'import ast; ...'` to walk `FunctionDef.args`. Grep-based
checks in Commit 1 gave a false negative on `CycleDetector.update` — the
parameter existed, the regex didn't find it.

**R554 — AST for string-literal extraction.** Extract Python string
literals via `ast.Constant.value`, never regex. Python concatenates
adjacent literals at parse time, so `Constant.value` is always complete.

**R560 — AST for DDL debugging.** Suspicious concatenation like
`is_transition_artifactINTEGER` from a debug log may be a display artifact.
Verify via `ast.Constant.value` on the source bytes.

### 11.2 Schema discipline

**R549 — Single source of truth for CREATE TABLE.** `schema.sql` is
authoritative for fresh-install DDL. Runtime fallbacks
(`async_ensure_*_table`) MUST match it column-for-column or be ALTER-only.
Two divergent CREATE TABLE statements for the same table is a latent
catastrophe — if the fallback fires before schema execution, tables can
be missing columns that no later migration backfills.

**R551 — Parity test in CI.** Every runtime `CREATE TABLE IF NOT EXISTS`
must have a parser-based test asserting column-set equality with
`schema.sql`. See `tests/test_schema_alignment.py` for the AST-based
pattern.

### 11.3 Test integrity

**R552 — 100% line coverage is not behavior coverage.** A suppression
feature ("suppress alerts when X") can be fully covered yet functionally
dead, because unit tests call the feature function directly with mocked
kwargs the production path never passes. Integration test through the
coordinator call site is mandatory for any conditional-suppression
behavior.

**R553 — `-o addopts=""` for isolated single-file runs.** `pytest.ini`
configures `--cov-fail-under=100` in `addopts`. Running one test file
without `-o addopts=""` fails on coverage with `0.00%` even when tests
pass. Bypass only for isolated runs; keep the gate on the full suite.

**R556 — `python3 - <<'PYEOF'` needs explicit `|| on_fail`.** `sys.exit(1)`
inside a heredoc subprocess does NOT abort a `set -uo pipefail` shell
script. Every python3 heredoc in a mutation script MUST be followed by
`|| on_fail`. Otherwise a failed patch silently continues.

**R557 — Test count from actual content, not comments.** When appending N
tests via heredoc, compute the expected count via grep on the heredoc
content, not from a mental tally.

**R558 — Per-field matrix assertions.** Multi-case loop assertions MUST
use per-row expected values, not "everything should be X". A test asserting
`lwt is None AND outdoor is None` for rows that each had only one bad
field failed while the code was correct.

**R559 — Explicit expected values in matrix tests.** Lay out
`(inputs_tuple) -> (expected_tuple)` explicitly. Implicit "all should be X"
hides per-field logic errors.

### 11.4 Truthy-value hazards

**R555 — isinstance guards for suppression-relevant bools.**
`bool(MagicMock())` is `True`. `bool("no")` is `True`. Any truthy non-bool
gating a suppression decision silently silences real alerts. Use
`x if isinstance(x, bool) else False`. Principle: **NEVER silence alerts
on an ambiguous signal** — over-alert rather than under-alert.

### 11.5 Test invocation and imports

**R561 — `--tb=long` for first traceback, never `tail -N`.** When a test
file fails to import, `pytest`'s short summary truncates to
`ModuleNotFoundError...` — hiding whether the real error is missing
module vs missing symbol. Always run ONE failing test with `--tb=long`
before diagnosing.

**R562 — Verify symbol names before import.** Before writing
`from module import NAME`, grep `module.py` for `^NAME` to confirm it
exists. A whole test file imported `MODEL_CHOICES_NAMES` (doesn't exist;
correct name is `MODEL_LABELS`) — six wasted iterations because the
traceback was truncated (see R561).


**R563 — Specific-test selection.** `pytest X.py::test_a X.py::test_b` per-test works; whole-file may fail sys.path.

**R564 — `python3 -m pytest` for whole-file.** Prefix `python3 -m` puts cwd on sys.path[0].

**R565 — Test files bootstrap own sys.path.** Module top: `_ROOT = Path(__file__).resolve().parent.parent` guarded by `if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))`.

### 11.6 Docs and delivery

**R566 — Docs path flexibility.** Probe both `docs/X.md` and `X.md`; use whichever exists.

**R567 — SSH paste size ≤ 1100 chars.** Larger pastes truncate silently, hang shell at `>`.
## Appendix A — Related files

| File | Purpose |
|---|---|
| `pyproject.toml` | Dependencies, pytest config, ruff config, mypy config |
| `.pylintrc` | Pylint configuration |
| `quality_scale.yaml` | IQS rule status (per HA convention) |
| `hacs.json` | HACS integration metadata |
| `.github/workflows/*.yml` | CI workflows |
| `scripts/bootstrap.sh` | Dev environment setup |
| `scripts/ci-local.sh` | Local CI-parity runner |
| `scripts/pre-push` | Git hook |
| `scripts/check-markdown.sh` | Markdown guard |
| `AGENTS.md` | Development rules and hard rules |

## Appendix B — Quick command reference

```bash
# Setup
scripts/bootstrap.sh

# Test
pytest -q                                          # full suite + coverage
pytest -q --no-cov tests/test_your_file.py        # single file, no coverage
pytest -q tests/test_your_file.py::test_case      # single test

# Quality
ruff check --no-fix --select E,F,W --ignore E501,E402,F401 custom_components/daikin_cycle_ml tests
/opt/mypy-ci-venv/bin/mypy --strict --python-version 3.14 custom_components/daikin_cycle_ml
bash scripts/check-markdown.sh

# Full local CI
scripts/ci-local.sh

# Git
git checkout -b feat/your-change
git add <files>
git commit -m "feat(scope): subject (#66)"
git push -u origin feat/your-change

# PR
gh pr create --base main --head feat/your-change --title "..." --body-file <file>
gh pr checks <num>
gh pr merge <num> --squash --delete-branch

# Release
git tag -a v1.9.0 -m "message"
git push origin v1.9.0
gh release create v1.9.0 --title "..." --notes-file <file> --verify-tag --latest
```
