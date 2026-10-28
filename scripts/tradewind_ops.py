#!/usr/bin/env python3
"""Offline diagnostics, billing audit and explicit reconciliation for Trade Wind."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.tradewind_core.security import settings, redact
from src.tradewind_core.store import Store
from src.tradewind_core.api import Client


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file')
    p.add_argument('--state-dir')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');sub.add_parser('usage');sub.add_parser('countries')
    r=sub.add_parser('reconcile')
    r.add_argument('operation_id');r.add_argument('--credits',required=True)
    r.add_argument('--state',choices=['completed','failed'],required=True)
    r.add_argument('--evidence',required=True,help='Provider receipt/log reference; never guess zero')
    a=p.parse_args(argv);cfg=settings(a.env_file)
    if a.command=='doctor':
        print(json.dumps({'version':'2.0.0rc1','key_configured':bool(cfg['key']),
            'config_source':cfg['config_source'],'distribution':cfg['distribution'],
            'legacy_credentials_used':False,'network_calls':0},ensure_ascii=False,indent=2));return 0
    ns=hashlib.sha256(cfg['key'].encode()).hexdigest()[:16] if cfg['key'] else 'offline'
    store=Store(a.state_dir or cfg['state'],ns)
    try:
        if a.command=='reconcile':
            store.reconcile(a.operation_id,a.credits,a.state,a.evidence)
            result={'budget':store.budget(),'operations':store.operations()}
        elif a.command=='countries':
            result=Client(cfg,store).call('customs.reference.countries',{},'customs-countries')
        else: result={'budget':store.budget(),'operations':store.operations()}
        print(json.dumps(redact(result,[cfg['key']]),ensure_ascii=False,indent=2))
    finally:store.close()
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(json.dumps({'error':redact(str(exc))}),file=sys.stderr);raise SystemExit(1)
