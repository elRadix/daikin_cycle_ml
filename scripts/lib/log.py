"""Unified logging."""
import json
import os
import sys

_COLORS = sys.stderr.isatty() and os.environ.get('NO_COLOR') is None


def _c(code, s):
    if not _COLORS:
        return s
    return f'\033[{code}m{s}\033[0m'


def info(msg):
    print(_c('36', '· ') + msg, file=sys.stderr)


def ok(msg):
    print(_c('32', '✓ ') + msg, file=sys.stderr)


def warn(msg):
    print(_c('33', '! ') + msg, file=sys.stderr)


def err(msg):
    print(_c('31', '✗ ') + msg, file=sys.stderr)


def debug(msg):
    if os.environ.get('VERBOSE'):
        print(_c('90', '  · ') + msg, file=sys.stderr)


def emit_json(data):
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write('\n')
