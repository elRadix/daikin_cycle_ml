# AGENTS.md — Daikin Cycle ML

HA custom integration. Python 3.14, HA Core 2026.10.
Loaded automatically by DeepSeek Code at session start.

NOTE ON FORMAT: code samples use 4-space indented blocks per R349.
Do not add triple-backtick fences when editing this file.

NOTE: DEEPSEEK.md is local-only, gitignored. Read it from the dev
container at /workspace/daikin_cycle_ml/DEEPSEEK.md if present.

## Project identity

- Repo: /workspace/daikin_cycle_ml (daikin_cycle_dev, image python:3.14)
- Main tip: 27b2d31 (PR F merge, PR #74)
- Working branch: feat/v1.9.0-prg-cleanup (unpushed at session start)
- Tracker: GitHub issue #66 (PINNED, 53 done / 31 pending)
- Release in flight: v1.9.0 (target); stable is v1.8.1
- Retired: run.py — never reference
- Ruleset protect-main: id 24465625, 6 required contexts

## Current state (v79.0 rebuilt 2026-10-18)

- Coverage: 100.00% (6409 stmts / 1824 branches)
- Mypy: 35 files strict
- i18n parity: config.step 157/157/157 · options.step 280/280/280
- Sensors / Binary / Registry: 46 / 15 / 61 (+2 update.* = 63 by entity_id)
- Services / Repairs: 9 / 8
- DB: daikin_cycle_ml.db schema v15 · HA Store alerts schema v1

### PR G progress (post-rebuild)

    Item                                       Commit    State
    §4.15 retention constant 30 → 90           1af57a9   landed
    §4.11 batch 2a rename avg_duration_min     8e9ff83   landed
    §4.10 dead template system removal         c1f0a98   landed
    §4.14 emoji map consolidation              c43bb87   landed
    Q4 setpoint_osc reversal gate              c20d0b6   landed
    §19 rewrite + drop §21 box                 8ae5009   landed (via C5)
    Plan-B live-fire                           —         pending (manual)
    Push branch + PR G                         —         pending

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

## Hard rules (CANDIDATES)

    R336  Double-paste heredoc failure mode.
    R337  json.dumps(..., ensure_ascii=False) for translations.
    R345  Phantom reads — verify with repr() + str.count() server-side.
    R346  Local verification = same command as CI:
          ruff check --no-fix --select E,F,W --ignore E501,E402,F401.
    R348  Plan-B steps must document WHICH code path they exercise.
    R349  Heredoc markdown MUST use 4-space-indented code blocks.
    R354  mypy strict needs temp var for getattr ternary.
    R356  Pre-cut symbol-grep over WHOLE repo, not cut window.
    R357  Post-cut substring guards use word-boundary regex.
          db_avg_duration_min contains _avg_duration_min.
    R358  Structural source-grep tests break on legit refactor.

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

## SSH

    Tailscale: ssh root@100.81.96.34 -p 2222
    LAN:       ssh root@192.168.1.237 -p 2222

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

## Scope boundaries

- In scope: custom_components/daikin_cycle_ml/, tests/, .github/workflows/, translations
- Out of scope: run.py, HA supervisor config, anything outside the repo
- New files: under 500 lines

## Session history note

Dev container was lost 2026-10-18 (docker image + container pruned after HA OS
upgrade). Branch reconstructed from chat transcript same day. Commit SHAs differ
from the original session (pre-crash had 7 commits). Content is equivalent;
consolidated into fewer commits during rebuild (docs merged, SHA-record commits
dropped). All work is now pushed to origin after each batch to prevent recurrence.
