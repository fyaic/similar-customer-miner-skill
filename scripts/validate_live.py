#!/usr/bin/env python3
"""Explicitly paid, bounded release check; never runs as part of pytest.

Uses one existing ledger for all cases. Keep generated customer evidence private.
This is an integration sample, not a statistically representative sales benchmark.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cli import run_pipeline, _apply_runtime_mode
from src.config_loader import load_config
from src.tradewind_core.security import private_json

CASES = [
    ('faucet-us', 'homedepot.com', 'faucet', 'US', 3),
    ('packaging-ca', 'uline.ca', 'packaging', 'CA', 2),
    ('tools-gb', 'screwfix.com', 'hand tools', 'GB', 2),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file', required=True)
    p.add_argument('--state-dir', required=True, help='Reuse the existing account ledger')
    p.add_argument('--max-credits', required=True, help='Cumulative ceiling including historical charges')
    p.add_argument('--output-dir', required=True)
    a = p.parse_args()
    output = Path(a.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = []
    for case, anchor, product, country, enrich in CASES:
        source = output/(case+'.csv')
        with source.open('w') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'main_products', 'region_positioning'])
            writer.writerow([case, anchor, product, country])
        cfg = load_config(load_local=False)
        _apply_runtime_mode(cfg, 'live')
        cfg['pipeline'].update(target_countries=[country], max_results_per_customer=3)
        cfg['tradewind'].update(env_file=a.env_file, state_dir=a.state_dir,
            max_credits=a.max_credits, max_enrich=enrich, verify_email=True)
        rows = run_pipeline(str(source), str(output/(case+'.xlsx')), cfg)
        stats = cfg['_run_stats']['tradewind']
        item = {'case': case, 'country': country, 'product': product,
                'companies': [{'name': c.company_name, 'domain': c.website, 'country': c.country,
                    'contact_title': c.contact_title, 'named_contact': bool(c.contact_name),
                    'role_match': c.contact_role_fit, 'mailbox_verified': c.email_verified,
                    'verification_status': c.email_verification_status, 'grade': c.grade} for c in rows],
                'stats': stats}
        summary.append(item)
        private_json(output/'live-summary.json', summary)
        print(json.dumps(item, ensure_ascii=False), flush=True)
        if stats.get('stop_reason'):
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
