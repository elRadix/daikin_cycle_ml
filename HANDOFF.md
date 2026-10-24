# HANDOFF — Daikin Cycle ML

Agent-readable mirror of the current session handoff. The canonical
version lives in the maintainer's chat transcript.

NOTE ON FORMAT: code samples use 4-space indented blocks per R349.
Do not add triple-backtick fences when editing this file.

NOTE: DEEPSEEK.md is local-only, gitignored. Read from dev container if present.

---

## Version marker

    HANDOFF v96.0 — Daikin Cycle ML
    Generated: 2026-10-24T08:40Z (updated 2026-10-24T~10:30Z post-gate)
    Supersedes: v95.0 (2026-10-23T21:30Z)
    Status: main @ a3e87fa (v1.12.3). Working tree CLEAN.
            All 3 prods on v1.12.3, no regressions.
            24h gate PASSED at 2026-10-24T08:44:49Z (+13s).
            Cycle 150 baseline captured (dur=5262s, cop=3.24, 16 real samples).
            NO code changes since v1.12.3. 0 commits since a3e87fa.
            Amendment queue: 7 files in container /tmp, 192 lines.
            NEW session findings: #133 (cop_sample_count tick-count bug),
                                 #134 (dhw_detect_v2 never existed).
            Context 🔴 ~90% — fresh session mandatory at handoff author time.

---

## State summary

Base: main HEAD a3e87fa (v1.12.3, released 2026-10-22T18:24:17Z)
origin/main: a3e87fa (MATCH)
Tag v1.12.3: a3e87fa
All 3 prods: v1.12.3, WAL, v17 marker intact, v18 absent

Session deltas (since v95.0):
    - 0 code commits
    - 24h gate verified PASSED (2026-10-24T08:44:49Z)
    - Cycle 150 closed baseline captured
    - Amendment 7 scope clarified: 4 cycles fleet-wide (was 2 DHW-only)
    - New bug filed: #133 (cop_sample_count = duration_s/30, inflated 11x)
    - New bug filed: #134 (dhw_detect_v2.py never existed on prod 1)
    - ATTR_DHW_TANK_TEMP: Option A confirmed (add in v1.12.4)
    - cop_samples cadence documented: 300-330s (throttle + jitter)

---

## Session start protocol

Before any mutation, verify:

1. git status --porcelain (must be empty) + git rev-parse HEAD (must be a3e87fa)
2. All 3 prods running v1.12.3 (manifest check per prod)
3. Gate status via gate-check block (was PASSED at 08:44:49Z)
4. Container name = daikin_cycle_dev (NOT _ml_dev)
5. Amendment queue intact: docker exec daikin_cycle_dev ls /tmp/amend_*.md

If any check fails, STOP and investigate — do NOT proceed to code.

---

## Bootstrap

Dev container:
    Container name:  daikin_cycle_dev (python:3.14, --restart unless-stopped)
    Image workdir:   /workspace/daikin_cycle_ml
    Host mount:      /homeassistant/daikin_cycle_ml_dev -> /workspace/daikin_cycle_ml

Prod HA hosts:
    Prod 1 LAN:       root@192.168.1.237 -p 2222
    Prod 1 Tailscale: root@100.81.96.34 -p 2222
    Prod 2:           192.168.100.52/23 (console only, no SSH)
    Prod 3 LAN:       192.168.129.117/23 (console only)
    Prod 3 Tailscale: root@100.100.87.4:22

SSH entry (host shell, not container):
    ssh root@100.81.96.34 -p 2222

Container entry (from host):
    docker exec -i daikin_cycle_dev bash -lc 'cd /workspace/daikin_cycle_ml && git status --porcelain && git rev-parse HEAD'

Standard heredoc pattern (R371, R385):
    docker exec -i daikin_cycle_dev bash -lc 'bash -s' <<'UNIQUE_TAG'
    set -uo pipefail
    cd /workspace/daikin_cycle_ml
    commands with explicit RC gates
    UNIQUE_TAG

---

## Current work — v1.12.4 (DHW backfill migration)

