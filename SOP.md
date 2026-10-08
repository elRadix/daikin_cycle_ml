# SOP - Daikin Cycle ML

Standard Operating Procedure: install, configure, operate, troubleshoot, release.

## 1. Scope

Local-only Home Assistant integration that detects compressor cycles on
Daikin Altherma heat pumps, classifies pendulum behaviour, scores cycle
quality, and advises on configuration. No cloud. No setpoint writes.

Out of scope: cost tracking, HACS publication, supervised ML,
COP calculation (provided by external package).

## 2. Install

1. Copy custom_components/daikin_cycle_ml/ into the HA config tree.
2. Restart Home Assistant.
3. Settings -> Devices & Services -> Add Integration -> Daikin Cycle ML.
4. Complete the 8-step wizard:
   user -> model_custom -> attributes -> cycle -> pendulum -> quality
   -> notifications -> finalize.

## 3. Configuration

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

## 4. Daily operation

Sensors (9): cycle_state, current_cycle, last_cycle, today,
quality_today, source_health, learned_thresholds, cop_vandaag,
stooklijn_advies.
Binary sensors (15): compressor_running, defrost_active, buh_active,
dhw_active, heating_active, cooling_active, pendulum_hourly,
pendulum_daily, short_run, short_off, source_stale,
missing_attributes, setpoint_oscillating, dhw_pendulum, high_cycle_rate.

Services:
- daikin_cycle_ml.reset_counters
- daikin_cycle_ml.export_cycles
- daikin_cycle_ml.label_cycle
- daikin_cycle_ml.recompute_baseline
- daikin_cycle_ml.run_maintenance

Scheduled jobs (automatic):
- poll every 30s
- baseline save every 6h
- maintenance daily 03:00
- k-means Sunday 04:00
- status update every N hours (opt-in)

## 5. Troubleshooting

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

## 6. Release procedure

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

## 7. Known limitations (v0.2)

- No COP / cost (out of scope)
- No HACS publication (out of scope)
- All ML is unsupervised; no training labels
- Cluster sensors not exposed yet (12b)
- Adaptive thresholds not wired yet (12a)

## 8. Reference

- README.md - quick start
- DOCUMENTATION.md - full architecture + ML flow
- ROADMAP.md - phase tracking
- CHANGELOG.md - release history

## 9. Update log (append-only)

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


## 10. Run.py regels (R83-R92)

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

## 11. Correcties op eerdere notities

- README executable bit: was 100644 (correct). No chmod needed. Handoff note was wrong.
- Entity binary_sensor.daikin_cycle_ml_missing_attributes (not _attrs).
  Repair issue-id remains missing_attrs (internal identifier).
- Stooklijn advies states: verlaag_lwt_2c, verhoog_lwt_2c, behoud, unknown.
- Entity counts: 9 sensors + 15 binary sensors = 24 (not 26+16 or 29+19).
- Repairs (5): source_stale, missing_attrs, db_corrupt, notify_failed, migration_failed.
- Services (6): reset_counters, export_cycles, label_cycle, recompute_baseline, run_maintenance, send_test_notification.
- DB tables (7): cycles, features, alerts, daily_summary, cop_samples, model_state, sqlite_sequence.


### R96 (batch 52b6)

**pytest-cov fail_under valkuil.** `[tool.coverage.report] fail_under=95`
in pyproject.toml blokkeert pytest NIET. pytest-cov print
"FAIL Required test coverage of 95% not reached" maar returnt rc=0.

**Fix:** voeg `--cov-fail-under=95` expliciet toe aan pytest-args in P5:

    python3 -m pytest -q --no-header --cov-fail-under=95

Alternatief: CI-workflow die `coverage report --fail-under=95` draait
na pytest.

Zonder deze fix kunnen coverage-drops ongemerkt door glippen (batch 52b5:
94.99% gemerkt door handmatige inspectie).


### R102 (batch 52g) - performance-tooling verdict

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

## 12. Handoff + multi-repo regels (R133-R145)

Toegevoegd 2026-09-27 na HACS default store indiening (PR #11345).
Volledige context: zie HANDOFF_SOP.md.

| Regel | Inhoud |
|-------|--------|
| R133 | Handoff wanneer context ORANGE, YELLOW + mijlpaal, of RED verplicht |
| R134 | Handoff-versienummer = +1 major (v16.0 -> v17.0), nooit minor |
| R135 | Handoff is self-contained - verse chat moet alles kunnen terugvinden |
| R136 | Handoff markeert onbekende zaken als TE VERIFIEREN |
| R137 | Handoff markeert VERVALLEN regels expliciet, verwijdert ze niet |
| R138 | Handoff checkt eerst: git status, CI status, PR status, containers |
| R139 | Handoff-versie = volledige git-commit-hash + tag-referentie |
| R140 | Handoff genereren via chat, opslaan via heredoc (R90-veilig) |
| R141 | Twee repos: daikin_cycle_ml (dev) + default (HACS-fork). Nooit verwarren |
| R142 | Fork default: nooit naar branch pushen na PR-open (HACS-bot sluit PR) |
| R143 | Nieuwe HACS PR = nieuwe branch vanaf verse upstream/master |
| R144 | Fork-master syncen voor nieuwe PR: git reset --hard upstream/master + --force-with-lease |
| R145 | Fork git identity lokaal (--no-global), nooit --global in container |

### Gap-note: R93-R132 ontbreken in dit document

SOP.md bevat momenteel alleen R83-R92 (sectie 10) en R96, R102 (sectie 11).
Regels R93, R94, R95, R97-R101, R103-R132 leven alleen in handoff-chat-historie
(handoff v15.0-v17.0 DEEL 2.8).

Backfill naar SOP.md is een openstaande taak (niet docs-triviaal - vereist
per-regel recon + format-matching). Zie handoff v17.0 DEEL 15.1 #2.


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
