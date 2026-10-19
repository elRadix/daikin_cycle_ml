# AGENTS.md — Daikin Cycle ML

HA custom integration. Python 3.14, HA Core 2026.10.
Loaded automatically by DeepSeek Code at session start.

NOTE ON FORMAT: code samples use 4-space indented blocks per R349.
Do not add triple-backtick fences when editing this file.

NOTE: DEEPSEEK.md is local-only, gitignored. Read it from the dev
container at /workspace/daikin_cycle_ml/DEEPSEEK.md if present.

## Project identity

- Repo: /workspace/daikin_cycle_ml (daikin_cycle_dev, image python:3.14)
- Main tip: 14dadfe (I8 squash merge, PR #82)
- Working branch: none (main clean)
- Tracker: GitHub issue #66 (PINNED, 66 done / 21 pending)
- Release in flight: v1.9.0 (target); stable is v1.8.1
- Retired: run.py — never reference
- Ruleset protect-main: id 24465625, 6 required contexts
- CI workflows on main: 7 (Ruff, Hassfest, HACS Validation, Mypy, Pylint, Coverage, CodeQL)

## Current state (v83.0 rebuilt 2026-10-19)

- Coverage: 100.00% (6724 stmts / 1922 branches)
- Tests: 6724 passed / 4 skipped
- Mypy: 35 files strict (via /opt/mypy-ci-venv, HA 2026.9.3)
- i18n parity: config.step 157/157/157 · options.step 281/281/281
- options.notifications_enabled 11/11/11 · options.notifications_dedup 19/19/19
- Sensors / Binary / Registry: 50 / 15 / 61 (+2 update.* = 63 by entity_id)
- Services / Repairs: 10 / 8
- Alerts (19): 17 BINARY_ALERT_MAP + 2 standalone (cop_low, stooklijn_advies) + status_summary
- DB: daikin_cycle_ml.db schema v15 · HA Store alerts schema v1
- Prod deployed: 14dadfe · Prod HA Core 2026.10.1 · Prod manifest 1.8.1
- QA scripts: scripts/bootstrap.sh, scripts/ci-local.sh, scripts/pre-push

## Hard rules (ACTIVE — never violate)

    R50   Never log tokens or credentials.
    R91   Never amend pushed commits.
    R327  Quoted heredocs for patches containing backticks.
    R328  Verify headRefOid after gh pr create — must match local HEAD.
    R329  No | head -N under set -euo pipefail — SIGPIPE kills the block.
    R347  After translation deploy: HA Core restart OR config-entry reload.
    R350  Recon-grep before any alert-pipeline change. --exclude-dir=__pycache__.
    R351  Every commit subject carries (#66). PR body line 1 = Refs #66.
          Tick boxes only AFTER merge.
    R352  Never combine cat >> and gh post in one heredoc. Split, or cat >.
    R353  getattr(self, name, default) in _build_alert_context /
          _alert_binary_states. Never direct attribute access.
    R355  Assert-guarded patch reports count != 1: run git status BEFORE retry.

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
- Pushing branch with any PR G batch uncommitted


## CI gates (must pass before every commit)

- Smoke:   pytest --no-cov tests/<file>
- Full:    pytest -q  (target: 4 skipped, 100.00% coverage)
- Ruff:    ruff check --no-fix --select E,F,W --ignore E501,E402,F401 <files>
- Mypy:    mypy --strict custom_components/


## Standard workflow

1. Read HANDOFF.md → run bootstrap.
2. Recon (R350 grep) — no writes.
3. Review plan with user. Wait for "go".
4. Implement, one commit per deliverable. Subject ends (#66).
5. Verify — full pytest + ruff + mypy.
6. Review — pre-merge rule check.
7. Plan-B live-fire — MANUAL: user triggers OptionsFlow Test-all.
8. Merge — MANUAL: user runs gh pr merge --squash, no --admin.
9. Tracker tick — MANUAL: gh issue edit 66 --body-file ...


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
- notify_service (e.g. notify.telegram_rachid)
- notify_emoji_enabled (default true)
- status_update_enabled (default false)
- status_update_interval_hours (default 24)
- retention_enabled / cycle_retention_days / alert_retention_days
- vacuum_enabled

## Daily operation

Sensors (50) — subset below; full list in live entity registry:
cycle_state, current_cycle, last_cycle, today, quality_today,
source_health, learned_thresholds, cop_vandaag, stooklijn_advies.
Binary sensors (15): compressor_running, defrost_active, buh_active,
dhw_active, heating_active, cooling_active, pendulum_hourly,
pendulum_daily, short_run, short_off, source_stale,
missing_attributes, setpoint_oscillating, dhw_pendulum, high_cycle_rate.

Services (10):
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

## Release procedure

For each release:
1. Bump VERSION in const.py and version in manifest.json (must match).
2. Update CHANGELOG.md with a new [x.y.z] - YYYY-MM-DD section.
3. Update ROADMAP.md: mark completed items, adjust next phase.
4. Update SOP.md if install/config/procedure changed.
5. Run full test suite:
   export PYTHONPATH=/workspace
   cd /workspace/daikin_cycle_ml
   pytest -q
   Gate: coverage >= 95%, 0 failures.
6. Optional: git tag if repo tracked.

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
