#!/usr/bin/env python3
"""Replay a private frozen Trade Wind response library against a chosen checkout.

Zero network; unknown requests fail closed. Run the identical script with two
--source-root values to compare releases without reusing legacy provider keys.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', required=True)
    p.add_argument('--responses', required=True, help='Private JSON: method/path/body/response records')
    p.add_argument('--output-dir', required=True)
    p.add_argument('--company-only', action='store_true', help='Disable person enrichment/email verification in both versions')
    p.add_argument('--product-evidence-file', help='Optional operator reviews, separate from frozen API response evidence')
    p.add_argument('--no-contact-search', action='store_true', help='rc3 qualification-only replay, never a contact-coverage comparison')
    a = p.parse_args()
    sys.path.insert(0, str(Path(a.source_root).resolve()))
    from src import tradewind as tw
    from src.cli import run_pipeline, _apply_runtime_mode
    from src.config_loader import load_config
    from src.tradewind_core.security import private_json
    fixture = Path(a.responses).read_bytes()
    records = json.loads(fixture)
    fingerprint = lambda method, path, body: json.dumps([method, path, body], sort_keys=True)
    responses = {fingerprint(r['method'], r['path'], r['body']): r['response'] for r in records}
    out = Path(a.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    missing = []
    summary = {'mode': 'frozen_response_replay', 'network_calls': 0, 'actual_new_credits': '0', 'company_only': a.company_only,
               'contact_search_enabled':not a.no_contact_search, 'external_product_reviews':bool(a.product_evidence_file),
               'response_library_sha256': hashlib.sha256(fixture).hexdigest(), 'cases': []}
    def send(method, url, body, headers, timeout):
        key = fingerprint(method, url.removeprefix('https://app.trade-wind.co'), body)
        if key not in responses:
            missing.append({'method': method, 'path': url, 'body': body})
            raise ValueError('Missing frozen response; network fallback forbidden')
        return 200, responses[key]
    with tempfile.TemporaryDirectory() as temp:
        for case, anchor, product, country, enrich in [
            ('faucet-us', 'homedepot.com', 'faucet', 'US', 3),
            ('packaging-ca', 'uline.ca', 'packaging', 'CA', 2),
            ('tools-gb', 'screwfix.com', 'hand tools', 'GB', 2),
        ]:
            source = out/(case+'.csv')
            with source.open('w') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name', 'main_products', 'region_positioning'])
                writer.writerow([case, anchor, product, country])
            cfg = load_config(load_local=False)
            _apply_runtime_mode(cfg, 'live')
            cfg['pipeline'].update(target_countries=[country], max_results_per_customer=3)
            cfg['tradewind'].update(state_dir=str(Path(temp)/case), max_credits='100', max_enrich=enrich, people_source='hunter', people_job_titles=[], verify_email=not a.company_only, enrich_people=not a.company_only)
            if a.product_evidence_file:
                cfg['tradewind']['product_evidence_file'] = a.product_evidence_file
            if a.no_contact_search:
                cfg['tradewind']['contact_search_enabled'] = False
            original_mine = tw.mine
            with patch.object(tw, 'settings', return_value={'key': 'replay-fixture', 'base': 'https://app.trade-wind.co', 'insight_prefix': '/api/insight', 'state': temp}), \
                 patch.object(tw, 'mine', side_effect=lambda profiles, config, path: original_mine(profiles, config, path, send=send)):
                companies = run_pipeline(str(source), str(out/(case+'.xlsx')), cfg)
            stats = cfg['_run_stats']['tradewind']
            summary['cases'].append({'case': case, 'candidates': len(companies),
                'companies': [{'name': c.company_name, 'website': c.website, 'title': c.contact_title,
                    'named_contact': bool(c.contact_name), 'mailbox_verified': c.email_verified,
                    'product_status': getattr(c, 'product_match_status', None)} for c in companies],
                'stop_reason': stats.get('stop_reason'),
                'product_unconfirmed': stats.get('product_unconfirmed_count', 0)})
            summary['cases'][-1].update(review_queue_count=stats.get('review_queue_count', 0),
                reviewed_product_matches=stats.get('reviewed_product_matches', 0))
            stats_path = out/(case+'.stats.json')
            saved = json.loads(stats_path.read_text())
            saved.update(mode='frozen_response_replay', actual_new_credits='0', network_calls=0,
                         warning='Ledger credit fields replay historical receipts; no actual spending')
            private_json(stats_path, saved)
    summary['missing_responses'] = missing
    private_json(out/'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if missing or any(c['stop_reason'] for c in summary['cases']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
