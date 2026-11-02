import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from contextlib import contextmanager


def now():
    return datetime.now(timezone.utc).isoformat()


def units(value):
    n = Decimal(str(value))
    if not n.is_finite() or n < 0 or n * 1000000 != int(n * 1000000):
        raise ValueError('Credits must be nonnegative with at most six decimal places')
    return int(n * 1000000)


def credits(n):
    return str(Decimal(n) / 1000000)


class Store:
    def __init__(self, root, namespace='offline'):
        self.root = Path(root) / namespace
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        path = self.root / 'state.sqlite3'
        if path.is_symlink():
            raise ValueError('Refusing symlink database')
        self.db = sqlite3.connect(path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        os.chmod(path, 0o600)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operations(
          id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, method TEXT NOT NULL, path TEXT NOT NULL,
          request TEXT NOT NULL, state TEXT NOT NULL, held INTEGER NOT NULL, charged INTEGER NOT NULL DEFAULT 0,
          billing_known INTEGER NOT NULL DEFAULT 0, request_id TEXT, task_id TEXT,
          response TEXT, created TEXT NOT NULL, updated TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS revisions(
          seq INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, payload TEXT NOT NULL, created TEXT NOT NULL);
        ''')
        self.db.execute("INSERT OR IGNORE INTO config VALUES('limit','0')")
        self.db.execute("INSERT OR IGNORE INTO config VALUES('baseline','0')")

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def close(self):
        self.db.close()

    def budget(self):
        cfg = dict(self.db.execute('SELECT key,value FROM config'))
        rows = self.db.execute('SELECT charged,held,state,billing_known FROM operations').fetchall()
        spent = sum(r['charged'] for r in rows) - int(cfg['baseline'])
        held = sum(r['held'] for r in rows)
        return {'limit': credits(int(cfg['limit'])), 'charged': credits(spent), 'reserved': credits(held),
                'available': str((Decimal(cfg['limit']) - spent - held) / 1000000),
                'unresolved_operations': sum(r['state'] in ('inflight','unknown','pending') or not r['billing_known'] for r in rows),
                'scope': 'local account namespace since last budget reset; not provider balance',
                'hard_cap': False}

    def set_budget(self, limit, reset=False):
        with self.transaction():
            if reset:
                if self.budget()['unresolved_operations']:
                    raise ValueError('Cannot reset budget with unresolved operations')
                total = self.db.execute('SELECT COALESCE(SUM(charged),0) FROM operations').fetchone()[0]
                self.db.execute("UPDATE config SET value=? WHERE key='baseline'", (str(total),))
            self.db.execute("UPDATE config SET value=? WHERE key='limit'", (str(units(limit)),))
        return self.budget()

    def billing_report(self):
        """Local reconciliation handoff; excludes request bodies and personal data."""
        with self.transaction():
            budget = self.budget()
            unresolved = []
            for row in self.db.execute('SELECT * FROM operations ORDER BY created'):
                if row['state'] not in ('inflight','unknown','pending') and row['billing_known']:
                    continue
                payload = json.loads(row['response'] or '{}')
                http = None
                match = re.search(r'HTTP (\d{3});', row['notes'])
                if match: http = int(match.group(1))
                if isinstance(payload, dict) and payload.get('http_status') is not None:
                    http = payload['http_status']
                unresolved.append({'operation_id':row['id'], 'request_id':row['request_id'],
                    'path':row['path'], 'state':row['state'], 'http_status':http,
                    'billing_known':bool(row['billing_known']), 'confirmed_credits':credits(row['charged']),
                    'reserved_credits':credits(row['held']), 'created':row['created']})
        return {'budget':budget, 'provider_balance':None, 'unresolved':unresolved,
                'paid_work_blocked':bool(unresolved), 'network_calls':0,
                'explanation':'本地累计预算不是账户余额；预留不是已扣费。费用未决时保留预留，不自动重试。',
                'next_action':('维护人员按 request_id 核对供应商回执；有证据后 reconcile。缺少回执不能猜零，不能仅靠换目录或加预算解锁。' if unresolved else '本地无未决费用；后续查询仍受授权范围和本地预算限制。')}

    def purge_operations(self, archive):
        from .security import private_json
        with self.transaction():
            if self.budget()['unresolved_operations']:
                raise ValueError('Cannot purge unresolved operations')
            if Path(archive).exists():
                raise ValueError('Archive already exists; do not overwrite audit history')
            backup={'archived_at':now(),'operations':[dict(r) for r in self.db.execute('SELECT * FROM operations')],
                    'config':dict(self.db.execute('SELECT key,value FROM config'))}
            private_json(archive,backup)
            self.db.execute('DELETE FROM operations')
            self.db.execute("UPDATE config SET value='0' WHERE key='baseline'")
        return {'archived':str(archive),'purged_operations':len(backup['operations']),'entities_preserved':True}

    def get(self, op_id):
        r = self.db.execute('SELECT * FROM operations WHERE id=?', (op_id,)).fetchone()
        return dict(r) if r else None

    def reserve(self, op_id, fingerprint, method, path, request, reserve, billable):
        with self.transaction():
            previous = self.get(op_id)
            if previous:
                if previous['fingerprint'] != fingerprint:
                    raise ValueError('Operation id already belongs to a different request')
                return previous
            # Unknown network outcomes block new chargeable work until reconciled.
            if billable and self.db.execute("SELECT 1 FROM operations WHERE state IN ('unknown','inflight','pending') OR billing_known=0 LIMIT 1").fetchone():
                raise ValueError('Reconcile unresolved billing before starting another paid operation')
            if billable and Decimal(self.budget()['available']) < Decimal(str(reserve)):
                raise ValueError('Local budget exhausted; adjust scope or budget')
            if billable and units(reserve) == 0:
                raise ValueError('Paid operations require a positive reserve')
            t = now()
            self.db.execute('INSERT INTO operations(id,fingerprint,method,path,request,state,held,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',
                            (op_id,fingerprint,method,path,json.dumps(request,ensure_ascii=False),'inflight',units(reserve),t,t))
        return None

    def finish(self, op_id, state, payload, amount=None, request_id=None, task_id=None, note='', cumulative=False):
        with self.transaction():
            row = self.get(op_id)
            known = amount is not None or bool(cumulative and row['billing_known'] and row['state'] in ('completed','failed','partial'))
            charged = units(amount) if amount is not None else row['charged']
            if cumulative:charged=max(charged,row['charged'])
            held = max(0, row['held'] - max(0, charged - row['charged']))
            if known and state not in ('pending','unknown','inflight'):
                held = 0
            self.db.execute('UPDATE operations SET state=?,held=?,charged=?,billing_known=?,request_id=COALESCE(?,request_id),task_id=COALESCE(?,task_id),response=?,updated=?,notes=? WHERE id=?',
                            (state,held,charged,int(known),request_id,task_id,json.dumps(payload,ensure_ascii=False),now(),note,op_id))

    def reconcile(self, op_id, amount, state, evidence):
        if not self.get(op_id):
            raise ValueError('Unknown operation')
        if state not in ('completed','failed','pending') or not evidence.strip():
            raise ValueError('Reconciliation requires terminal/pending state and evidence')
        row = self.get(op_id)
        self.finish(op_id,state,json.loads(row['response'] or '{}'),amount,note='reconciled: '+evidence)
        return self.get(op_id)

    def save_entity(self, record):
        payload = json.dumps(record,ensure_ascii=False,allow_nan=False)
        with self.transaction():
            self.db.execute('INSERT INTO revisions(entity_id,payload,created) VALUES(?,?,?)',(record['id'],payload,now()))
            self.db.execute('INSERT INTO entities VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated=excluded.updated',(record['id'],payload,now()))

    def entities(self):
        return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM entities ORDER BY rowid')]

    def history(self, entity_id):
        return [dict(r) for r in self.db.execute('SELECT * FROM revisions WHERE entity_id=? ORDER BY seq',(entity_id,))]

    def operations(self):
        return [dict(r) for r in self.db.execute('SELECT id,method,path,state,held,charged,billing_known,request_id,task_id,created,updated,notes FROM operations ORDER BY created')]

    def recover_refused(self, apply=False):
        from .network import legacy_refusal
        with self.transaction():
            rows=[dict(r) for r in self.db.execute('SELECT * FROM operations')]
            candidates=[r for r in rows if legacy_refusal(r)]
            if apply:
                self.db.execute('CREATE TABLE IF NOT EXISTS network_recoveries(id TEXT PRIMARY KEY, original TEXT NOT NULL, recovered_at TEXT NOT NULL)')
                for row in candidates:
                    self.db.execute('INSERT INTO network_recoveries VALUES(?,?,?)', (row['id'],json.dumps(row,ensure_ascii=False),now()))
                    payload=json.loads(row['response'])
                    payload.update(failure_phase='connect_refused',billing_basis='archived_rc4_winerror_10061',transport='legacy_unproven')
                    self.db.execute("UPDATE operations SET state='not_sent',held=0,charged=0,billing_known=1,response=?,updated=?,notes=? WHERE id=?",
                        (json.dumps(payload,ensure_ascii=False),now(),'Recovered rc4 WinError 10061; original preserved in network_recoveries',row['id']))
            return {'applied':apply,'matched_operations':[r['id'] for r in candidates],
                    'preserved_history':True,'network_calls':0}
