#!/usr/bin/env python3
"""Offline diagnostics, billing audit and explicit reconciliation for Trade Wind."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.tradewind_core import VERSION
from src.tradewind_core.security import settings, redact
from src.tradewind_core.store import Store
from src.tradewind_core.api import Client


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file')
    p.add_argument('--state-dir')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor');sub.add_parser('usage');sub.add_parser('countries')
    b=sub.add_parser('billing-report')
    b.add_argument('--output', help='Private JSON handoff for maintainers; no business API calls')
    d=sub.add_parser('diagnose')
    d.add_argument('--proxy-mode',choices=['system','direct'],default='system')
    d.add_argument('--output')
    recovery=sub.add_parser('recover-refused')
    recovery.add_argument('--apply',action='store_true')
    r=sub.add_parser('reconcile')
    r.add_argument('operation_id');r.add_argument('--credits',required=True)
    r.add_argument('--state',choices=['completed','failed'],required=True)
    r.add_argument('--evidence',required=True,help='Provider receipt/log reference; never guess zero')
    a=p.parse_args(argv);cfg=settings(a.env_file)
    if a.command=='doctor':
        print(json.dumps({'version':VERSION,'key_configured':bool(cfg['key']),
            'config_source':cfg['config_source'],'distribution':cfg['distribution'],
            'legacy_credentials_used':False,'network_calls':0},ensure_ascii=False,indent=2));return 0
    if a.command=='diagnose':
        from src.tradewind_core.network import diagnose
        from src.tradewind_core.security import private_json
        result=diagnose(a.proxy_mode)
        if a.output: private_json(a.output,result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['network_reachable'] else 2
    ns=hashlib.sha256(cfg['key'].encode()).hexdigest()[:16] if cfg['key'] else 'offline'
    state_root=a.state_dir or cfg['state']
    if a.command=='billing-report' and not (Path(state_root)/ns/'state.sqlite3').is_file():
        raise ValueError('未找到原账户账本；请沿用实际运行的工作目录和state-dir，不能用空账本证明费用已解决。')
    store=Store(state_root,ns)
    try:
        if a.command=='billing-report':
            result=store.billing_report()
            if a.output:
                from src.tradewind_core.security import private_json
                private_json(a.output, redact(result,[cfg['key']]))
        elif a.command=='recover-refused':
            result=store.recover_refused(a.apply)
        elif a.command=='reconcile':
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
