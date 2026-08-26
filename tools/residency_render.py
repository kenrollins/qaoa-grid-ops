#!/usr/bin/env python3
"""Render a gridops-residency /status or /claim response as operator text.

A separate file, not a `python3 -c` one-liner inside gb10-gpu: the inline
version needed double quotes inside an f-string inside a single-quoted shell
string, which Python only tolerates from 3.12 and which nothing could lint.
"""
from __future__ import annotations

import json
import sys
import time


def main() -> int:
    try:
        d = json.load(sys.stdin)
    except ValueError:
        print('gridops-residency returned something that is not JSON', file=sys.stderr)
        return 1
    if not isinstance(d, dict):
        print(d)
        return 0

    # An error body from the service (FastAPI's {"detail": ...}) is the useful
    # thing to show, not an empty status render.
    if 'detail' in d and 'state' not in d:
        print('REFUSED   {}'.format(d['detail']))
        return 1

    busy = '  (busy: {})'.format(d['busy']) if d.get('busy') else ''
    print('STATE     {}{}'.format(d.get('state'), busy))
    if d.get('holder'):
        print('HOLDER    {} ({})'.format(d['holder'], d.get('principal')))
    rem = d.get('lease_remaining_seconds')
    if rem is not None and d.get('state') == 'claimed':
        print('LEASE     {}m {}s remaining of {}s'.format(
            rem // 60, rem % 60, d.get('lease_seconds')))
    if d.get('pre_claim_models'):
        print('RECORD    restore on release: {}'.format(', '.join(d['pre_claim_models'])))
    if d.get('pending_restore'):
        print('PENDING   NOT yet restored: {}'.format(', '.join(d['pending_restore'])))

    obs = d.get('observed') or {}
    if obs:
        loaded = obs.get('loaded_models')
        if loaded is None:
            lm = 'unknown'
        elif loaded:
            lm = ', '.join(loaded)
        else:
            lm = 'none'
        print('OBSERVED  orchestrator {} · loaded: {}'.format(
            'up' if obs.get('orchestrator_reachable') else 'DOWN', lm))
        ceiling = ''
        if obs.get('qsim_max_qubits'):
            ceiling = ' · ceiling {} qubits'.format(obs['qsim_max_qubits'])
        print('          qsim {}{}'.format(
            'serving' if obs.get('qsim_serving') else 'not serving', ceiling))

    if d.get('last_error'):
        print('ERROR     {}'.format(d['last_error']))

    for step in (d.get('progress') or [])[-12:]:
        stamp = time.strftime('%H:%M:%S', time.localtime(step.get('t', 0)))
        detail = ' — {}'.format(step['detail']) if step.get('detail') else ''
        print('  {}  {:<8} {}{}'.format(stamp, step.get('status', ''), step.get('step', ''), detail))
    return 0


if __name__ == '__main__':
    sys.exit(main())
