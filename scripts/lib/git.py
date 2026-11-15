"""Git subprocess wrapper. Raises GitError with full stderr."""
import os
import subprocess
import sys

DEFAULT_TIMEOUT = 600


class GitError(Exception):
    def __init__(self, cmd, rc, out, err):
        self.cmd = cmd
        self.rc = rc
        self.out = out
        self.err = err
        super().__init__(f'git {" ".join(map(str, cmd))} (exit {rc})')


def _run(*a, check=True):
    if os.environ.get('DRY_RUN'):
        print(f'[dry-run — NOT EXECUTED] git {" ".join(a)}', file=sys.stderr)
        return subprocess.CompletedProcess(a, 0, '', '')
    timeout = int(os.environ.get('GIT_TIMEOUT', DEFAULT_TIMEOUT))
    r = subprocess.run(
        ['git', *a], capture_output=True, text=True, timeout=timeout,
    )
    if check and r.returncode != 0:
        raise GitError(a, r.returncode, r.stdout, r.stderr)
    return r


def run(*a, check=True):
    return _run(*a, check=check)


def output(*a):
    return _run(*a).stdout.strip()


def current_branch():
    return output('rev-parse', '--abbrev-ref', 'HEAD')


def is_clean():
    return output('status', '--porcelain') == ''


def staged_files():
    return [f for f in output('diff', '--cached', '--name-only').split('\n') if f]


def changed_files(base='origin/main'):
    for b in (base, 'main', 'HEAD~1'):
        try:
            return [f for f in output('diff', '--name-only', f'{b}...HEAD').split('\n') if f]
        except GitError:
            continue
    return []


def remote_hash(b):
    try:
        return output('rev-parse', f'origin/{b}')
    except GitError:
        return ''


def local_hash():
    return output('rev-parse', 'HEAD')
