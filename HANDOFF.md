# HANDOFF — Daikin Cycle ML

Agent-readable mirror of the current session handoff. The canonical
version lives in the maintainer's chat transcript.

NOTE ON FORMAT: code samples use 4-space indented blocks per R349.
Do not add triple-backtick fences when editing this file.

NOTE: DEEPSEEK.md is local-only, gitignored. Read from dev container if present.

## State summary (v79.0 rebuilt 2026-10-18)

    Branch          feat/v1.9.0-prg-cleanup (unpushed)
    main HEAD       27b2d31 (PR F merged)
    origin/main     27b2d31 (MATCH)
    Branch commits  4 — 1af57a9, 8e9ff83, c1f0a98, c43bb87
    Tag v1.8.1      a1d6c38
    Coverage        100.00% (6409 stmts / 1824 branches)
    Mypy            35 files strict
    Tracker         Issue #66 (PINNED, 53 done / 31 pending)
    Ruleset         protect-main id=24465625, 6 required contexts

## Session start protocol

1. Read AGENTS.md and DEEPSEEK.md (if present).
2. Read this file.
3. Run bootstrap block below inside the dev container.
4. If tree is dirty → investigate before proceeding.
5. Confirm scope with user. Do not begin new work until user says "go".

## Bootstrap

Paste inside HA host SSH shell (docker exec heredoc pattern).

    docker exec -i daikin_cycle_dev bash -lc 'bash -s' <<'BOOTSTRAP'
    set -uo pipefail
    cd /workspace/daikin_cycle_ml

    echo "=== GIT ==="
    git fetch --quiet origin 2>/dev/null || true
    echo "HEAD:        $(git rev-parse HEAD)"
    echo "branch:      $(git branch --show-current)"
    echo "origin/main: $(git rev-parse origin/main)"
    echo "dirty:       $(git status --porcelain | wc -l) files"
    git status --porcelain

    echo
    echo "=== COMMITS ==="
    git log --oneline -5

    echo
    echo "=== PRS / ISSUES ==="
    gh pr list --state open
    gh issue list --limit 5 --state open

    echo
    echo "=== TRACKER #66 ==="
    gh issue view 66 --json body -q .body > /tmp/i66.md 2>/dev/null || true
    echo "pending: $(grep -c '^- \[ \]' /tmp/i66.md 2>/dev/null || echo 0)"
    echo "done:    $(grep -c '^- \[x\]' /tmp/i66.md 2>/dev/null || echo 0)"

    echo
    echo "=== CI (main) ==="
    gh run list --branch main --limit 3 2>/dev/null || echo "(skipped)"
    BOOTSTRAP

## Current work — PR G remaining

    Priority  Task                                          State
    DONE      §4.15 retention 30 → 90                       1af57a9
    DONE      §4.11 batch 2a rename                         8e9ff83
    DONE      §4.10 dead template removal                   c1f0a98
    DONE      §4.14 emoji consolidation                     c43bb87
    DONE      C5 agent docs (this commit)                   —
    RED       Q4 setpoint_osc reversal gate                 pending
    DONE      §19 rewrite + §21 drop (docs)                 8ae5009 (via C5)
    RED       Plan-B live-fire (manual)                     pending
    RED       Push branch + create PR G                     pending
    ORANGE    §4.12 / §4.13 verify/close tracker boxes      pending
    ORANGE    Tracker #66 recovery comment                  pending

### Deferred (not in PR G)

    alert_type              Reason
    datasheet_missing       needs last_cop_norm_unknown_ts
    kmeans_retrain_stale    needs last_kmeans_ok_ts
    db_retention_warning    pure read, hygiene
    quality_degradation     needs 7d quality helper
    energy_daily_anomaly    needs thermal baseline + sigma
    service_due             needs cumulative runtime counter

### Deferred to batch 2b (§4.11 Q5 second half)

    Add avg_duration_7d_min to alert contexts.
    Needs async plumbing decision (Option A cache / B executor / C async).
    Labels EN "Avg duration 7d" / NL "Gem. duur 7d" already specified.

### §4.15a — retention fallback drift (v79.1 backlog)

    coordinator.py:551 and storage/db.py:550 hardcode alert_retention_days=30
    instead of reading DEFAULT_ALERT_RETENTION_DAYS. §4.15 bumped the const
    but not the fallbacks. Needs spec amendment + follow-up fix.

## R350 recon (before any alert-pipeline edit)

    rg --hidden --glob '!__pycache__' -l \
      'ALERT_SCHEMA|ALERT_ADVICE|ALERT_TYPE_EMOJI|BINARY_ALERT_MAP|NOTIF_ID_BY_TYPE|alert_group_|alert_enabled_|alert_agg_' \
      tests/ custom_components/

## Live alert inventory (16 + status_summary)

    1  pendulum_hourly      evaluate_alerts    pendulum         warning
    2  pendulum_daily       evaluate_alerts    pendulum         warning
    3  short_run            evaluate_alerts    short_cycle      warning
    4  short_off            evaluate_alerts    short_cycle      warning
    5  ml_anomaly           evaluate_alerts    ml               warning
    6  setpoint_osc         evaluate_alerts    setpoint         warning
    7  cop_low              standalone         cop_stooklijn    warning
    8  stooklijn_advies     standalone         cop_stooklijn    warning
    9  cop_degradation      evaluate_alerts    cop_stooklijn    warning
    10 defrost_excessive    evaluate_alerts    component_health warning
    11 buh_excessive        evaluate_alerts    component_health warning
    12 source_stale         evaluate_alerts    data_quality     critical
    13 missing_attributes   evaluate_alerts    data_quality     warning
    14 dhw_pendulum         evaluate_alerts    pendulum         warning
    15 high_cycle_rate      evaluate_alerts    short_cycle      warning
    16 cop_vs_datasheet_low evaluate_alerts    cop_stooklijn    info
    17 status_summary       async_emit_status_update none        info

## When to say STOP

Rule violations requiring halt:
- R41, R50, R53, R90, R91, R93, R96, R103, R107, R113, R117, R302,
  R318, R327, R328, R329, R331, R347, R350, R351, R352, R353, R355
- Bare ruff check without --no-fix (R332)
- Alert-render release without Plan-B gate
- Heredoc > ~3.5KB to bash -s
- gh pr create without headRefOid verify (R328)
- Unquoted heredoc with backticks (R327)
- | head -N under set -euo pipefail (R329)
- json.dumps ensure_ascii=True (R337)
- run.py reference (retired)
- Double-paste of any heredoc (R336)
- Tracker box tick before merge commit exists (R351)
- Region cut without pre-cut symbol-grep over whole repo (R356)
- Post-cut substring guard without word-boundary regex (R357)
- Structural source-grep test not revised on legit refactor (R358)

## Ruleset / merge

- protect-main id=24465625, 6 required contexts
- Merge via gh pr merge --squash --subject ... --body ...
- Never --admin
- PR body line 1: Refs #66

## Session history note

Dev container was lost 2026-10-18 (docker image + container pruned after
HA OS upgrade to 2026.10.1). Branch reconstructed from chat transcript.
Original session had 7 commits; rebuild consolidated to 4 + agent docs.
SHAs differ from original; content equivalent. **Push after every batch
from now on to prevent recurrence.**
