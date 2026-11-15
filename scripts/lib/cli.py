"""Common argparse for every script."""
import argparse
import os


def common_parser(prog, desc):
    p = argparse.ArgumentParser(prog=prog, description=desc)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--verbose', '-v', action='store_true')
    p.add_argument('--json', action='store_true')
    return p


def apply(args):
    if args.verbose:
        os.environ['VERBOSE'] = '1'
    if args.dry_run:
        os.environ['DRY_RUN'] = '1'
