#!/usr/bin/env python3
"""git_safe — git wrapper enforcing R-rules."""
import argparse
import os
import re
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)
from lib import exit_codes, git, log, text  # noqa: E402


def cmd_diff_main(args):
    print(f'Changed vs {args.base}:')
    for f in git.changed_files(args.base):
        print(f'  {f}')
    return exit_codes.OK

def cmd_commit(args):
    if not git.staged_files():
        log.warn('nothing staged — commit will fail; run: git add ...')
    msg = args.message
    if args.partial_issue:
        bad = re.search(rf'(?i)\b(fixes|closes|resolves)\s+#{args.partial_issue}\b', msg)
        if bad:
            log.err(f'partial fix uses "{bad.group(0)}" — auto-closes the issue')
            log.err(f'use "Part of #{args.partial_issue}" — closes only on --complete')
            return exit_codes.AST_FAIL
        if not re.search(rf'(?i)\bpart\s+of\s+#{args.partial_issue}\b', msg):
            log.warn(f'hint: partial fix should say "Part of #{args.partial_issue}"')
    closers = re.findall(r'(?i)\b(fixes|closes|resolves)\s+#(\d+)', msg)
    if closers and not args.complete:
        log.warn(f'hint: auto-close keyword(s) {closers} — add --complete to confirm')
    if text.has_dutch(msg):
        log.err('commit message contains Dutch — English only (translations/nl.json is the only allowed place)')
        return exit_codes.AST_FAIL
    log.info(f'git commit -m {msg!r}')
    git.run('commit', '-m', msg)
    return exit_codes.OK

def cmd_amend(args):
    git.run('commit', '--amend', '--no-edit')
    if not args.push:
        return exit_codes.OK
    branch = git.current_branch()
    git.run('push', '--force-with-lease', 'origin', branch)
    remote, local = git.remote_hash(branch), git.local_hash()
    if remote != local:
        log.err(f'remote {remote[:7]} != local {local[:7]} — force-push did not stick')
        return exit_codes.PUSH_FAIL
    log.ok(f'remote verified {remote[:7]}')
    return exit_codes.OK

def _has_keepalive():
    import pathlib
    p = pathlib.Path.home() / '.ssh' / 'config'
    return p.exists() and 'ServerAliveInterval' in p.read_text()

def _pr_body_has_r813(branch):
    import subprocess
    r = subprocess.run(
        ['gh', 'pr', 'view', branch, '--json', 'body', '-q', '.body'],
        check=False, capture_output=True, text=True,
    )
    body = (r.stdout if r.returncode == 0 else '').lower()
    return ('r813' in body
            or 'no-verify bypass' in body
            or 'bypass rationale' in body)


def cmd_push(args):
    branch = args.branch or git.current_branch()
    local = git.local_hash()
    remote = git.remote_hash(branch)
    log.info(f'{branch}: local={local[:7]} remote={remote[:7] or "(none)"}')
    if local == remote:
        log.warn(f'nothing to push ({branch} == origin/{branch})')
        return exit_codes.OK
    if not _has_keepalive():
        log.warn('hint: ~/.ssh/config missing ServerAliveInterval — long pushes may drop')
    if args.no_verify and not _pr_body_has_r813(branch):
        log.err('--no-verify requires "## R813 bypass" or "## no-verify bypass" section in PR body')
        return exit_codes.PUSH_FAIL
    cmd = ['push'] + (['--no-verify'] if args.no_verify else []) + ['origin', branch]
    try:
        git.run(*cmd)
    except git.GitError as e:
        msg = ((e.err or '') + (e.out or '')).lower()
        if 'pre-push' in msg or 'hook' in msg:
            log.warn('hint: pre-push hook failed (see stderr above)')
            log.warn('hint: add "## no-verify bypass" to PR body, then retry --no-verify')
        elif 'rejected' in msg or 'failed to push' in msg:
            log.warn('hint: push rejected — check branch protection or non-fast-forward')
            log.warn('hint: push via PR; force: git_safe amend --push')
        raise
    log.ok(f'pushed {branch} -> {local[:7]}')
    return exit_codes.OK


def cmd_post_merge(args):
    body = f'Post-merge verification: PR #{args.pr_num} merged into main.'
    if args.detail:
        body += f'\n\n{args.detail}'
    if text.has_dutch(body):
        log.err('post-merge comment contains Dutch — English only')
        return exit_codes.AST_FAIL
    import subprocess
    r = subprocess.run(['gh','pr','comment',str(args.pr_num),'--body',body],
        check=False, capture_output=True, text=True)
    if r.returncode != 0:
        log.err(f'gh pr comment failed: {r.stderr.strip()}')
        return exit_codes.PUSH_FAIL
    log.ok(f'commented on PR #{args.pr_num}')
    return exit_codes.OK

def cmd_branch_cleanup(args):
    if args.branch in ('main','master'):
        log.err(f'refusing to delete protected branch "{args.branch}"')
        return exit_codes.AST_FAIL
    if not git.output('branch', '--list', args.branch).strip():
        log.warn(f'branch "{args.branch}" not found locally')
        return exit_codes.OK
    git.run('branch', '-D', args.branch)
    log.ok(f'deleted {args.branch}')
    return exit_codes.OK

def cmd_branch_delete(args):
    git.run('push', '--no-verify', 'origin', '--delete', args.branch)
    log.ok(f'deleted remote branch {args.branch}')
    return exit_codes.OK

def main():
    p = argparse.ArgumentParser(prog='git_safe')
    sub = p.add_subparsers(dest='cmd', required=True)

    def add(name):
        sp = sub.add_parser(name)
        sp.add_argument('--dry-run', action='store_true')
        sp.add_argument('--verbose', '-v', action='store_true')
        sp.add_argument('--json', action='store_true')
        return sp

    d = add('diff-main')
    d.add_argument('--base', default='origin/main')
    d.set_defaults(func=cmd_diff_main)

    c = add('commit')
    c.add_argument('-m', '--message', required=True)
    c.add_argument('--partial-issue', type=int)
    c.add_argument('--complete', action='store_true')
    c.set_defaults(func=cmd_commit)

    a = add('amend')
    a.add_argument('--push', action='store_true')
    a.set_defaults(func=cmd_amend)

    pu = add('push')
    pu.add_argument('--branch')
    pu.add_argument('--no-verify', action='store_true')
    pu.set_defaults(func=cmd_push)

    pm = add('post-merge')
    pm.add_argument('pr_num', type=int)
    pm.add_argument('--detail', default='')
    pm.set_defaults(func=cmd_post_merge)

    bc = add('branch-cleanup')
    bc.add_argument('branch')
    bc.set_defaults(func=cmd_branch_cleanup)

    bd = add('branch-delete')
    bd.add_argument('branch')
    bd.set_defaults(func=cmd_branch_delete)

    args = p.parse_args()
    if args.dry_run:
        os.environ['DRY_RUN'] = '1'
    if args.verbose:
        os.environ['VERBOSE'] = '1'

    try:
        code = args.func(args)
    except git.GitError as e:
        log.err(f'git {" ".join(map(str, e.cmd))} failed (exit {e.rc})')
        for ln in (e.err or '').rstrip().splitlines():
            if ln:
                log.err(ln)
        code = exit_codes.PUSH_FAIL
    except Exception as e:
        log.err(f'{type(e).__name__}: {e}')
        code = exit_codes.AST_FAIL

    if args.json:
        log.emit_json({'exit': code, 'cmd': args.cmd})
    return code



if __name__ == '__main__':
    sys.exit(main())
