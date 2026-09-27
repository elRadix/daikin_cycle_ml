# HANDOFF SOP - Daikin Cycle ML

Self-contained SOP for handoff generation and multi-repo maintenance.
Rules R133-R145. Companion to SOP.md.

## 1. When to generate a handoff (R133)

Generate a new handoff when:

- Context indicator is ORANGE (80-90%)
- Context indicator is YELLOW (50-79%) AND a milestone is reached
- Context indicator is RED (>90%) - mandatory, stop other work first

| Indicator | Action |
|-----------|--------|
| GREEN < 50% | Continue |
| YELLOW 50-79% | Warn on substantial step |
| ORANGE 80-90% | Mandatory: handoff before next large step |
| RED > 90% | STOP - only finish + handoff |

R87: ORANGE + >3 iterations -> STOP.

## 2. Handoff versioning (R134, R139)

- Version number = +1 MAJOR (v16.0 -> v17.0), never minor
- Handoff version line MUST contain:
  - Full 40-char git commit hash of HEAD
  - Tag reference (annotated tag object + target)
  - In-sync status with origin/main

## 3. Self-contained requirement (R135)

A fresh chat must be able to:

- Find every relevant fact without external lookups
- Resume work from DEEL 17 (start-here section)

FORBIDDEN in handoff:

- Three-dot placeholders in tables
- Etc. in structured lists
- References like see previous handoff

## 4. Uncertainty marking (R136, R137)

Mark unknown items as: TE VERIFIEREN

Mark obsolete rules explicitly: VERVALLEN - do NOT remove them.
Reason: history of why a rule existed is valuable.

Example from v17.0:

- R99: VERVALLEN in v1.1.0 - no symlinks, single source
- R112: VERVALLEN in v1.1.0

## 5. Pre-handoff checks (R138)

Before writing the handoff, run:

1. git status (working tree clean?)
2. git rev-parse HEAD / origin/main (in sync?)
3. CI status on HEAD (6/6 green?)
4. HACS PR status (if applicable)
5. Container status (daikin_test Up?)
6. Prod HA runtime (entities, DB, errors)

## 6. Storage method (R140)

Generate the handoff in chat, then save via heredoc:

    cat > /config/handoff_vXX.md << 'HANDOFF_END'
    ... content ...
    HANDOFF_END

Reason: File Editor fails silently on files >5 KB (R90).
Verify with wc -c + marker-grep before use.

## 7. Multi-repo discipline (R141-R145)

Two repos in play:

| Repo | Purpose | Where |
|------|---------|-------|
| elRadix/daikin_cycle_ml | Dev, releases, tags | /workspace/daikin_cycle_ml (host-mount) |
| elRadix/default | HACS fork, PR-only | /workspace/hacs-default (container-only) |

R141: Never confuse the two. Each has its own git config.

R142: After opening a HACS PR, NEVER push to the feature branch.
The HACS bot auto-closes PRs on new commits.

R143: New HACS PR = new branch from fresh upstream/master.
Do not reuse an old branch.

R144: Before new PR: sync fork-master:

    git fetch upstream
    git reset --hard upstream/master
    git push origin master --force-with-lease

R145: Fork git identity must be LOCAL (--no-global):

    cd /workspace/hacs-default
    git config user.name elRadix
    git config user.email elRadix@users.noreply.github.com

Never use --global in container - affects other repos.

## 8. Quick reference

| Rule | One-liner |
|------|-----------|
| R133 | Handoff at ORANGE / YELLOW-milestone / RED |
| R134 | +1 major, never minor |
| R135 | Self-contained, no placeholders or etc. |
| R136 | Mark unknown as TE VERIFIEREN |
| R137 | Mark obsolete as VERVALLEN, keep them |
| R138 | Check git/CI/PR/containers first |
| R139 | Version = full hash + tag ref |
| R140 | Generate in chat, save via heredoc |
| R141 | Two repos: dev + fork, never confuse |
| R142 | No push after PR-open |
| R143 | New PR = new branch from upstream/master |
| R144 | Sync fork-master before new PR |
| R145 | Fork identity local, never --global |

