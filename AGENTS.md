# AGENTS.md — Daikin Cycle ML

Home Assistant integration that turns your ESPAltherma sensor into a
complete heat pump intelligence platform — cycle detection, per-mode COP,
seasonal SPF, weather-normalized degradation, runtime + energy accounting,
installer-grade curve advice, and 19 ML-powered alerts.

Data source: ESPAltherma by @raomin (github.com/raomin/ESPAltherma) —
reads the Daikin Altherma X10A port via ESP32 and exposes the attributes
this integration consumes.

Local-only. No cloud. No accounts. Everything runs inside the Home
Assistant box.

HA custom integration. Python 3.14 (CI) / 3.13 (ruff target, model-compat).
Min HA 2026.9.0 (hacs.json). Loaded automatically by the coding agent at
session start.

NOTE ON FORMAT: code samples use 4-space indented blocks per R349.
Do not add triple-backtick fences when editing this file.

NOTE: DEEPSEEK.md is local-only, gitignored. Read it from the dev
container at /workspace/daikin_cycle_ml/DEEPSEEK.md if present.

## Project identity (v89.0 — updated 2026-11-19 evening)

- GitHub: elRadix/daikin_cycle_ml · default branch main · HACS custom repo
- Dev container: /workspace/daikin_cycle_ml (daikin_cycle_dev, image python:3.14)
  Cloud sessions (claude.ai/code) clone to /home/user/daikin_cycle_ml:
  Python 3.13, no homeassistant package installed — create a venv with
  requirements_test.txt + homeassistant + aiosqlite (CI uses 3.13 too).
  Cloud sessions can push branches but NOT tags and cannot delete remote
  branches (proxy 403). Tags + branch deletion run from daikin_cycle_dev
  via docker exec with a pre-guard (see v87.0 addendum).
