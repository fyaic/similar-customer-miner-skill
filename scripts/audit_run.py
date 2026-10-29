#!/usr/bin/env python3
"""Recompute batch coverage and check receipts against the original local ledger."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.execution_audit import build_audit, verify_ledger


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('evidence', help='Run .evidence.json')
    p.add_argument('--ledger', required=True, help='Original account state.sqlite3')
    p.add_argument('--allow-cached', action='store_true')
    a = p.parse_args(argv)
    evidence = json.loads(Path(a.evidence).read_text())
    original = evidence.get('execution_audit', {})
    if not original.get('discovery'):
        print('Missing execution scope; audit failed'); return 2
    db = sqlite3.connect(Path(a.ledger).resolve().as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        errors = verify_ledger(evidence, db)
    finally:
        db.close()
    audit = build_audit(original['discovery'], original['companies'], evidence['operations'],
                        original['options'], evidence.get('stop_reason'))
    ok = not errors and (audit['new_online_case'] or a.allow_cached and audit['cached_or_live_complete'])
    print(json.dumps({'passed': bool(ok), 'classification': audit['classification'],
                      'companies_planned': audit['companies_planned'], 'companies_complete': audit['companies_complete'],
                      'new_live_receipts': audit['new_live_receipts'], 'cached_receipts': audit['cached_receipts'],
                      'errors': errors}, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