Branch: feat/v1.12.4-dhw-backfill (at a3e87fa, ready to checkout)
Milestone: v1.12.4 (2 open: #116, #130)
Target: close #116 + #130 with 7 amendments + schema v18

Scope highlights (see full spec §5.4):
    - Schema v18: 5+ columns, marker-guarded idempotent migration
    - R445a-c: 3-shape classifier (relabel / split / tail)
    - R445d: 36 in-cycle unknowns (not 49, 47 out-of-cycle -> #126)
    - R445e: dynamic Carnot gate (0.55 x Carnot, not absolute >11)
    - R446:  synthesis of orphan DHW runs from samples
    - R446b: merge adjacent same-mode splits (gap<120s)
    - Amend 7: aggregate backfill (4 cycles fleet-wide: 1, 2, 64, 120)
    - R447: DELETE+rebuild cop_hourly (excludes artifacts)
    - R448: daily_summary rebuild (from corrected cycles)
    - R449: energy_acc rebuild DEFERRED (preserve HWM chain)

Execution order (CRITICAL, do not reorder):
    1. R445a-c   cycle-level mode fix
    2. R445d     sample-level unknown relabel (36 samples)
    3. R445e     sample-level artifact flag (dynamic Carnot)
    4. R446      synthesize orphan DHW runs
    5. R446b     merge adjacent same-mode splits
    6. Amend 7   aggregate backfill (4 cycles)
    7. R447      DELETE+rebuild cop_hourly
    8. R448      daily_summary rebuild
    -- R449 (energy_acc rebuild) DEFERRED --

Reasoning for order:
    - Mode fixes (R445) MUST precede R446/R446b (they read corrected modes)
    - Amend 7 MUST see clean samples (post-R445d/e) and merged cycles (post-R446b)
    - R447/R448 MUST see corrected cycles AND backfilled aggregates

---

### Deferred (not in v1.12.4)

    - energy_acc rebuild for affected days (R449) — preserve HWM chain
    - thermal.py rewrite (v1.12.5, #132)
    - MAX_CYCLE_DURATION_S change (v1.12.5, #120)
    - _resolve_cop_sample_mode fix (v1.12.5, #128)
    - Carnot gate at collection time (v1.13.0, #123)
    - features.v11 fix (v1.13.0, #129)
    - Alerts DB persistence (v1.13.0 backlog)

---

### Deferred to v1.12.5 batch

    #120  4h hybrid cycle detection (Tier 1/2/3)
    #121  Option B: MAX(ts) from DB on init
    #122  stability gate (settle-time after mode transition)
    #125  kmeans instrumentation (log async_run_kmeans callers)
    #126  47-population source fix (out-of-cycle unknowns)
    #127  RFI external Daikin methodology
    #128  3-line caller fix for _resolve_cop_sample_mode
    #131  split prevention (MODE_DEBOUNCE_S raise or 2-tick commit)
    #132  thermal.py rewrite (needs ATTR_DHW_TANK_TEMP, now Option A in v1.12.4)
    #133  NEW: cop_sample_count = duration_s/30 (tick count bug)

### Deferred to v1.13.0 batch

    #123  Carnot gate at collection time
    #124  heating artifact investigation
    #129  features.v11 fix + thermal recompute
    Alerts DB persistence
    Full features schema migration v0-v11

---

## §4.15a — retention fallback drift (v79.1 backlog)

Unchanged from v79.0. Refer to prior handoff.

---

## R350 recon (before any alert-pipeline edit)

Unchanged from v79.0. Before ANY change to the alert pipeline, verify:
    - ALERT_LABELS registry entry exists (R368)
    - _build_alert_context getattr guard (R353)
    - Test for alert context key resolution

---

## Live alert inventory (19 + status_summary)

19 alert types (see §19 for full matrix):
    pendulum_hourly, pendulum_daily, short_run, short_off, ml_anomaly,
    setpoint_osc, cop_low, stooklijn_advies, cop_degradation,
    defrost_excessive, buh_excessive, source_stale, missing_attributes,
    dhw_pendulum, high_cycle_rate, cop_vs_datasheet_low,
    db_retention_warning, kmeans_retrain_stale, energy_daily_anomaly
    + status_summary (6h scheduler)

DB alerts table: EMPTY in all 3 prods. DB persistence deferred to v1.13.0.

---

## Rules — see §2.8 (full R-rule table)

Current R-rule count: v96.0 introduces NO new R-rules.

Prior R-rules R50-R451 remain in effect. R452-R455 remain candidates.

RETIRED: R25-R82, R83-R92, R93-R132, R96, R102.

---

## §1 — Status & overview

### §1.1 Document status

    Field                    Value
    Doc version              v96.0
    Date                     2026-10-24T08:40Z (updated ~10:30Z post-gate)
    Supersedes               v95.0 (2026-10-23T21:30Z)
    Project version (stable) v1.12.3
    main HEAD                a3e87fa "v1.12.3: DHW compound-mode detection (#118)"
    origin/main              a3e87fa (MATCH)
    Working tree             CLEAN (verified 2026-10-24T~10:30Z)
    Tag v1.12.3              a3e87fa — published 2026-10-22T18:24:17Z
    Release latest           v1.12.3
    Epic #119                OPEN — 50-item checklist
    Milestones               v1.12.4 (2 open) · v1.12.5 (10 open incl #133) · v1.13.0 (3 open) · epic (1 open)
    Session deltas           No code. Gate PASSED. Cycle 150 baseline. Findings #133/#134.
    Tests @ main             7330 stmts / 2090 branches / 100.00%
    Mypy strict              37 files clean
    Ruff                     All checks passed
    CI @ main                HACS ✓ · Hassfest ✓ · Mypy ✓
    i18n parity              config 157/157/157 · options 281/281/281 · services 13/13/13 · issues 9/9/9
    Open PRs (dev)           0
    Open PRs (HACS)          0
    Open issues              #116, #119-#134 (17 open), + older #88, #97, #102, #22, #18
    Ruleset protect-main     id=24465625, 6 contexts, active
    Dev container            daikin_cycle_dev
    Context at handoff       🔴 ~90%
    24h gate start           2026-10-23T08:44:36Z
    24h gate end             2026-10-24T08:44:36Z — PASSED (verified 08:44:49Z)

### §1.2 Project description

See v92.0 §1.2 (unchanged).

### §1.3 Git/GitHub status

Recent commits on main (v1.12.3 included):
    a3e87fa  v1.12.3: DHW compound-mode detection (#118)     <- HEAD
    9e8727d  v1.12.2: DB data-integrity fixes + WAL (#115)
    b18294f  v1.12.1: fix #109 restart phantom short_off
    92e30b2  fix(coordinator): source gate phantom short_off (#109)

Branches (local):
    main                           a3e87fa  Base active
    feat/v1.12.4-dhw-backfill      a3e87fa  v1.12.4 phase
    feat/v1.12.5-settle-time-gate  a3e87fa  v1.12.5 phase
    feat/v1.13.0-carnot-gate       a3e87fa  v1.13.0 phase
    feat/v1.6.0-hvac-parity        a47414e  ⚠️ DO NOT TOUCH (stash c3a-tmp)

Stale branches deleted in prior session (v95.0): 5 total, all HTTP 404 verified.

### §1.4 Session actions (v96.0 session)

    Type                          Count  Items
    Code changes                  0      main @ a3e87fa frozen
    CI runs                       0      no commits
    Gate checks                   2      PASSED at 08:44:49Z (+13s)
    Baseline captures             1      cycle 150 + samples 2712-2720
    Amendment queue verification  1      7 files, 192 lines, intact
    New bugs filed                0      (deferred to Block 2 commit)
    New findings                  2      #133, #134 (log in next commit)
    Housekeeping                  0      none this session
    GitHub writes                 0      no posts yet
    Fabrications                  0      —

---

## §2 — Werkwijze / SOP

### §2.1 Gouden regel

run.py is RETIRED sinds v77.0. Actuele regel:

    Alles via docker exec -i daikin_cycle_dev bash -lc 'bash -s' <<'TAG' met
    set -euo pipefail (of set -uo pipefail + expliciete RC-gates), exit 1 op
    elke failure, en verify-mutate-verify patroon binnen dezelfde block.

Flow per stap:
    1. Recon (read-only)
    2. Plan (exact patch op basis van recon)
    3. Patch (atomair, anchor-count guards)
    4. Verify (AST + targeted test + full suite + ruff + mypy)
    5. Commit (tracker-nummer in subject — R351, --no-verify skip pre-commit)
    6. Push (pre-push hook = ci-local.sh, 4 gates)
    7. PR + CI + merge (gh pr CLI, PR_NUM guard — R408)
    8. Tag + release (idempotent, R407 version-at-HEAD guard)

### §2.2 SSH verbinding

Zie Bootstrap hierboven.

### §2.3 Containers

    Aspect          Dev (daikin_cycle_dev)         Prod HA
    Image           python:3.14                    HA Core 2026.10.2
    Workdir         /workspace/daikin_cycle_ml     /config/custom_components/daikin_cycle_ml
    Mount           /homeassistant/daikin_cycle_ml_dev -> workdir
                    /mnt/data/supervisor/homeassistant -> /config
    Python          3.14.8                         3.14.x
    pytest          9.0.3                          —
    mypy            2.4.0 (/opt/mypy-ci-venv)      —
    gh CLI          v2.97.0 at /usr/local/bin/gh (NOT in image — R405)
    git             2.47.3                         2.47.3
    git identity    elRadix / elRadix@users.noreply.github.com

Missing binaries: jq NOT installed — use python3 -c.

Container name: daikin_cycle_dev (NOT daikin_cycle_ml_dev — repeated bug).

### §2.4 Standaard flow (docker exec heredoc)

    Klein (single command)
    docker exec -i daikin_cycle_dev bash -lc 'cd /workspace/daikin_cycle_ml && git status --porcelain && git rev-parse HEAD'

    Multi-command
    docker exec -i daikin_cycle_dev bash -lc 'bash -s' <<'UNIQUE_TAG'
    set -euo pipefail
    cd /workspace/daikin_cycle_ml
    commands
    UNIQUE_TAG

Regels:
    - <<'TAG' quoted als er backticks in Python string literals (R418)
    - < /dev/null achter stdin-lezende commando's (R374)
    - Geen set -euo pipefail als er grep in de block zit (R371) — gebruik set -uo pipefail + RC gates
    - Elke heredoc-chunk ≤1.5 KB (R385)
    - Markdown append pattern (R429): ≤1.6 KB per block, zero backticks

### §2.5 Exit codes

scripts/ci-local.sh exit codes: 0 = alle 4 gates pass (pytest 100% / ruff / mypy strict / markdown) · 1 = een gate faalde.

### §2.6 Block-structuur patronen

    A — Recon: State → grep → print. No mutation.
    B — Patch: Preflight guards → patch per hunk → verify → full suite + ruff + mypy.
    C — Release: Stage 0 state guard → 1 patch → 2 targeted → 3 ruff+mypy → 4 full suite (~155s) → 5 commit.
    D — Markdown: cat > /tmp/file.md then cat >> per ≤1.6KB chunk, zero backticks.

### §2.7 Host-side scripts patroon

    Direct op HA host ~ #
    sqlite3 /config/.storage/daikin_cycle_ml_<entry>.db "SELECT ..."
    ha core info | grep -E "^(version|state):"
    curl -s -H "Authorization: Bearer $SUPERVISOR_TOKEN" http://supervisor/core/api/states
    docker cp daikin_cycle_dev:/workspace/daikin_cycle_ml/README.md /tmp/

### §2.8 R-regels — canonieke bron = AGENTS.md

Cluster A — ACTIVE (never violate): R50, R91, R133-R145, R327-R329, R347, R350, R351, R352, R353, R355, R369, R370.

Cluster B — CANDIDATES: R336, R337, R345, R346, R354, R356, R357, R358, R365, R366, R368, R371-R403, R404-R425, R426-R431, R432-R440, R441-R449, R450-R451.

RETIRED: R25-R82, R83-R92, R93-R132, R96, R102.

v96.0 introduces NO new R-rules. Proposed R452-R455 remain in ticket descriptions.

### §2.9 SSH Web Terminal lessen

Zie R-rule table (symptoom → regel mapping). Key clusters:
    - Heredoc: R385, R327, R374, R384, R389, R390, R418
    - gh CLI: R369, R391, R405, R408, R431, R437, R450
    - Patches: R345, R355, R370, R375, R395, R429, R430
    - Daikin physics: R441-R449
    - Container: daikin_cycle_dev NOT _ml_dev

---

## §3 — Release workflow (gh CLI)

### gh install in container (if recreated — R405)

    apt-get update -qq
    apt-get install curl ca-certificates
    curl gh_2.97.0_linux_amd64.tar.gz | tar -xz
    mv gh /usr/local/bin/
    gh --version && gh auth status

### Authenticate

    gh auth login --git-protocol ssh

Current state: elRadix, active. SSH key cycledev canoniek.

### Tag creation (R407 3-layer guard)

    L1: manifest at HEAD == TAGV
    Create annotated tag
    L2: deref == HEAD
    L3: version at tagged commit == TAGV
    Push (pre-push runs ci-local.sh ~155s)
    Fetch, verify remote deref

### Release notes (R429 append pattern)

Content = user-facing. Publish with --latest (R386; isLatest JSON broken in gh 2.54/2.97).

    gh release create "$TAGREF" --verify-tag --latest --title "..." --notes-file /tmp/notes.md

### Verify (R450)

    gh release view v1.12.4 --json tagName,isDraft,isPrerelease,publishedAt,targetCommitish
    gh release list (parse "Latest" column)
    gh api repos/elRadix/daikin_cycle_ml/releases/latest --jq .tag_name

---

## §4 — Architectuur

High-level v1.12.3 (unchanged):

    ESPAltherma (sensor.althermasensors, 105-186 attrs, v1 OR v2 label set)
      → engine/attribute_reader.py → read() → build_compat_view() → normalize
      → coordinator.py (DataUpdateCoordinator[DataSnapshot])
          30s: snapshot + missing_required gate
    _tick_buh_and_defrost + _tick_energy (+ _energy_hwm sync)
    _maybe_collect_cop_sample (300s throttle, cadence 300-330s observed)
    _refresh_cop_today / _maybe_refresh_stooklijn
    _maybe_refresh_cop_hourly (300s throttle, cache only)
    _maybe_refresh_cop_degradation / _maybe_refresh_spf
          6h: _async_baseline_save_callback → _maybe_rollup_cop_hourly
              (writes cop_hourly — ONLY caller)
          1h: _async_dispatch_alerts → _refresh_7d_rollups → alerts
          04:00 local Sun: kmeans refresh
          04:00 local daily: stooklijn hook
          03:00 local: maintenance retention
          6h: status_summary notification
          Shutdown: _async_handle_shutdown → _async_flush_accumulators
      → storage/db (SQLite v16 + WAL + v17 data migration)
      · engines · notification_engine · status_report
      → sensor.py (50) + binary_sensor.py (15) + services (13) + repairs (9) + update.* (2)

Migration chain _async_setup_database (v1.12.3):
    1. async_migrate_legacy_db(hass, entry)
    2. db.async_initialize() (schema.sql + v16 ALTER + WAL pragma)
    3-7. v11→v15 chain
    8. async_migrate_to_v17() (data migration)
    9. v1.12.4: async_migrate_to_v18() — after v17 (R438), uses 8 amendments

---

## §5 — Database

### §5.1 Locatie

    Field                Value
    Pad (v1.10.0+)       /config/.storage/daikin_cycle_ml_<entry_id>.db (per-entry)
    Pad (v1.9.2 earlier) /config/.storage/daikin_cycle_ml.db (legacy shared)
    Backup path          /config/.daikin_backups/daikin_cycle_ml.db.backup-<ts>
    Marker file          /config/.storage/.daikin_cycle_ml_v1100_migrated
    Schema source        storage/schema.sql
    Driver               aiosqlite (WAL since v1.12.2)
    journal_mode         wal, synchronous=NORMAL, busy_timeout=5000
    Schema versie        v16 + v17 data migration applied (v18 planned v1.12.4)

Prod DB paths:
    Prod 1: 01M57X8B5FM4PVFEN8JV9ZKH5V
    Prod 2: 01M3HW3TT236JS26329V16D76Y
    Prod 3: 01M3HTYPK4K06Z519DJ47PF3J6

### §5.2 Tabellen (compact)

    cop_samples (PK id)
        id, ts REAL NOT NULL, cop REAL, lwt REAL, outdoor REAL, flow_lmin REAL,
        power_stable INTEGER, mode TEXT, source TEXT
        ⚠️ Minimal schema. NO power_w, NO data_quality. power_stable=1 by construction.
        ⚠️ Cadence: 300-330s (300s throttle + 30s poll jitter). NOT 30s.
        v18 adds: mode_original TEXT, is_transition_artifact INTEGER DEFAULT 0

    cycles (PK id, UNIQUE start_ts)
        id, start_ts, end_ts, duration_s, mode, dT_max, dT_avg, rps_max, rps_avg,
        outdoor_temp, buh_used, defrost_used, quality_score, label, cluster_id,
        cop_avg, cop_sample_count, cop_sample_stdev, cop_confidence, thermal_kw_avg,
        is_transient
        ⚠️ cop_sample_count = duration_s / 30 (TICK COUNT, not DB COUNT — see #133)
        ⚠️ cop_confidence derived from inflated count -> inflated confidence
        MAX_CYCLE_DURATION_S=14400 hard cap forces close
        v18 adds: mode_original, parent_cycle_id, is_dhw_tail, is_reconstructed

    features (PK cycle_id)
        cycle_id, vector_json TEXT (12-dim), v11 REAL (always 0.0 — never populated, #129)
        1:1 with cycles enforced

    cop_hourly (PK (ts_hour, mode))
        ts_hour INTEGER (HOURS-since-epoch, NOT seconds)
        n_samples, cop_mean, cop_p10, cop_p50, cop_p90, cop_std,
        lwt_mean, outdoor_mean, outdoor_min, outdoor_max, flow_mean, updated_ts
        ⚠️ ts_hour = int(unix_seconds // 3600). DATE(ts_hour, 'unixepoch') is WRONG.
        ⚠️ Only written by 6h _async_baseline_save_callback. Rollup does NOT UPDATE (#130).

    daily_summary (PK (day, mode))
        day TEXT, mode, cycles, total_duration_s, duration_min, duration_max,
        quality_sum, dt_max_sum, rps_sum, buh_count, defrost_count, updated_ts

    alerts (PK id, UNIQUE(ts, alert_type))
        id, ts, alert_type, severity, message, aggregated_count
        ⚠️ EMPTY in all 3 prods — never wired (v1.13.0)

    model_state (PK key)
        key, value_json, updated_ts REAL
        ~45 rows typical: energy_acc.<day>, runtime_acc.<day>, kmeans_state,
        baseline_state, adaptive_thresholds, last_maintenance_ts, spf_state,
        thermal_daily_baseline, cycle_detector_state, data_migration_v1_12_2,
        data_migration_v1_12_4 (planned)

### §5.3 Retention

    Table          Default         Configurable
    cycles         90d (prod 365)  cycle_retention_days
    features       CASCADE         —
    alerts         90d             alert_retention_days
    cop_samples    365d fixed      —
    cop_hourly     365d fixed      —
    daily_summary  ∞               —
    model_state    400d (energy)   model_state_retention_days
                   ∞ (other)

Dagelijks 03:00 local via _run_maintenance.

### §5.4 Migratie-paden

Current (v1.12.3): v17 data-only complete + marker.

⚠️ v17 issue (#129): features.vector_json[11] is 0.0 for all cycles →
    v17 backfill wrote 0.0 to cycles.thermal_kw_avg. Marker claims
    thermal_filled: 116 but values are zero.

v18 (planned v1.12.4) — 8 amendments in strict order:

    1. R445a-c   (from #116): 3-shape classifier on cycles
    relabel any unknown in-cycle sample -> cycle mode
    3-shape on cycles: pure (relabel), mixed 0.30-0.99 (split), tail 0.01-0.29 (flag)
    2. R445d     in-cycle unknowns relabel (36 samples, NOT 49 — 47 out-of-cycle #126)
    3. R445e     dynamic Carnot gate (0.55 x Carnot, not absolute >11)
    division guard: lwt<=outdoor -> unconditional flag
    Live evidence: sample 2712, Carnot=13.76, ratio=1.198 >> 0.55
    4. R446      synthesize orphan DHW runs (gap<=15min, run>=15min)
                 ⚠️ Compute thermal from SAMPLES, not features.vector_json[11] (#129)
                 Formula: flow_lmin * (LWT - DHW_tank_R5T) * 4.18 / 60
    5. R446b     merge adjacent same-mode cycles if:
    consecutive, gap <120s (2x MODE_DEBOUNCE_S)
    both is_transient=0, both is_reconstructed=0 or mixed
    Keep prev.id, prev.end_ts=next.end_ts, is_reconstructed=1
    DELETE next row + features
    Prod 1 evidence: 8 split pairs (2/3, 7/8, 25/26, 36/37, 66/67, 69/70, 70/71, 71/72)
    Worst: 4-way split (rows 69-72)
    6. Amend 7   aggregate backfill FLEET-WIDE self-gating (NOT DHW-only):
    For cycles WHERE cop_sample_count IS NULL or 0
                   AND COUNT(*) in window >= 1
    Recompute cop_avg from samples (cop IS NOT NULL)
    Set cop_sample_count = COUNT(*) from samples
    Skip if 0 valid samples
    ⚠️ MUST use SELECT COUNT(*) FROM cop_samples, NOT duration_s/30
    Prod 1 fleet: 4 cycles (ids 1, 2, 64, 120)
    id 1:  DHW,     1650s,  3 samples
    id 2:  DHW,      361s,  1 sample
    id 64: heating, 7460s, 17 samples  <- NEW this session
    id 120:heating, 6658s, 22 samples  <- NEW this session
    Marker: cop_aggregates_backfilled = 4
    7. R447      DELETE+rebuild cop_hourly buckets (NOT INSERT OR IGNORE)
    Otherwise partial-hour rows persist (#130)
    Prod 1 evidence: hour 13 has n=6 stored vs n=11 actual
    ⚠️ n_samples MUST be COUNT(*) from cop_samples
    Exclude is_transition_artifact=1 samples
    8. R448      daily_summary rebuild from corrected cycles
    ⚠️ Rebuild AFTER R446b merge (so day totals reflect merged cycles)

DEFERRED: R449 (energy_acc rebuild) — preserve HWM chain.

Marker data_migration_v1_12_4 extended counts:
    shape_a_relabelled, shape_b_split, shape_c_tail_marked,
    unknown_in_dhw_fixed, artifacts_flagged, cycles_synthesized,
    splits_merged, cop_aggregates_backfilled, hours_rebuilt,
    days_rebuilt, energy_acc_rebuilt: false

---

## §6 — Engines

All engine modules UNCHANGED since v95.0.

### engine/thermal.py — KNOWN BUGS (#132)

    - dt_from_attrs (line 30-36) uses ATTR_INLET_WATER_R4T for BOTH modes (wrong cold side for DHW)
    - compute_thermal_power_live (line 46-63) cascade: power_w * cop PRIMARY, flow * dt FALLBACK
    - When COP polluted (e.g., 19.5 transition), thermal = power * 19.5 = massively inflated
    - Signature: (*, power_w, cop, flow_lmin, dt_k, rps) — keyword-only
    - v1.12.5 rewrite: (mode, flow_lmin, lwt, attrs) -> float|None
    - 3 call sites: sensor.py:212, sensor.py:230, coordinator.py:1583
    - 9 test files affected. 200-300 lines + 20 tests estimated
    - v1.12.4 does NOT touch thermal.py

### engine/cycle_detector.py

    - State untouched. MAX_CYCLE_DURATION_S=14400
    - _pump_is_off(value) (line 95) handles False/'OFF'/'FALSE'/'NO'/''. None->False
    - update() fall-through close requires on=False
    - _process_new_cycle does NOT touch cop_samples
    - ⚠️ NO _compressor_hz_std_ratio / _lwt_slope / is_thermodynamically_stable
      (must build for v1.12.5 stability gate)
    - ⚠️ cop_sample_count incremented per-tick (likely root of #133)

### engine/physics.py — DOES NOT EXIST

    Must be created in v1.12.5 for get_physical_cop_ceiling(mode, lwt, outdoor)

### const.py delta

    ATTR_INLET_WATER_R4T = "Inlet water temp.(R4T)" @ line 142 (exists)
    ATTR_OPERATION_MODE @ 137, ATTR_IU_OPERATION_MODE @ 138, ATTR_3WAY_VALVE @ 139
    UPDATE_INTERVAL_SECONDS = 30 @ line 9 (code-verified)

    ⚠️ ATTR_DHW_TANK_TEMP DOES NOT EXIST — MUST ADD in v1.12.4 (Option A confirmed)
    ⚠️ ATTR_DHW_COIL_RETURN DOES NOT EXIST — add in v1.12.5 (#132 scope)

    Verbatim strings (R4T/R5T decoys exist on prod 1 only):
        ATTR_INLET_WATER_R4T = "Inlet water temp.(R4T)"     # correct water-side
        ATTR_DHW_TANK_TEMP   = "DHW tank temp. (R5T)"       # correct, note space before paren
    DECOYS (do NOT add as constants):
        "Heat exchanger mid-temp.(R5T)"   — refrigerant side, prod 1 only
        "O/U Heat Exch. Temp.(R4T)"       — refrigerant side, prod 1 only
    NEVER substring-match on R4T or R5T for physics references.

### Coordinator (verified)

    - _maybe_collect_cop_sample at line 2339. Caller at 1090 (inside _async_update_data)
    - _last_cop_sample_ts: float = 0.0 at line 491. Check 2343, update 2376. Never persisted (#121)
    - power_stable gate at 2361, write True at 2370
    - _resolve_cop_sample_mode at 2306 — 3-step ladder (data.mode → direct I/U → classify_mode)
      DOES NOT consult detector.state (#128)
    - deque imported at line 8. _setpoint_history at 473
    - DaikinCycleMLCoordinator class at line 383. Single instantiation __init__.py:185

### ml/ modules — unchanged

    adaptive_thresholds.run_min.heating contains 27+ learned values at 240min
    (14400s/60 = contaminated by 4h cap — F13 in #120)

---

## §7 — Config flow

UNCHANGED since v95.0. 13 setup steps, 66 options keys + 3 data keys.
Reconfigure: basic / full (preserving data).

---

## §8 — Entities

UNCHANGED since v95.0. 50 sensors, 15 binary sensors, 2 update entities.

    current_cycle state ∈ {heating, dhw, idle} — verified live = 'dhw' compound
    duty_cycle_today prod 1 = 96.02% (post-DHW), prod 2 = 36.5%
    short_run = off, short_off = off (all clean)

    hp_specs bundled datasheet (real k factors):
        A7/W35 COP=4.92 k=0.447
        A2/W35 COP=4.08 k=0.437
        A-7/W35 COP=3.04 k=0.414
        A-2/W45 COP=2.36 k=0.349
        A7/W55 COP=2.94 k=0.430
        A-7/W55 COP=2.05 k=0.387
    Model: epra12eav3 (prod 1), epra08eav3 (prod 2)

---

## §9 — Services

UNCHANGED since v95.0. 13 services.

---

## §10 — Diagnostics + repairs

UNCHANGED since v95.0. 9 repairs (all is_fixable=False).

---

## §11 — Scheduler

UNCHANGED since v95.0.

    Per-prod 6h timer bases:
        Prod 1: ~19:29:53Z (01:29/07:29/13:29/19:29)
        Prod 2: ~04:57:30Z (04:57/10:57/16:57/22:57)
        Prod 3: ~18:45:00Z (00:45/06:45/12:45/18:45)

    kmeans drift: prod 1 last_ok_ts = 2026-10-19T07:42:01Z (Monday, not Sunday 04:00)
    #125 status: code verified correct, instrumentation needed (v1.12.5)

---

## §12 — Translations

UNCHANGED since v95.0.

    config.step 157/157/157 · options.step 281/281/281
    services 13/13/13 · issues 9/9/9
    R401: no <word>, use [word]

---

## §13 — Testing

UNCHANGED since v95.0.

    Python 3.14.8, pytest 9.0.3, pytest-cov 7.1.0, pytest-asyncio 1.4.0,
    pytest-homeassistant-custom-component 0.13.373, pytest-timeout 2.4.0,
    hypothesis 6.170.1, syrupy 6.1.1, ruff 0.17.1, mypy 2.4.0 (HA 2026.9.3)

    TOTAL: 7330 stmts / 2090 branches / 100.00%. ~3246 tests.

    Active xfail (from v1.11.0, tracked #97):
        test_29_scenarios.py::test_scenario_cycles_rollup_math
        test_c5_sensors.py::test_duty_cycle_computes_pct
        test_cop_sensors.py::test_refresh_cop_today_valid

    Warning status: 0 warnings.

    9 test files affected by thermal rewrite (v1.12.5 #132):
        test_feat2_thermal_power_live.py, test_v1120_transient_classification.py,
        test_v1122_db_fixes.py, test_v1120_db_first_cycle.py, test_v161_energy_guard.py,
        test_31b_thermal_kw.py, test_v1120_schema_v16.py, test_audit_boundary_gaps.py,
        test_47_status_report_edges.py

---

## §14 — Changelog

### v1.12.3 (2026-10-22, SHIPPED)

DHW compound-mode detection (#116 forward half). Full text in v92.0 §14.

### v1.12.4 (planned ≥2026-10-24, gate PASSED)

    Added:
    - Schema v18 with 7 columns:
    cop_samples: mode_original, is_transition_artifact
    cycles: mode_original, parent_cycle_id, is_dhw_tail, is_reconstructed
    - async_migrate_to_v18 marker-guarded idempotent
    - R444 per-install flow threshold
    - R445a-c 3-shape classifier
    - R445d in-cycle unknown relabel (36 samples, fleet)
    - R445e dynamic Carnot gate (0.55 x Carnot)
    - R446 synthesis of orphan DHW cycles from samples
    - R446b merge of adjacent same-mode splits
    - Amend 7 fleet-wide aggregate backfill (4 cycles on prod 1)
    - ATTR_DHW_TANK_TEMP constant added (verbatim R5T water-side key)

    Changed:
    - Migration marker extended counts (splits_merged, cop_aggregates_backfilled, ...)
    - R447 DELETE+rebuild cop_hourly (NOT INSERT OR IGNORE)
    - R446 thermal from samples (bypass features.v11 = 0.0 bug)

    Fixed:
    - Historical DHW samples reclassified
    - Unknown-in-DHW samples relabelled
    - COP artifacts flagged by dynamic Carnot
    - Orphan cycles synthesized
    - Split cycles merged
    - cop_hourly rebuilt
    - daily_summary rebuilt
    - NULL-aggregate cycles backfilled (4 cycles, fleet)
    - Baselines retrained once

    Rollback: mode_original restore + delete split/synth children + clear marker.
    Backfilled aggs NOT rolled back (represent real measurement).

    Known limitations:
    - energy_acc not rebuilt (v1.12.5 R449 deferred)
    - post-migration dhw_detect_v2 still FAIL for transition-artifact samples
      until v1.12.5 stability gate
    - cop_sample_count still inflated for tick-count cycles (fix v1.12.5 #133)

### v1.12.5 (planned) — expanded scope

    #120 hybrid (Tier1/2/3)
    #121 Option B fix
    #122 stability gate
    #125 instrumentation
    #126 source fix (47 out-of-cycle unknowns)
    #128 3-line caller fix
    #131 split prevention
    #132 thermal rewrite (200-300 lines)
    #133 cop_sample_count = duration_s/30 fix (NEW)
    #134 dhw_detect_v2.py add to scripts/ (NEW, low priority)

### v1.13.0 (planned)

    #123 Carnot gate
    #124 heating artifacts
    #129 features rewrite
    alerts DB

---

## §15 — Task list (open)

### §15.1 Direct tasks (pre-gate CLOSED in v95.0)

    #3  Clean /tmp artifacts            CLOSED (40 deleted, 96 remain)
    #4  Delete 5 stale remote branches  CLOSED (all HTTP 404)
    #5  Close #109 formally             CLOSED (already closed, comment added)
    #8  R4T/R5T verify prod 2           CLOSED (all keys present)
    #9  R4T/R5T verify prod 3           CLOSED (all keys present)
    #10 UPDATE_INTERVAL_SECONDS          CLOSED (30 @ const.py:9)

Remaining optional (P3, deferred):
    #6  Fix 3 flaky tests (#97) — 2h, dedicated session
    #7  Token scope to repo, read:org (#88) — 15 min

### §15.2 Verify tasks (waiting on condition)

    #1  Gate PASSED confirmation            CLOSED 2026-10-24T08:44:49Z
    #2  DHW cycle 150 closed baseline       CLOSED (captured this session)
    #3  Next DHW reheat on prod 2           Weather-dependent
    #4  WAL stability                       Ongoing (0 on all 3)
    #5  kmeans_state update next Sunday     TBD 2026-10-26 04:00 local
    #6  #127 external Daikin response       TBD
    #7  Prod 3 anomaly MAX=78059 recheck    If recurs

### §15.3 Release tasks — v1.12.4 (gate PASSED, ready)

    #1  Verify gate PASSED (rerun)                ✅ DONE 08:44:49Z
    #2  Capture DHW cycle 150 closed baseline     ✅ DONE (dur=5262s, cop=3.24)
    #3  Read #116 (6 comments) + #130 + #119      ✅ DONE (this session)
    #4  git checkout feat/v1.12.4-dhw-backfill    PENDING
    #5  Update HANDOFF.md -> v96.0                PENDING (this is it)
    #6  Apply schema v18 + async_migrate_to_v18   PENDING (8 amendments)
    #7  Write 20+ tests with --timeout=120        PENDING (R435)
    #8  4-gate verify -> commit -> PR -> merge    PENDING
    #9  Tag v1.12.4 + release --latest            PENDING
    #10 Deploy prod 3 -> prod 1 -> prod 2         PENDING
    #11 Close v1.12.4 milestone (2 tickets)       PENDING

### §15.4 Issue priority order

    1. #116 (v1.12.4) — DHW historical migration with 8 amendments
    2. #130 (v1.12.4) — cop_hourly DELETE+rebuild (pairs with #116, R447)
    3. #120 (v1.12.5) — 4h hybrid
    4. #121 (v1.12.5) — Option B fix
    5. #128 (v1.12.5) — 3-line caller fix
    6. #131 (v1.12.5) — Split prevention (8 pairs prod 1, 3 pairs prod 2)
    7. #132 (v1.12.5) — Thermal rewrite (R4T/R5T verified, unblocked)
    8. #122 (v1.12.5) — Stability gate (UPDATE_INTERVAL_SECONDS=30 confirmed)
    9. #125 (v1.12.5) — kmeans instrumentation
    10. #126 (v1.12.5) — Source fix (47 out-of-cycle unknowns)
    11. #127 (v1.12.5) — RFI external response pending
    12. #133 (v1.12.5) — cop_sample_count tick-count fix (NEW this session)
    13. #134 (v1.12.5) — dhw_detect_v2.py add to scripts/ (NEW this session)
    14. #123, #124, #129 (v1.13.0) — Carnot gate + heating artifacts + features rewrite

### §15.5 Epic/milestone structure

    Epic #119 wraps all open work. 50-item checklist.
    Milestone v1.12.4: #116, #130 (2 open)
    Milestone v1.12.5: #120, #121, #122, #125, #126, #127, #128, #131, #132, #133 (10 open)
    Milestone v1.13.0: #123, #124, #129 (3 open)

---

## §16 — Backlog

### §16.1 Wired + wizard

Alle wizard-velden gewired.

### §16.2 Tunable (P3)

    I3 datasheet_missing · I4 service_due · I5 quality_degradation

### §16.3 Multi-channel

    Alerts store per-entry split · Alerts DB persistence (v1.13.0)
    feat/v1.6.0-hvac-parity cleanup (⚠️ DO NOT TOUCH — stash c3a-tmp)

### §16.4 Feature-vector (v1.13.0)

    IsolationForest · Per-season baselines · weather-normalized energy
    time-of-day buckets · per-dimension weighting · Full features schema migration
    add fan_step, 4way_valve, target_cond_temp · v11 never populated — recompute from samples

### §16.5 Active bugs (per epic #119)

    #116, #120, #121, #122, #123, #124, #125, #126, #127, #128, #129,
    #130, #131, #132, #133 (NEW), #134 (NEW)

### §16.6 Deferred

    Short defrost artifacts (0-60s) — v1.13.0
    cycle_detector_state persists only on state transition — cosmetic
    #102 re-add manifest categories
    #97 flaky test real fix (2h)
    #88 token scope
    2 dangling prod config refs
    5 docs WARNs
    thermal_kw_avg=0.0 for pre-v1.12.0 cycles (v1.13.0 #129)
    Prod 3 anomaly MAX=78059 non-reproducible
    7 sub-300s DHW cycles (R454 territory, document only)
    8 split DHW pairs on prod 1 (R446b mitigates retroactively)
    4 NULL-aggregate cycles (Amend 7 fixes fleet-wide in v1.12.4)
    #133 cop_sample_count tick-count bug (v1.12.5)
    #134 dhw_detect_v2.py add to scripts/ (v1.12.5)

### §16.7 Security

    Token scope over-scoped (#88) — 15 min reduction to repo, read:org

### §16.8 Docs (v1.12.4 PR additions)

    - Diagnostics per-section field names ⚠️ TE VERIFIEREN
    - ts_hour hours-since-epoch contract to DATABASE.md
    - thermal_kw_avg=0.0 clarification
    - cop_samples cadence: 300-330s (300s throttle + 30s poll jitter)
    - is_transition_artifact=1 excluded from COP aggregations
    - Cycle synthesis semantics (R446)
    - R446b merge logic (rollback requires un-merging)
    - power_stable = measurement flag not physics gate
    - R445e dynamic Carnot threshold
    - #131 split cycle prevention
    - Amend 7 aggregate backfill
    - Two R5T keys + two R4T keys decoy warning
    - cop_sample_count = duration_s/30 tick count (NEW — #133)

### §16.9 Housekeeping

    - /tmp/*.md on container: 96 remain (safe to leave)
    - /tmp/amend_*.md: 7 files, KEEP until PR merges
    - /tmp/dhw_detect.py (v1) on prod 1: KEEP (last working script)
    - /tmp/dhw_detect_v2.py: ⚠️ NEVER EXISTED (handoff v95.0 was wrong — #134)
    - /config/scripts/db_check.py, db_verify.py, db_verify_prod3.py: KEEP
    - scripts/dhw_detect_v2.py: add in v1.12.4 PR (#134)
    - HANDOFF.md: full rewrite this session (was v79.0 mirror, now v96.0 canonical)

---

## §17 — Next chat start here

### §17.1 Context estimate

🔴 Context ~90% at handoff author. Fresh session mandatory.

### §17.2 First message template (paste full handoff v96.0 above, then:)

    Fresh session. main = a3e87fa (v1.12.3, released 2026-10-22T18:24:17Z).
    Working tree CLEAN. All 3 prods on v1.12.3.

    CONFIRMED STATE (from v96.0 session):
    - 24h gate PASSED 2026-10-24T08:44:49Z (+13s)
    - Cycle 150 closed baseline captured: dur=5262s, cop_avg=3.24, 16 real samples
    - Sample 2712 pre-fix artifact confirmed: cop=16.486, flow=26.7, Carnot ratio=1.198
    - Amendment queue: 7 files / 192 lines in container /tmp
    - Amendment 7 scope = 4 cycles fleet-wide (ids 1, 2, 64, 120)
    - ATTR_DHW_TANK_TEMP = Option A (add in v1.12.4)
    - New bugs: #133 (cop_sample_count tick-count), #134 (dhw_detect_v2 never existed)
    - cop_samples cadence: 300-330s (not 30s)
    - Execution order: R445a-c -> R445d -> R445e -> R446 -> R446b -> Amend 7 -> R447 -> R448

    FIRST ACTIONS (in order):
    1. Verify gate + prod state (read-only, 2 min)
    2. git checkout feat/v1.12.4-dhw-backfill
    3. Apply HANDOFF.md v96.0 (this file)
    4. Log #133 + #134 as new issues
    5. Implement schema v18 + async_migrate_to_v18
    6. 20+ tests with --timeout=120
    7. 4-gate verify -> commit -> PR -> merge -> tag v1.12.4 -> release --latest
    8. Deploy prod 3 -> prod 1 -> prod 2
    9. Close v1.12.4 milestone

    WORKFLOW: chunks <=1.5KB (R385), container daikin_cycle_dev (NOT _ml_dev),
    amend queue in /tmp (do NOT delete), 4-file version bump (R404),
    gh at /usr/local/bin/gh v2.97 (R405), R407 3-layer tag guard,
    R408 PR_NUM guard, R450 use gh api .../releases/latest.

    DO NOT: touch thermal.py (v1.12.5), change MAX_CYCLE_DURATION_S (v1.12.5),
    fix _resolve_cop_sample_mode (v1.12.5), trust cop_sample_count as DB count (#133),
    substring-match R4T/R5T, assume dhw_detect_v2.py exists.

### §17.3 First tasks (bootstrap sequence)

    1. Verify gate (read-only, 30s)
    2. Verify all 3 prods manifest 1.12.3
    3. Verify main @ a3e87fa, tree clean
    4. git checkout feat/v1.12.4-dhw-backfill
    5. HANDOFF.md v96.0 commit (if not already done)
    6. Log #133 + #134 issues via gh
    7. Implement v1.12.4 schema v18 + 8 amendments
    8. 20+ tests --timeout=120
    9. 4-gate verify -> commit -> PR -> merge -> tag -> release
    10. Deploy prod 3 -> prod 1 -> prod 2
    11. Close v1.12.4 milestone

### §17.4 v1.12.4 implementation checklist (8 amendments detail)

Zie §5.4 hierboven voor volledige order.

Amendment 1-3 (R445a-c) — 3-shape classifier on cycles
Amendment 4 (R445d) — in-cycle unknown relabel, 36 samples fleet
Amendment 5 (R445e) — dynamic Carnot (0.55x), division guard
Amendment 6 (R446) — synthesize orphan DHW runs, thermal from samples (formula: flow*(LWT-R5T_tank)*4.18/60)
Amendment 7 (R446b) — merge adjacent same-mode splits, gap<120s
Amendment 8 (Amend 7) — fleet-wide aggregate backfill, 4 cycles (1, 2, 64, 120)
Amendment 9 (R447) — DELETE+rebuild cop_hourly, exclude artifacts
Amendment 10 (R448) — daily_summary rebuild
DEFERRED (R449) — energy_acc rebuild

### §17.5 Amendment queue — 7 files in container /tmp

    1. amend_132_body.md              77 lines  -> post to #132 after context read (R437)
    2. amend_handoff_20_2.md          24 lines  -> ABSORBED into v96.0 (do not apply separately)
    3. amend_handoff_15_1.md          15 lines  -> ABSORBED into v96.0 (do not apply separately)
    4. amend_122_noop.md               7 lines  -> audit trail only (do NOT post)
    5. amend_132_const_diff.md        20 lines  -> v1.12.5 branch when #132 picked up
    6. amend_132_guard_test.md        19 lines  -> v1.12.5 branch when #132 picked up
    7. amend_v1124_backfill.md        30 lines  -> v1.12.4 scope (Amendment 7, 4 cycles fleet)

All verified present in container /tmp, 192 lines total.

### §17.6 Quick verification SQL (per-prod)

    Gate check
    python3 -c "
    import datetime as d
    now = d.datetime.now(d.timezone.utc)
    gate = d.datetime(2026,10,24,8,44,36,tzinfo=d.timezone.utc)
    print(f'now:  {now.strftime(\"%Y-%m-%dT%H:%M:%SZ\")}')
    print(f'gate: {gate.strftime(\"%Y-%m-%dT%H:%M:%SZ\")}')
    if now < gate:
        r = (gate - now).total_seconds()
        print(f'GATE NOT PASSED - {int(r//3600)}h {int((r%3600)//60)}m remaining')
        raise SystemExit(1)
    print('GATE PASSED')
    "

    DB verify (per prod)
    python3 <<'PY'
    import sqlite3, glob
    f = glob.glob('/config/.storage/daikin_cycle_ml_*.db')[0]
    conn = sqlite3.connect(f'file:{f}?mode=ro', uri=True)
    cols = {r[1] for r in conn.execute('PRAGMA table_info(cycles)')}
    print('is_transient:', 'is_transient' in cols)
    print('thermal_kw_avg:', 'thermal_kw_avg' in cols)
    print('mode_original (v18):', 'mode_original' in cols)
    print('is_reconstructed (v18):', 'is_reconstructed' in cols)
    print('journal_mode:', conn.execute('PRAGMA journal_mode').fetchone()[0])
    r = conn.execute("SELECT value_json FROM model_state WHERE key='data_migration_v1_12_2'").fetchone()
    print('v17_marker:', r[0] if r else 'NOT FOUND')
    r = conn.execute("SELECT value_json FROM model_state WHERE key='data_migration_v1_12_4'").fetchone()
    print('v18_marker:', r[0] if r else 'ABSENT (correct)')
    conn.close()
    PY

### §17.7 SSH quick start

    Prod 1 LAN
    ssh root@192.168.1.237 -p 2222

    Prod 1 Tailscale
    ssh root@100.81.96.34 -p 2222

    Prod 3 Tailscale
    ssh root@100.100.87.4 -p 22

    Container exec
    docker exec -i daikin_cycle_dev bash -lc 'cd /workspace/daikin_cycle_ml && git status --porcelain && git rev-parse HEAD'

Push via SSH: HA host -> cd /homeassistant/daikin_cycle_ml_dev && git push origin <branch>
(key Daikin Cycle ML). Container -> docker exec ... git push origin <branch> (key cycledev).
NOOIT git push https://TOKEN@... (R50).

### §17.8 Project state summary

    Field                     Value
    Branch                    main clean
    main HEAD                 a3e87fa
    origin/main               a3e87fa (MATCH)
    Tag v1.12.3               a3e87fa (Latest)
    Release latest            v1.12.3 (2026-10-22T18:24:17Z)
    Issue #116                OPEN, 6 comments
    Epic #119                 OPEN, 50-item checklist
    Milestones                v1.12.4: 2 open · v1.12.5: 10 open · v1.13.0: 3 open
    Tests @ main              7330 stmts / 2090 branches, 100.00%
    Mypy @ main               37 files strict clean
    Ruff @ main               All checks passed
    CI @ main                 HACS ✓ · Hassfest ✓ · Mypy ✓
    Sensors/Binary            50 / 15 (+2 update.*)
    Services/Repairs          13 / 9
    Branches ready            main, feat/v1.12.4-dhw-backfill, feat/v1.12.5-settle-time-gate, feat/v1.13.0-carnot-gate
    Protected                 feat/v1.6.0-hvac-parity @ a47414e (stash c3a-tmp)
    Prod 1                    1.12.3, wal, v17 {2,116}, epra12eav3, DHW cycle 150 closed
    Prod 2                    1.12.3, wal, v17 {3,179}, epra08eav3
    Prod 3                    1.12.3, wal, v17 {2,155}
    24h gate                  PASSED 2026-10-24T08:44:49Z
    Active trackers           #116, #119, #120-#134 (17 open)
    R-rules v96.0             NONE formalized
    run.py                    RETIRED since v77.0
    mypy-ci-venv              /opt/mypy-ci-venv (HA 2026.9.3)
    jq binary                 NOT installed — use python
    gh binary                 /usr/local/bin/gh v2.97 (container-local)
    Container name            daikin_cycle_dev (NOT _ml_dev)
    Amendment queue           7 files in /tmp/amend_*.md — VERIFIED

---

## §18 — Chat alerts (compact)

### §18.1 Context thresholds

    <50  🟢
    50-70 🟡 (prepare handoff)
    70-85 🟠 (finish current)
    85+  🔴 (stop, fresh mandatory)

### §18.2 Symptom -> rule

See §2.9 for full symptom table. Key clusters:
    R50 (tokens) · R91 (amend) · R133-R145 (handoff) · R327-R329 (heredoc)
    R345 (phantom) · R369/R390 (backticks gh body) · R371-R376 (bash -s heredoc)
    R384-R389 (PS2/heredoc failure) · R391-R403 (gh pr + test async)
    R404-R425 (version/gh/migrations) · R426-R431 (tests/markdown)
    R432-R440 (squash/DB pytest) · R441-R449 (Daikin physics + multi-install audit)
    R450-R451 (gh release JSON + grep multi-line)

### §18.3 STOP triggers

    Bare ruff check (R346) · Source transform zonder repr() verify (R345)
    Heredoc >1.5KB (R385) · Nested heredocs / backticks in markdown (R429)
    Length threshold pass/fail (R430) · gh pr checks --json for status (R431)
    gh pr create zonder headRefOid (R328) · Unquoted heredoc backticks (R418)
    | head -N onder set -euo (R329) · CI poll stale runs
    Terminal-read phantom typo zonder repr() (R345) · <tag> zonder ^{} (R407)
    json.dumps ensure_ascii=True (R337) · run.py referentie
    Dubbel plakken heredoc (R384) · Direct attr access zonder getattr (R353)
    Test hang zonder timeout wrapper · Direct async_setup_entry zonder patch (R402)
    Hassfest met <word> (R401) · <<PY unquoted met backticks (R418)
    git push -u origin <existing> zonder fetch (R419) · Amend na push zonder ls-remote (R421)
    WAL lone pragma (R436) · gh issue comment --body with backticks (R437)
    Data migration inside async_initialize reading v11-v15 (R438)
    Per-prod verify zonder baselines (R440) · I/U exact-match (R441)
    Fan DHW signal (R443) · Hardcoded flow threshold (R444)
    Single migration rule (R445) · Single-sample comparison (R446)
    Cross-install audit false-PASS (R447) · Multi-chunk paste silent drop (R448)
    Audit on 1 install (R449) · gh release view --json isLatest (R450)
    grep -n multi-line output without AST (R451)
    Diagnosing aggregation staleness without checking compressor
    Trusting COP >11 as valid physics
    Assuming 0 cycles = detector dead without DHW-only check
    Substring match on R4T/R5T as physics reference
    docker exec daikin_cycle_ml_dev (wrong name — use daikin_cycle_dev)
    Trusting cop_sample_count as real DB count (it's duration_s/30 — #133)

---

## §19 — Alert reference (matrix + channels + actions)

    Alert                    Trigger                                    Sev       Dedup   Persist  Notify  Action
    pendulum_hourly          cycles_in_window(3600) >= 4                warning   60m     ✓        ✓       Check setpoint/hysterese
    pendulum_daily           cycles_today >= 40 (non-transient)         warning   1440m   ✓        ✓       Reduce cycling
    short_run                last.duration < threshold                  warning   30m     ✓        ✓       Raise minlooptijd
    short_off                off < 5min (v1.12.1 gated)                 warning   30m     ✓        ✓       Check warmtevraag; restart = phantom
    ml_anomaly               snap.anomaly.is_anomaly                    warning   60m     ✓        ✓       Review cycles + detector
    setpoint_osc             _setpoint_history >= 6 + reversal          warning   30m     ✓        ✓       Lock LWT setpoint
    cop_low                  cop_today < 2.5 (n>=3)                     warning   30m     ✓        ✓       Inspect COP trend
    stooklijn_advies         state in {lower,raise}_lwt + conf >= 0.7   warning   10080m  ✓        ✓       Adjust heating curve
    cop_degradation          week_pct < -15.0                           warning   1440m   ✓        ✓       Check refrigerant/filters
    defrost_excessive        _defrost_7d_sum > 30                       warning   1440m   ✓        ✓       Check humidity/airflow
    buh_excessive            _buh_7d_ratio > 0.15                       warning   1440m   ✓        ✓       WP undersized
    source_stale             now - last_ok > 60s                        critical  60m     ✓        ✓       Check ESPAltherma MQTT/WiFi
    missing_attributes       len(missing_attrs) > 0                     warning   60m     ✓        ✓       Check attribute definition
    dhw_pendulum             DHW cycles/h >= 3                          warning   60m     ✓        ✓       Check DHW setpoint
    high_cycle_rate          cph > 4 * 1.5 (non-transient)              warning   60m     ✓        ✓       Adjust hysteresis/LWT
    cop_vs_datasheet_low     pct < -10.0                                info      1440m   ✓        ✓       Check charge/filters
    db_retention_warning     stale_alerts > 100 OR stale_cycles > 100   info      1440m   ✓        ✓       Run run_maintenance
    kmeans_retrain_stale     now - last_ok_ts > 14d                     info      1440m   ✓        ✓       Run recompute_kmeans
    energy_daily_anomaly     today_el > mean+2sigma + >2.0kWh + n>=7    info      1440m   ✓        ✓       Check demand/valves
    status_summary           6h scheduler                               info      6h      ✓        ✓       Read only

Channels: Persistent (always unless persistent_enabled: false), Notify, HA Store (last_sent), DB alerts table (NOT wired — v1.13.0).
Quiet hours: 22:00-07:00 local. Critical bypass. quiet_hours_enabled: false in prod.

Emoji mapping (19): see prior handoff §19 for full list. Severity: critical ⚠️, warning 🟡, info ℹ️.

---

## §20 — New bugs / backlog (this session)

### §20.1 Session discoveries

Fleet R4T/R5T attribute verification (closed pre-gate blocker):
    All 3 prods expose Inlet water temp.(R4T), DHW tank temp. (R5T),
    I/U operation mode, Operation Mode, 3way valve.
    Two R5T keys exist on prod 1 only:
        DHW tank temp. (R5T) = tank water (CORRECT)
        Heat exchanger mid-temp.(R5T) = refrigerant (DECOY)
    Same for R4T:
        Inlet water temp.(R4T) = water (CORRECT)
        O/U Heat Exch. Temp.(R4T) = refrigerant (DECOY)
    v1.12.5 const.py must use verbatim strings, no substring match.

8 split DHW pairs on prod 1 (widens #131):
    rows 2/3, 7/8, 25/26, 36/37, 66/67, 69/70, 70/71, 71/72.
    Gaps 30s-90s (all MODE_DEBOUNCE_S multiples).
    Worst case: rows 69-72 = 4-way split.
    Prior handoff only documented prod 2 splits (id 189/190/191).
    R446b (amendment 6) retroactively fixes both prods.

Live pre-fix artifact captured (validates R445e + #128):
    Sample 2712 at 08:07Z: cop=16.486, lwt=30.9, out=8.8, flow=26.7, mode='heating'.
    Flow 26.7 is DHW flow (heating baseline ~15.0). Valve was in DHW position
    when _resolve_cop_sample_mode returned 'heating'.
    Carnot = 13.76, ratio 1.198 >> 0.55 bound. R445e flags on migration.

Live compound-mode validation (v1.12.3 working):
    Full DHW reheat captured: I/U = 'Heating + DHW', 3way = 'ON',
    current_cycle = 'dhw', samples 2713-2717 all mode='dhw', COP 3.1-4.3,
    flow 26.4-26.7. No splits, no unknown flips. Clean reference for post-v1.12.4.

Cycle 150 closed baseline (post-gate reference):
    duration 5262s, end 1792834320.95, cop_avg=3.2415, cop_sample_count=172
    (inflated — real count is 16), cop_confidence='high', thermal_kw_avg=5.636,
    is_transient=0. NO MAX_CYCLE_DURATION_S cap hit.
    ⚠️ cop_sample_count=172 while real samples=16 confirms #133.

### §20.2 Verified findings (this session, cited)

    Finding                                           Source
    UPDATE_INTERVAL_SECONDS = 30 @ const.py:9         code-verified
    DHW tank temp. (R5T) present all 3 prods          attr dump 2026-10-24T00:16Z
    I/U operation mode present all 3 prods            same
    3way valve key present all 3 prods                same
    Heat exchanger mid-temp.(R5T) prod-1 only         same
    O/U Heat Exch. Temp.(R4T) prod-1 only             same
    Prod 1 attr count = 105 (not 81)                  attr dump 2026-10-24T08:25Z
    Prod 2 attr count = 186                           attr dump 2026-10-24T00:16Z
    Prod 3 attr count = 174                           attr dump 2026-10-24T00:18Z
    Brine inlet temp. prod-2/3 only (=0)              same
    Compound mode 'Heating + DHW' at 08:25Z           live capture
    3way = 'ON', current_cycle = 'dhw'                live capture
    Samples 2713-2717 mode='dhw'                      DB query
    Artifact 2712 cop=16.486, flow=26.7               DB query
    8 split DHW pairs prod 1                          DB query
    9 zero-sample DHW cycles (7 sub-300s, 2 NULL-agg) DB query
    DHW 14400s cap hits = 0 (heating-only)            DB query
    Unknown samples 83 all-time, 0 in 24h             DB query
    Unknown in-DHW-cycle = 7                          DB query
    COP artifacts 24h = 3                             DB query
    Carnot out-of-band DHW 24h = 0/17                 DB query
    v17 marker matches handoff (all 3 prods)          DB query
    v18 marker absent (all 3 prods)                   DB query
    cop_sample_count = duration_s/30 (60/150 cycles)  DB query 2026-10-24T~10:00Z
    cop_samples cadence 300-330s (97% of deltas)      DB query 2026-10-24T~10:00Z
    4 fleet-wide NULL-agg cycles: 1,2 (DHW) + 64,120 (heating)   DB query
    Cycle 150 closed: 5262s, cop=3.24, 172 stored / 16 real     DB query
    dhw_detect_v2.py NEVER existed on prod 1          ssh test, host /tmp
    HANDOFF.md last touched commit 89644c2 (v1.9.0-era)  git log 2026-10-24T~10:20Z

### §20.3 New bugs filed this session

#133 — cop_sample_count = duration_s/30 (tick count, not DB count)
    Scope: v1.12.5
    Evidence: cycle 150 dur=5262s stored=172 actual=16; cycle 137 dur=4381s
              stored=143 actual=13; fleet 60/150 cycles match duration/30
    Corollaries (both in #133 body):
    Amend 7 UPDATE target must use SELECT COUNT(*), AVG(cop) FROM cop_samples
    R446b merge recompute must use COUNT(*) + AVG(cop) from samples
    R447 n_samples must be COUNT(*) from samples (never sum from cycles.cop_sample_count)
    cop_confidence inflated by factor ~11x
    Impact on v1.12.4: zero blocking, but codes must respect the constraint
    Likely root cause: _process_new_cycle increments a counter per 30s tick

#134 — dhw_detect_v2.py never existed on prod 1
    Scope: v1.12.5 (recreate + test 4th-case detection pattern)
    Evidence: only /tmp/dhw_detect.py (v1, 6737 bytes, Oct 23 16:08) present
    Host uptime 20d 10h -> /tmp NOT cleared by reboot; v2 was never deployed
    v1 output captured for pre-fix reference:
        VERDICT: FAIL, 115 misclassified, 7 pure_dhw clusters,
        days_only_suspicious=6 days (10-11,12,13,20,21,22)
    Action: recreate v2 in repo scripts/ in v1.12.4 PR (R449 cross-install validation)
    Handoff §16.9 v95.0 claim "KEEP /tmp/dhw_detect_v2.py" was WRONG

### §20.4 Session meta-lessons

1. HANDOFF.md on disk was 17 versions stale (v79.0 mirror from 2026-10-18).
   Canonical handoff lived only in chat. This session fixes the drift by
   writing full v96.0 to disk.
2. amend_handoff_*.md were absorbed into handoff v96.0 by end-of-session.
   Do not apply separately.
3. Container /tmp persists across docker restart (in container's writable layer).
   Host /tmp is NOT the same filesystem.
4. "KEEP /tmp/X.py" in prior handoff is a claim that must be VERIFIED, not trusted.
   #134 is exactly this failure mode.
5. Fleet-level aggregate queries (COUNT by cop_sample_count class) catch
   systemic bugs that single-cycle inspection misses (#133).
6. Live DHW windows are gold for evidence: 30-minute reheat gives the full
   compound-mode + transition + steady-state trace. Cycle 150 pre-close is
   exactly this.

### §20.5 Fabrications retracted

None. Zero fabrications this session.

---

## When to say STOP

    - Context >85% (🔴)
    - Any RED flag in §18.3
    - Unverified claim about prod state before write
    - Anchor count != 1 in patch block (R355)
    - Test fails after patch (do not commit)
    - CI poll times out (R383 — not a failure, retry)
    - Container recreation needed (loses /tmp, gh auth, etc.)

---

## Ruleset / merge

    Ruleset: protect-main id=24465625
    6 required checks: HACS, Hassfest, Mypy, Python Tests, Ruff, Markdown
    Enforcement: active
    Merge: squash via gh pr merge --squash --auto (R432 subject format)
    Pre-push: runs ci-local.sh (~155s, 4 gates)

---

## Session history note

    v79.0  (2026-10-18)  Mirror rebuild after run.py retirement
    v79.1  ...           PR G remainder + retention fallback drift backlog
    v80-v94 (2026-10-18 to 2026-10-23)  Chat-canonical only, disk mirror stale
    v95.0  (2026-10-23T21:30Z)  Recon + pre-gate verification + DHW live capture
    v96.0  (2026-10-24T08:40Z, updated ~10:30Z)  Gate PASSED, cycle 150 baseline,
                                                 session findings #133/#134,
                                                 Amendment 7 fleet-wide (4 cycles),
                                                 ATTR_DHW_TANK_TEMP Option A,
                                                 full disk rewrite

    Next:   v97.0 after v1.12.4 ships and deploys to all 3 prods.