- Main tip: d615af7 (release v1.24.1, PR #433). Nothing unreleased.
- Latest release: v1.24.1 (tag v1.24.1 -> d615af7), 2026-11-19.
  Same day: v1.24.0 (tag v1.24.0 -> 177ae8e, PR #429).
  Before: v1.23.3 (143f9cf), v1.23.0-v1.23.2 (2026-11-18), v1.22.10 (91034f5).
- Manifest / const.VERSION / pyproject: 1.24.1 (match)
- Open PRs: none. GitHub deletes the head branch when a PR merges
  (seen for #428 #429 #432 #433): restart the session branch from
  origin/main and push normally, no force (R394).
- Dev container working tree is DIRTY on old commit c9ba74c: modified
  binary_sensor.py, const.py, coordinator.py, scripts/resolve_issue.py +
  untracked tests/test_v12211_cop_flag_visibility.py,
  test_v12211_prod1_983_repro.py. Unreviewed pre-#391 work: diff before
  discarding (TE VERIFIEREN whether anything is missing from main).
- Retired: run.py — never reference
- Ruleset protect-main: id 24465625 — required-context count TE VERIFIEREN
- CI workflows (.github/workflows, 8): ruff, hassfest, hacs, mypy, pylint,
  coverage, markdown, model-compat. Plus CodeQL (dynamic, "Push on main").
- Model compat: v1 definitions pinned to ESPAltherma beta 3548ea2 (#430,
  was b613d10 since #393; docs/MODEL_ATTRIBUTES.json). v2 catalog names pinned to beta 3548ea2
  (#413, docs/ESPALTHERMA_V2_CATALOG.json, tools/parse_espaltherma_catalog.py);
  the PR gate regenerates the snapshot at its pin, the weekly drift issue
  lists removed v2 names (consumed ones first).
- ESPAltherma checkout for alignment work: git clone --depth 1 --branch beta
  https://github.com/raomin/espaltherma (public; definitions/ + data/).

## Trackers / open issues (2026-11-19 evening)

Issue #66 (v1.9 tracker) is no longer the active tracker. Work is now
tracked per issue; commits/PRs reference their own issue
("Part of #N" / "Fixes #N").

Closed 2026-11-18 (solution comment + release link): #347 (@JoHuTi),
#369 (@MBGek), #288 phase 1 (@fransh47), #388, #392 (v1.23.0); #193,
#353, #400 (CuttingStorm, Tweakers), #408 (v1.23.1-v1.23.3).

Closed 2026-11-19 with v1.24.0 (solution comment + release link): #413,
#415, #417, #419, #421, #423, #427.

Closed 2026-11-19: #431 with v1.24.1 (published 18:06); #430 drift
(beta b613d10 -> 3548ea2 only touched web UI / control / i18n: v1
definitions and v2 catalog unchanged, pin moved).
- #425  p3 ux    Show today's alerts in a card (Tweakers feedback)

- #398  p1 enh   Bivalent phase 2: wizard section, binary_sensor
                 bivalent_active, boiler energy sensors, BUH1 vs
                 permission-signal disambiguation, 2 new alerts
- #397  p3 bug   Datasheet follow-up: verify EPGA, EDLQ, EBLQ011-016, EPSK, ERRQ
- #368  enh      Universal Energy Balance Engine + Adaptive Floor Buffer
- #343  p1 enh   Subcooling-based refrigerant diagnostics (espaltherma)
- #339  p2       Diagnostics v2 polish + tech-debt cleanup
- #309           P1/P2 MQTT bridge as input
- #239  p1       [Tracker] RFI #127 thermodynamics + COP sanity gates
- #221  p1       [Tracker] Altherma R Hybrid (EVLQ) — future analytics
- #208  p3       HA dark mode (all cards have dark mode since v1.24.0 #427:
                 TE VERIFIEREN whether #208 can be closed)
- #198  p2       Wizard dropdown -> full Daikin catalog via alias layer
- #189  p1       HT attribute aliases (blocked-external)
- #187  p2 epic  ESPAltherma collaboration (internal decision 2026-11-18:
                 nothing posted on the ESPAltherma repo)
- #175  p3       Per-model stooklijn defaults HT (blocked-external)
- #88   epic     Rolling backlog tracker

Tweakers feedback "alerts not shown in any card" is now #425.

## Current state (v89.0 — 2026-11-19 evening)

- Coverage: 100.00% (pyproject fail_under = 100), CI green on d615af7
- Tests: 6985 collected (README badge 6985)
- Dashboard cards (7): one header with the model, shared variables
  (lang_override / theme_override / show_help + card-specific), EN/NL/FR,
  dark mode; shared block tools/card_common.js synced by
  tools/sync_card_common.py; docs dashboard/cards/README.md; every card
  folder has README + CHANGELOG (cards 1.1.x); screenshots of every card
  and tab rendered from the integration's states (same filenames)
- Sensor daily_summary_recent exposes events_by_day (#427); heating-curve
  advice keeps measured buckets / LWT during DHW and BUH (suppressed_by)
- DB data migrations v31 (#415 stale cop_hourly rows), v32 (#419 runs lost
  on restart rebuilt from cop_samples, is_reconstructed = 1), quality
  rescore (#421, marker data_migration_quality_v2_completed), off-time
  relearn (#415, marker data_migration_off_s_relearn_completed);
  cycles.buh_s / cycles.defrost_s columns (#421)
- DB data migration v30 (#408): flags pre-gate COP outliers, rebuilds
  cop_hourly hours + all daily_summary days once (marker
  data_migration_v30_completed)
- New option: buh_power_sensor_entity (Device -> Sensors), added to the
  power meter for electrical power / COP only
- Pylint 10.00/10 · Ruff clean · Mypy strict 0 errors (CI, HA pin 2026.9.3)
- Translations: en, nl, fr (+ icons.json)
- Entities (README): 50 sensors · 17 binary sensors
  (strings.json entity keys: sensor 51 / binary_sensor 20 — difference TE VERIFIEREN)
- Services: 13 (services.yaml) · Repair issues: 11 (strings.json issues)
- Alerts: 19
- DB: daikin_cycle_ml.db schema v16 (v1.12.0 migration, #105/#107) ·
  HA Store alerts v1 · user datasheet store v1
- IQS: Bronze + Silver + Gold (README badge)
- prod-1: v1.23.3 on HA 2026.11.1 (diagnostics 2026-11-19 06:42); update
  to v1.24.1 + re-paste all cards TE VERIFIEREN; then check SQL section A
  (~100 % per day), runtime_check, cop_cross_check, rescored quality
- QA scripts: scripts/bootstrap.sh, scripts/ci-local.sh, scripts/pre-push,
  scripts/check-markdown.sh, scripts/create_issue.py, update_issue.py,
  resolve_issue.py, git_safe.py

### Superseded v83.0 snapshot (2026-10-19, VERVALLEN — kept for history)

- Main 14dadfe (PR #82), tracker #66, release target v1.9.0, stable v1.8.1
- Tests 6724 / 4 skipped, 35 mypy files, 50 / 15 entities, 10 services,
  8 repairs, DB schema v15, prod 14dadfe on HA 2026.10.1

## Hard rules (ACTIVE — never violate)

    R50   Never log tokens or credentials.
    R91   Never amend pushed commits.
    R327  Quoted heredocs for patches containing backticks.
    R328  Verify headRefOid after gh pr create — must match local HEAD.
    R329  No | head -N under set -euo pipefail — SIGPIPE kills the block.
    R347  After translation deploy: HA Core restart OR config-entry reload.
    R350  Recon-grep before any alert-pipeline change. --exclude-dir=__pycache__.
    R351  VERVALLEN (v84.0): #66 no longer the tracker. Current practice:
          commit/PR references its own issue ("Part of #N" / "Fixes #N").
          Tick tracker boxes only AFTER merge.
    R352  Never combine cat >> and gh post in one heredoc. Split, or cat >.
    R353  getattr(self, name, default) in _build_alert_context /
          _alert_binary_states. Never direct attribute access.
    R355  Assert-guarded patch reports count != 1: run git status BEFORE retry.
    R369  No backticks in gh body-file heredocs — use Python writer + sanity-check.
    R370  Source-mutation: inspect → mutate → verify. Never blind sed on assumed line.

### Handoff + multi-repo (R133-R145)

    R133  Handoff when context ORANGE, YELLOW + milestone, or RED mandatory.
    R134  Handoff version = +1 major (v16.0 -> v17.0), never minor.
    R135  Handoff is self-contained — fresh chat must reconstruct everything.
    R136  Handoff marks unknowns as TE VERIFIEREN.
    R137  Handoff marks expired rules explicitly, does not delete them.
    R138  Handoff first checks: git status, CI status, PR status, containers.
    R139  Handoff version = full git-commit-hash + tag reference.
    R140  Generate handoff via chat, save via heredoc (R90-safe).
    R141  Two repos: daikin_cycle_ml (dev) + default (HACS-fork). Never confuse.
    R142  Fork default: never push to branch after PR-open (HACS-bot closes PR).
    R143  New HACS PR = new branch from fresh upstream/master.
    R144  Sync fork-master for new PR: git reset --hard upstream/master + --force-with-lease.
    R145  Fork git identity local (--no-global), never --global in container.

## Hard rules (CANDIDATES)

    R336  Double-paste heredoc failure mode.
    R337  json.dumps(..., ensure_ascii=False) for translations.
    R345  Phantom reads — verify with repr() + str.count() server-side.
          AMENDED v83.0: on grep/sed conflict, sed -n '<line>p' is authoritative.
    R346  Local verification = same command as CI:
          ruff check --no-fix --select E,F,W --ignore E501,E402,F401.
    R348  Plan-B steps must document WHICH code path they exercise.
    R349  Heredoc markdown MUST use 4-space-indented code blocks.
    R354  mypy strict needs temp var for getattr ternary.
    R356  Pre-cut symbol-grep over WHOLE repo, not cut window.
    R357  Post-cut substring guards use word-boundary regex.
          db_avg_duration_min contains _avg_duration_min.
    R358  Structural source-grep tests break on legit refactor.
    R365  Alert-registry grow → sweep len(X) AND len(X[key]) across all test files.
    R366  No `except Exception:` in new helpers — never swallow NameError/AttributeError.
    R368  ALERT_LABELS entry required per context key; missing key = render KeyError.
    R371  set -uo pipefail + RC gates for grep-heavy heredocs; never set -euo with grep.
    R372  sed -n '<line>p' is authoritative over grep when they disagree.
    R373  Alert cache snapshot MUST fall back to store query for per-tick fields.
    R374  stdin-reading cmds in bash -s heredocs consume rest of body — append </dev/null.
    R375  Multi-mutation Python patch >1.5KB → split into ≤1.5KB chunks with per-chunk verify.
    R376  Container paths in bare paste — wrap with docker exec -i daikin_cycle_dev bash -lc 'bash -s'.
    R377  Pre-guard block includes git status --porcelain + git rev-parse HEAD in same paste.
    R378  ALERT_LABELS nested per-language {"en": {...}, "nl": {...}} — index via ["en"][key].
    R379  Session-loss mid-patch recovery: git status + diff -q backup + grep apply-markers + AST + pytest.
    R380  Coupled day-key lifecycle gates — split per subsystem.
    R381  Restore-failure isolation per subsystem — never block downstream writes for siblings.
    R382  Ruff E702 semicolons in test files — split into separate lines.
    R383  CI poll timeout ≠ failure — diagnose via gh run list --commit $SHA before amending.
    R384  Heredoc delimiter mismatch = PS2-trap, nothing mutated. Ctrl+C → echo READY → re-paste identical.

### Active rules added in v89.0 (2026-11-19)

    R385  Release notes: ALWAYS give the full Markdown source in the chat
          (one fenced markdown block, ready to paste), not only a file.
          Gallery / image URLs point at the tag (raw.../vX.Y.Z/...);
          the user tags before publishing.
    R386  Merge via the GitHub MCP with the full 40-char head SHA from
          git ls-remote (short or typed SHAs are refused).
    R387  Card variables live on the header button-card (variables: &dcm)
          and every other button-card has variables: *dcm. Variables on
          the outer stack-in-card are ignored by button-card.
    R388  Card taps: never rely on click. button-card calls preventDefault
          on touchend (no click on touch) -> use pointerup with a
          movement guard. A button-card without actions is disabled
          (pointer-events: none) -> its content needs pointer-events: auto.
          Test touch with a harness that reproduces both.
    R389  Shared card block (DCM-COMMON): edit tools/card_common.js, run
          tools/sync_card_common.py; never edit the block in a card
          (tests fail on drift, --check).
    R390  Card changes: render every card under Node in EN / NL / FR /
          dark (tests/test_427_cards_live_states.py, fixture from the real
          integration) and look at it in Chromium before merging.
    R391  Every card change updates that card's CHANGELOG.md and README;
          screenshots keep their filenames (main README and external
          sites link to them) and every image is shown in its card README.
    R392  pattern-analysis.yaml is CRLF: rewrite with CRLF kept; a huge
          git diff --stat = line endings lost.
    R393  Long in-container simulations: --timeout=0/N (pytest-timeout
          default 120 s) and delete testing_config/.storage/daikin_cycle_ml*
          first (the DB survives between runs; a restored detector from
          a later run blocks every sample as clock skew).
    R394  After a merge the remote head branch is gone: git checkout -B
          <session branch> origin/main and push normally (never force).
    R395  Every diagnostics file that is sent (issue, chat, prod) is
          ingested with tools/ingest_diagnostics.py into
          tests/fixtures/diagnostics (anonymised, trimmed, INDEX.json).
          Never store or mention a reporter's name or handle; --note
          describes the install or the problem only. See the README
          in that folder.

## Historical rules (RETIRED)

Run.py retired since v77.0. Retained for archival context only. Never apply.

### Run.py rules R83-R92


Supplement to DEEL 2 of the handoff. Added in batch 52c.

| Regel | Inhoud |
|-------|--------|
| R83 | Bootstrap P0: verify ruff + sqlite3 + pylint present before use |
| R84 | Fragile test-files: async setup_entry always asyncio.wait_for(timeout=3); OptionsFlow tests always conftest autouse reload-mock |
| R85 | Wall-time tracking. Full suite >90s -> flag voor refactor |
| R86 | Version bump = one commit. Version + CHANGELOG + README + tag + push in one batch |
| R87 | Context orange 80%+ and >3 iterations on same batch: STOP, handoff, fresh chat |
| R88 | CI compliance. Pylint + ruff both green. .pylintrc scope = integration code |
| R89 | Pytest exit code via pipe unreliable. Use subprocess.run(cmd, capture_output=True) without shell pipe, then Python-side tail |
| R90 | File Editor fails silently on files >5 KB. Fallback: heredoc chunks via SSH addon (cat > /config/run.py << 'RUNEOF'). Always verify with marker-grep + wc -l |
| R91 | Amend + reset --soft: hash-aware. On batch-mix: git commit --amend -m "<new message>". Force-with-lease expected after amend |
| R92 | Amend-fix must not commit on red pytest. P5->P6 sequence hard-stop if pytest fails. No try/except around commit step |

### Corrections on earlier notes (pre-v1.9 era)


- README executable bit: was 100644 (correct). No chmod needed. Handoff note was wrong.
- Entity binary_sensor.daikin_cycle_ml_missing_attributes (not _attrs).
  Repair issue-id remains missing_attrs (internal identifier).
- Stooklijn advies states: verlaag_lwt_2c, verhoog_lwt_2c, behoud, unknown.
- Entity counts: 9 sensors + 15 binary sensors = 24 (not 26+16 or 29+19).
- Repairs (5): source_stale, missing_attrs, db_corrupt, notify_failed, migration_failed.
- Services (6): reset_counters, export_cycles, label_cycle, recompute_baseline, run_maintenance, send_test_notification.
- DB tables (7): cycles, features, alerts, daily_summary, cop_samples, model_state, sqlite_sequence.


#### R96 (batch 52b6)

**pytest-cov fail_under valkuil.** `[tool.coverage.report] fail_under=95`
in pyproject.toml blokkeert pytest NIET. pytest-cov print
"FAIL Required test coverage of 95% not reached" maar returnt rc=0.

**Fix:** voeg `--cov-fail-under=95` expliciet toe aan pytest-args in P5:

    python3 -m pytest -q --no-header --cov-fail-under=95

Alternatief: CI-workflow die `coverage report --fail-under=95` draait
na pytest.

Zonder deze fix kunnen coverage-drops ongemerkt door glippen (batch 52b5:
94.99% gemerkt door handmatige inspectie).


#### R102 (batch 52g) - performance-tooling verdict

**Rejected on 2-core + Python 3.14 environment** (measured 2026-09-27):

- **pytest-xdist** (`-n 2 --dist loadscope`):
  - Full suite: 64s -> 45s (-30%)
  - But: 2 tests in `test_18_options_menu.py` fail in full-suite
    xdist context (cross-file state contamination; not xdist's fault)
  - Fix cost: 1-3h bisect; win: 19s per run - not worth on 2 cores
  - Revisit if CI runner goes >=4 cores (2-3x win would justify fix)

- **pytest-testmon 2.2.0**:
  - Incompatible with Python 3.14 (uses sys.monitoring / PEP 669)
  - Selects 0 tests even on real content changes
  - Revisit when upstream adds 3.14 support

- **Baseline (accepted)**: sequential full suite ~64s local, ~65s CI

Do not re-attempt without a hardware or Python-version change.
Re-measure first (probe recipe: sequential vs xdist on subset AND full).

### Gap-note: R93-R132 absent from this document


SOP.md bevat momenteel alleen R83-R92 (sectie 10) en R96, R102 (sectie 11).
Regels R93, R94, R95, R97-R101, R103-R132 leven alleen in handoff-chat-historie
(handoff v15.0-v17.0 DEEL 2.8).

Backfill naar SOP.md is een openstaande taak (niet docs-triviaal - vereist
per-regel recon + format-matching). Zie handoff v17.0 DEEL 15.1 #2.


## Forbidden

- gh pr merge --admin
- Skipping Plan-B for any alert-render release
- Referencing run.py
- Pasting same heredoc twice in one block (R336)
- json.dumps(..., ensure_ascii=True) on translations (R337)
- Triple-backtick fences inside heredocs (R349)
- Typo claim without grep -c / repr() evidence (R345)
- Direct attr access in _build_alert_context / _alert_binary_states (R353)
- Amending pushed commits (R91)
- Merging a PR without the user's own ask ("merge when green" counts)
- Publishing release notes without the Markdown source in the chat (R385)
- Pushing branch with any PR G batch uncommitted


## CI gates (must pass before every commit)

- Smoke:   pytest --no-cov tests/<file>
- Full:    pytest -q  (target: 100.00% coverage, fail_under=100)
- Ruff:    ruff check --no-fix --select E,F,W --ignore E501,E402,F401 <files>
- Mypy:    mypy --strict custom_components/


## Standard workflow

1. Read HANDOFF.md → run bootstrap.
2. Recon (R350 grep) — no writes.
3. Review plan with user. Wait for "go".
4. Implement, one commit per deliverable. Subject references its issue (#N).
5. Verify — full pytest + ruff + mypy.
6. Review — pre-merge rule check.
7. Plan-B live-fire — MANUAL: user triggers OptionsFlow Test-all.
8. Merge — only on the user's ask ("merge when green" counts): squash via
   the GitHub MCP with the full head SHA (R386); never --admin.
9. Tracker tick — VERVALLEN (v89.0, #66 retired): comment on and close the
   PR's issues after the release ships (release procedure step 7).


## Tracker rule (added 2026-10-08)

For any multi-PR effort, create one tracking issue before opening the
first child PR. The issue body carries:

- The design doc or audit content
- A per-PR checklist (one section per PR)
- Follow-up items
- Locked decisions

Every child PR references the issue number in its body. On completion
of each child PR, update the issue checklist (tick the box, comment
with the merge commit hash). The issue is closed only when the final
release ships.

Handoff sections 15 (tasks) and 16 (backlog) reference the tracker
issue number. They do not duplicate its content.

Active tracker: see issue pinned on the repository.

Rationale: a merged PR cannot serve as a tracker (GitHub locks it).
Issues have native checklists, comments, and cross-links, and close
only when the work is done.

## Bootstrap rule (added 2026-10-08)

Every handoff document includes a bootstrap block: a single paste that
fetches full session state and pending actions. The handoff does not
duplicate what the block fetches. The block reports:

1. Git state: HEAD, branch, tree, tag deref, origin/main
2. Last 5 commits
3. Open PRs
4. Open issues
5. Pinned issues (tracker)
6. Active tracker: pending checklist items
7. Active tracker: done checklist items
8. Active tracker: last 5 comments
9. Recent CI runs on main
10. Next action line

A second block (run on the HA host, not in the dev container) reports
production state: HA Core version, entity count, daikin error tail.

SOP.md references the current active tracker issue number explicitly.
When the tracker changes (a new multi-PR effort), the bootstrap block
in the new handoff points at the new issue.

Rationale: eliminates guesswork in fresh sessions. The handoff stays
small; the live state comes from GitHub via the bootstrap block.

## SSH

    Tailscale: ssh root@100.81.96.34 -p 2222
    LAN:       ssh root@192.168.1.237 -p 2222


## Scope boundaries

- In scope: custom_components/daikin_cycle_ml/, tests/, .github/workflows/, translations
- Out of scope: run.py, HA supervisor config, anything outside the repo
- New files: under 500 lines


## Scope

Local-only Home Assistant integration that detects compressor cycles on
Daikin Altherma heat pumps, classifies pendulum behaviour, scores cycle
quality, and advises on configuration. No cloud. No setpoint writes.

Out of scope: cost tracking, HACS publication, supervised ML,
COP calculation (provided by external package).

## Install

1. Copy custom_components/daikin_cycle_ml/ into the HA config tree.
2. Restart Home Assistant.
3. Settings -> Devices & Services -> Add Integration -> Daikin Cycle ML.
4. Complete the 8-step wizard:
   user -> model_custom -> attributes -> cycle -> pendulum -> quality
   -> notifications -> finalize.

## Configuration

Options can be edited via:
- Settings -> Devices & Services -> Daikin Cycle ML -> Configure (quick)
- Reconfigure -> quick (source + model) or full wizard

Key options:
- compressor_rps_threshold (default 3)
- short_run_threshold_min (default 20)
- good_run_threshold_min (default 45)
- pendulum_cycles_per_day (default 40)
- persistent_enabled (default true)
- quiet_hours_enabled / start / end
- notify_service (e.g. a notify entity such as notify.telegram_bot_123_456)
- notify_emoji_enabled (default true)
- status_update_enabled (default false)
- status_update_interval_hours (default 24)
- retention_enabled / cycle_retention_days / alert_retention_days
- vacuum_enabled

## Daily operation

Sensors (50 per README) — subset below; full list in live entity registry:
cycle_state, current_cycle, last_cycle, today, quality_today,
source_health, learned_thresholds, cop_vandaag, stooklijn_advies.
Binary sensors (17 per README; list below is the v83 subset): compressor_running, defrost_active, buh_active,
dhw_active, heating_active, cooling_active, pendulum_hourly,
pendulum_daily, short_run, short_off, source_stale,
missing_attributes, setpoint_oscillating, dhw_pendulum, high_cycle_rate.

Services (13):
- daikin_cycle_ml.reset_counters
- daikin_cycle_ml.export_cycles
- daikin_cycle_ml.label_cycle
- daikin_cycle_ml.recompute_baseline
- daikin_cycle_ml.run_maintenance
- daikin_cycle_ml.send_test_notification
- daikin_cycle_ml.export_cop_hourly
- daikin_cycle_ml.import_datasheet
- daikin_cycle_ml.remove_user_datasheet
- daikin_cycle_ml.recompute_kmeans
- daikin_cycle_ml.assign_legacy_db
- daikin_cycle_ml.archive_legacy_db
- daikin_cycle_ml.export_legacy_db

Scheduled jobs (automatic):
- poll every 30s
- baseline save every 6h
- maintenance daily 03:00
- k-means Sunday 04:00
- status update every N hours (opt-in)

## Troubleshooting

| Symptom | Check |
|---------|-------|
| No cycles detected | source sensor entity_id, source_stale repair |
| All modes unknown | I/U operation mode attr present? |
| No notifications | notify_service configured, quiet hours not active |
| No status updates | status_update_enabled = true? |
| DB errors | path /config/.storage/daikin_cycle_ml.db, permissions |
| Baseline empty | wait >= 3 cycles; check model_state['baseline_state'] |
| k-means empty | wait 1 week; check model_state['kmeans_state'] |
| Missing attrs | repairs issue list_missing_attributes |

Diagnostics endpoint: Settings -> Devices & Services -> Daikin Cycle ML
-> Download diagnostics. Includes:
- entry (redacted), coordinator state, store counters, last cycle
- baseline summary (per-mode sample counts)
- database counts (5 tables) + extra (daily_summary 7d, model_state keys)

## Changelog policy (added 2026-11-18)

- CHANGELOG.md is APPEND-ONLY. Add new items under ## [Unreleased]
  using the existing section style (### Added / Changed / Fixed / ...).
- Never restructure, reformat, regroup or re-link existing history.
  A full Keep a Changelog reformat was tried (f140781) and reverted
  (8d46d9f) on user instruction.
- Fixes stay under [Unreleased] until the user decides to release;
  no version bump or tag on your own initiative.
- PRs for user-reported issues use "Part of #N" (not "Fixes #N") so the
  issue stays open until the release ships and the reporter confirms.

## Release procedure (reference: PR #386 v1.22.10, #396 v1.23.0)

Release PR = version bump only, ONE commit, nothing else in it.

1. Branch release/vX.Y.Z from fresh origin/main (cloud sessions may use
   their assigned claude/... branch).
2. Bump in one commit "chore: release vX.Y.Z":
   - custom_components/daikin_cycle_ml/const.py  VERSION = "X.Y.Z"
   - custom_components/daikin_cycle_ml/manifest.json  "version": "X.Y.Z"
   - pyproject.toml  version = "X.Y.Z"          (all three must match)
   - README.md badges: version-X.Y.Z and tests-<collected test count>
   - CHANGELOG.md: insert "## [X.Y.Z] - YYYY-MM-DD" directly under
     "## [Unreleased]" (append-only; existing items move under it as-is,
     add missing ### Tests lines for new test files)
3. Verify: pytest tests/test_50d_version_contract.py -v --no-cov (7 passed),
   ruff clean; CI gate is authoritative.
4. PR title "chore: release vX.Y.Z", labels chore + priority:p2. Body has
   four H2 sections, in this order:
   - Summary: "Release vX.Y.Z"
   - Changes: version bump A -> X.Y.Z (const.py, manifest.json,
     pyproject.toml); README badges version + tests N; CHANGELOG entries
     under [X.Y.Z] (one-line list)
   - Already merged in this release: one line per PR (#N short description)
   - Test Plan: test_50d_version_contract 7 passed; ruff clean; CI gate
     (authoritative)
5. After CI green + merge: comment on the PR
   "Post-merge verification: PR #N merged into main. vX.Y.Z release
   merged. CI green. Ready for tag."
6. Tag vX.Y.Z on the merge commit, push tag (user, from daikin_cycle_dev),
   publish GitHub release (template of previous releases: logo, star
   badge, end-user "What's new" with benefits for the heat pump and issue
   links, "After updating" incl. which cards to re-paste, card gallery
   with image URLs on the tag, Thank you, Manuals, technical section,
   Support). ALWAYS hand over the full release-notes Markdown source in
   the chat (R385). Optionally a Tweakers post (Dutch, UBB) in the same
   reply.
7. Comment on and close the issues in the release; reporters get update
   instructions (HACS update, restart, re-paste cards, model check).

## Known limitations (v0.2 — historical)

Items below reflect the v0.2 state. Some are resolved post-v1.6 (see Update log);
retained for archeology.

- No COP / cost (out of scope)
- No HACS publication (out of scope)
- All ML is unsupervised; no training labels
- Cluster sensors not exposed yet (12b)
- Adaptive thresholds not wired yet (12a)

## Reference

- README.md - quick start
- DOCUMENTATION.md - full architecture + ML flow
- ROADMAP.md - phase tracking
- CHANGELOG.md - release history

## Update log (append-only)

### 2026-09-25 - 12a adaptive thresholds

- New module ml/adaptive_thresholds.py (pure, no HA imports).
- Learned values via percentile: short_run p20, good_off p50,
  target_cycles_per_day p50.
- Wired into coordinator via _effective_threshold(key, default):
  only active when adaptive_thresholds_enabled=True (default false).
- Persisted as model_state['adaptive_thresholds'] on the 6h hook.
- 3 new sensors expose learned values (return unknown below
  adaptive_min_samples, default 20).
- Entity count: 26 -> 29 sensors.

### 2026-09-25 - 12b cluster activation

- ml/clustering.py extended with nearest_centroid + classify_clusters.
- storage/schema.sql: cycles.cluster_id column added.
- storage/db.py: async_update_cycle_cluster (lazy ALTER TABLE migration),
  async_count_by_cluster, async_ensure_cluster_column.
- Coordinator loads model_state['kmeans_state'] at startup and assigns
  cluster_id to every new cycle via nearest-centroid.
- 3 new binary sensors: cluster_pendulum, cluster_normal, cluster_dhw_like.
- Diagnostics: cluster summary (centroids, labels, counts per cluster).
- Cluster labels auto-derived from centroid properties.
- Entity count: 16 -> 19 binary sensors.

### Current total

- 9 sensors + 15 binary sensors = 24 entities.
- Coverage gate: >=95% (currently ~95.1%).
- Old DBs auto-migrate on first cluster write.
- Repairs (5): source_stale, missing_attrs, db_corrupt,
  notify_failed, migration_failed.
- Services (6): reset_counters, export_cycles, label_cycle,
  recompute_baseline, run_maintenance, send_test_notification.
- DB tables (7): cycles, features, alerts, daily_summary,
  cop_samples, model_state, sqlite_sequence.

## Session history note

Dev container was lost 2026-10-18 (docker image + container pruned after HA OS
upgrade). Branch reconstructed from chat transcript same day. Commit SHAs differ
from the original session (pre-crash had 7 commits). Content is equivalent;
consolidated into fewer commits during rebuild (docs merged, SHA-record commits
dropped). All work is now pushed to origin after each batch to prevent recurrence.

### v83.0 addendum (2026-10-19)

- I6 (energy_daily_anomaly) + J (avg_duration_7d_min) + I7 (pre-release cleanup) + I8
  (energy_acc decoupling) shipped on 2026-10-19, main = 14dadfe.
- AGENTS.md consolidated from SOP.md (removed) as single source of truth.
- SOP.md → git rm, all sections migrated here verbatim.
- Run.py rules R83-R92 moved to Historical rules (RETIRED) section.
- Rule catalog R374-R384 promoted from candidate → active.

### v84.0 addendum (2026-11-18)

- Handoff refreshed from live git + GitHub state; v83.0 snapshot was stale
  (v1.9.0 era). Main = 25c2d48, latest release v1.22.10.
- Product description (README intro) added to top of this file.
- Tracker #66 retired as active tracker; R351 marked VERVALLEN.
- Open follow-ups: #388 remainder, Model compat scheduled failure,
  test count + prod state TE VERIFIEREN.

### v85.0 addendum (2026-11-18 evening)

- Merged: #390 (cards resolve entities in any language), #391 (COP-sensor
  MAX_COP gate; flagged cop_samples excluded from all aggregates), #393
  (Daikin-sourced datasheet values with `ref`/`verified`, 11 non-catalogue
  models flagged not removed, MODEL_ATTRIBUTES @ beta b613d10).
- Open: #394 (EVLQ nominal A7/W35, hybrid indoor-code aliases, COP < 1.0
  flagged via physics.below_cop_floor — classifier contract untouched),
  #288 PR (boiler signals trusted for hybrid OR `Bivalent Operation`).
- Docs aligned: README, CONFIGURATION §4.8, ENTITIES, DATABASE
  (is_transition_artifact), ALERTS, TROUBLESHOOTING (§4.6 dashboards, §5.1
  guards), MODEL_COMPATIBILITY coverage table (generated from datasheets.json).
- Lessons: count-pin tests (EXPECTED_CANONICAL_COUNT) must be bumped when
  ALIAS_GROUPS grows (R365); never `git stash` while a background suite runs.

### v86.0 addendum (2026-11-18 night)

- Released v1.23.0: #394 + #395 merged, release PR #396 (version bump
  only, PR #386 template, post-merge verification comment posted).
- Release first published as tag `1.23`; user retagged to `v1.23.0`
  (same commit d24187e). Release + compare + issue-comment links verified
  200. Stray tag `1.23.0` deleted from the dev container.
- Cloud sessions cannot push tags or delete branches (proxy 403). Do it
  from daikin_cycle_dev: docker exec -i daikin_cycle_dev bash -lc
  'bash -s' with a pre-guard (tip == merged PR head) before deleting.
  Always publish releases with tag `vX.Y.Z`.
- Release notes source: logo, star badge, What's new (end-user), After
  updating, Thank you (reporters by @handle), Docs, Technical, Follow-ups,
  Tests, Changelog/compare, Support. Template = release 1.23.
- Release procedure now documented under "Release procedure" (above).
- Follow-ups opened: #397 (datasheets), #398 (bivalent phase 2).
- Prod deployed version / HA Core: TE VERIFIEREN (expect 1.23.0 after
  HACS update; R347 restart).
- Lessons: markdown gate rejects indented `##` / 5+-space bullets even
  inside 4-space code blocks — keep AGENTS.md templates as plain bullets.

### v87.0 addendum (2026-11-18 late night)

- Released v1.23.1 (#401 #402 #403), v1.23.2 (#405), v1.23.3 (#407 #409
  #410). Release PRs #404 #406 #411 (PR #386 template, labels chore +
  priority:p2, post-merge verification comment).
- Behaviour now on main:
  - A cycle is never closed at midnight; daily_summary splits runtime and
    longest per day, count/quality/BUH/defrost on the start day; the
    15-min live rollup includes the detector's open cycle on every day
    it covers (open_cycle=..., cycle rows are written on close only).
  - daily_summary_recent.events_by_day (runtime_acc.<day>: BUH minutes,
    defrost events) feeds Daily Summary Tabbed Events + Pattern Analysis.
  - buh_excessive = BUH minutes / compressor minutes (7 d), cycle ratio
    only as fallback.
  - AUTO tie (v2 wins, Q1 kept): monolithic extras merged into the
    individual attrs (native Stats: counters survive).
  - Datasheet outdoor via build_compat_view(ATTR_OUTDOOR_AIR_R1T).
  - Effective short_run threshold >= half the configured value.
  - Diagnostics: coordinator_timing.tick_duration_max_{ts,tick,phases_ms},
    database.pending_cop_samples / last_vacuum, coordinator.cop_cross_check,
    source_resolution.supplemented_from_mono.
  - docs/cycle-thresholds.json + drift test; Carnot factor stays 0.65.
- prod-1 (EPRA12EAV3, HA 2026.11.1): on v1.23.2 max tick 315 ms (startup),
  27 s spike not reproduced. Advice given: set BUH power sensor to
  sensor.weerstand_power and clear cop_sensor_entity (user template
  sensor.altherma_global_cop mixes v2 entity + mono attrs -> reads ~24 %
  high). TE VERIFIEREN after update: cop_cross_check, buh_meter_w,
  cop_vs_datasheet_pct (-27 % seen once next to a 7 min short run).
- Tag + branch cleanup from the dev container (cloud gets 403):

      docker exec -i daikin_cycle_dev bash -lc 'bash -s' <<'EOF'
      set -uo pipefail
      cd /workspace/daikin_cycle_ml || exit 1
      git fetch -q origin main --tags </dev/null
      SHA=<merge sha>
      git show "$SHA:custom_components/daikin_cycle_ml/manifest.json" | grep version
      git tag -a vX.Y.Z "$SHA" -m "vX.Y.Z" && git push origin refs/tags/vX.Y.Z </dev/null
      EOF

  Branch deletion: same wrapper, delete only when the remote tip equals
  the merged PR head (pre-guard), then git push origin --delete.
- Lessons:
  - CHANGELOG conflicts between parallel PRs: git's conflict block can
    start mid-section; merge per ### section and assert every line of
    both sides survives before writing (one bullet was dropped once).
  - Tests that pass alone can fail in the full suite when another suite
    patches OptionsFlow.config_entry: pin it with monkeypatch.
  - A test that injects data production never writes (hand-made open
    cycle row, last_record + raw mono key) hides real gaps (#405, #407).

### v88.0 addendum (2026-11-19)

- Merged (unreleased): #414 (v2 catalog names, I/U O/U side names,
  cooling for no-DHW installs and "Auto Cool"), #416 (off_s = start -
  previous end, v31 stale cop_hourly, curve tracking same-moment,
  cop_vs_datasheet_low on a steady 1 h mean, weighted p10/p90), #418
  (restore before the first tick, persist on split + every 15 min, resume
  gap = downtime), #420 (ended_by / continued, split segments not short,
  live score, diagnostics runtime_check, v32 lost-run rebuild), #422
  (proportional penalties incl. BUH time and defrost, rescore of all
  cycles), #424 ("0"/"1" as numbers, dT from R1T, bounded accumulator
  write, learned_thresholds state = value in use, log on change).
- Root causes found on prod-1 (runs 24/7): restart restored the detector
  after the first tick (44-84 % runtime on restart days); off_s measured
  at close; heating <-> DHW split treated as a stop; live score judged
  an open run; ESPAltherma v2 "0"/"1" read as booleans.
- SQL check for daily runtime (local days, cycles split at midnight) and
  lost runs: see the session transcript / issue #417; prod-1 DB at
  /config/.storage/daikin_cycle_ml_01M57X8B5FM4PVFEN8JV9ZKH5V.db
  (sqlite3 -readonly from the Advanced SSH add-on). HA OS has no
  home-assistant.log; `ha core logs` shows only the recent window.
- Quality score formula is documented in docs/ML.md (penalty table);
  tests pin values with the arithmetic in a "#421" comment.
- Lessons:
  - A test pinning a contract (fixed penalties, cache-first LWT, raw
    learned state) is updated with the new arithmetic in a comment, never
    deleted.
  - Always pass the full head SHA from git ls-remote to merge (a typed
    SHA was refused with 409).
  - Run detector tests with power_w and an explicit "off" sample (COP and
    flow alone keep the compressor "on").
  - A startup step on the coordinator goes through a guarded module
    helper: setup tests use a MagicMock coordinator.

### v89.0 addendum (2026-11-19 evening)

- Released v1.24.0 (#429): #414 #416 #418 #420 #422 #424 + #428 (cards
  unified: header with model, shared variables, EN/NL/FR, dark mode,
  events_by_day, heating-curve points, DHW rendering, docs index).
  Issues #413 #415 #417 #419 #421 #423 #427 closed with a solution comment.
- Released v1.24.1 (#433): #432 (pattern-analysis touch via pointerup,
  heating-curve point pop-ups, tiles fit narrow cards, new screenshots of
  every card and tab). #431 closes once the release is published.
- Root causes worth remembering:
  - stack-in-card variables never reached button-card (R387): every
    lang_override / default_tab / theme option was dead config before #428;
  - click listeners in button-card fail on touch (R388);
  - the stooklijn advice was wiped during DHW / BUH, emptying two cards;
  - events_by_day was built (#400) but never exposed by the sensor: a
    test that injects payloads skips the sensor layer, so the card test
    now renders from states of the real integration.
- Tooling: tools/card_common.js + tools/sync_card_common.py;
  tests/test_427_cards_live_states.py (fixture generator inside, opt-in
  with DCML_DUMP_CARD_STATES=1); screenshots are rendered with a
  Playwright harness (button-card cards in shadow roots, ha-icon stand-in
  with MDI paths, SVG animations frozen), not committed.
- User preferences: release notes source always in chat (R385); clear
  end-user language about the benefits for the heat pump and the request
  to re-paste cards; galleries of all card screenshots in releases;
  image filenames never change.
