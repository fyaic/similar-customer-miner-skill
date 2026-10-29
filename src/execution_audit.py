"""Batch coverage is separate from API success and lead quality.

Local receipt checks establish execution provenance, not a cryptographic provider
attestation. Empty documented results count as executed queries, never as leads.
"""
import json
from datetime import datetime, timezone

KEYS = {'company.search': 'companies', 'company.enrich': 'company',
        'people.search': 'people', 'people.enrich': 'person',
        'email.verify': 'result', 'customs.search': 'records'}


def receipt_valid(event):
    payload = event.get('response') or {}
    if not isinstance(payload, dict):
        return False
    key = KEYS.get(event.get('operation'))
    nested = payload.get('data')
    value = payload.get(key) if key in payload else nested.get(key) if isinstance(nested, dict) else None
    present = key in payload or isinstance(nested, dict) and key in nested
    shaped = present and (isinstance(value, list) if key in {'companies', 'people', 'records'} else value is None or isinstance(value, dict))
    if event.get('operation') == 'email.verify':
        shaped = isinstance(payload.get('result') or nested, dict) and 'email' in (payload.get('result') or nested)
    return bool(key and shaped and event.get('state') == 'completed'
                and event.get('billing_known') and event.get('request_id'))


def build_audit(discovery, companies, events, options, stop_reason=None):
    def stage(name, context, body=None):
        matches = [e for e in events if e.get('operation') == name and e.get('context') == context
                   and (body is None or e.get('body') == body)]
        valid = [e for e in matches if receipt_valid(e)]
        return {'operation': name, 'status': 'covered' if valid else 'missing_receipt',
                'receipts': [e['operation_id'] for e in valid],
                'new': sum(not e.get('reused', False) for e in valid),
                'cached': sum(bool(e.get('reused')) for e in valid)}
    queries = [{**p, 'stage': stage('company.search', {'seed': p['seed'], 'query': p['query']}, p['body'])} for p in discovery]
    rows = []
    for c in companies:
        item = dict(c)
        context = {'seed': c['seed'], 'domain': c['domain']}
        disposition = c['disposition']
        stages = []
        if disposition != 'excluded_product':
            stages.append(stage('company.enrich', context))
        if disposition == 'qualified':
            if options.get('customs_enabled'):
                stages.append(stage('customs.search', context))
            if options.get('contact_search_enabled', True):
                stages.append(stage('people.search', context))
                if options.get('verify_email') and c.get('email'):
                    stages.append(stage('email.verify', context))
        item['stages'] = stages
        item['complete'] = disposition in {'qualified', 'excluded_product', 'excluded_identity'} and all(s['status'] == 'covered' for s in stages)
        item['mailbox_scope'] = ('not_requested' if not options.get('verify_email') or not options.get('contact_search_enabled', True)
                                 else 'address_available' if c.get('email') else 'no_address_returned')
        rows.append(item)
    valid = [e for e in events if receipt_valid(e)]
    new_live = [e for e in valid if e.get('transport') == 'live' and not e.get('reused')]
    # Every attempted business operation must have a receipt, including optional person enrichment.
    coverage_complete = bool(queries and valid) and not stop_reason and all(q['stage']['status'] == 'covered' for q in queries) and all(r['complete'] for r in rows) and all(receipt_valid(e) for e in events)
    provenance_ok = bool(valid) and all(e.get('transport') == 'live' for e in valid)
    complete_live = coverage_complete and provenance_ok
    return {'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(),
            'coverage_complete': coverage_complete, 'cached_or_live_complete': complete_live,
            'new_online_case': bool(complete_live and new_live),
            'classification': 'new_online_complete' if complete_live and new_live else 'cached_complete' if complete_live else 'partial_or_unproven',
            'new_live_receipts': len(new_live), 'cached_receipts': sum(bool(e.get('reused')) for e in valid),
            'injected_receipts': sum(e.get('transport') == 'injected' for e in valid),
            'legacy_unproven_receipts': sum(e.get('transport') == 'legacy' for e in valid),
            'companies_planned': len(rows), 'companies_complete': sum(r['complete'] for r in rows),
            'discovery': queries, 'companies': rows, 'options': options_for_audit(options),
            'stop_reason': stop_reason,
            'scope': 'Selected candidates within per-seed limit; not exhaustive market coverage. Product review holds remain incomplete. Mailbox validity does not prove employment or authority.'}


def options_for_audit(options):
    return {k: options.get(k, default) for k, default in {
        'contact_search_enabled': True, 'verify_email': False, 'customs_enabled': False,
        'people_source': 'apollo', 'max_enrich': 5, 'require_product_match': True}.items()}


def verify_ledger(evidence, db):
    """Recheck local operation ids, normalized request bodies and response snapshots."""
    errors = []
    for e in evidence.get('operations', []):
        if not e.get('operation_id'):
            errors.append('Missing operation id'); continue
        row = db.execute('SELECT * FROM operations WHERE id=?', (e['operation_id'],)).fetchone()
        if row is None:
            errors.append('Receipt not in supplied ledger: '+e['operation_id']); continue
        row = dict(row)
        from src.tradewind_core.api import prepare
        spec = prepare(e['operation'], e['body'])
        if (row['path'] != spec['path'] or row['method'] != spec['method']
                or json.loads(row['request'])['body'] != spec['body']
                or json.loads(row['response'] or '{}') != e.get('response', {})
                or row['state'] != e.get('state') or bool(row['billing_known']) != e.get('billing_known')
                or row['request_id'] != e.get('request_id')):
            errors.append('Receipt mismatch: '+e['operation_id'])
        transport = 'live' if 'transport=live' in row['notes'] else 'injected' if 'transport=injected' in row['notes'] else 'legacy'
        if not e.get('reused') and evidence.get('run_started_at') and row['created'] < evidence['run_started_at']:
            errors.append('Historical receipt claimed as new: '+e['operation_id'])
        if transport != e.get('transport'):
            errors.append('Transport mismatch: '+e['operation_id'])
    return errors
