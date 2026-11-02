"""Failure isolation without inventing receipts or retrying chargeable calls."""
import json
from decimal import Decimal
import pytest
from src.tradewind_core.api import Client
from src.tradewind_core.store import Store
from src import tradewind as tw
from src.models import CustomerProfile


@pytest.mark.parametrize('amount', [None, 0, .1])
def test_email_500_receipt_controls_settlement(tmp_path, amount):
    store = Store(tmp_path); store.set_budget(2)
    payload = {'success':False, 'request_id':'req-error', 'error':{'code':'INTERNAL_ERROR'}}
    if amount is not None: payload['meta']={'billing':{'credits_charged':amount}}
    client = Client({'key':'fixture-key','base':'https://app.trade-wind.co','insight_prefix':'/api/insight'},store,
                    send=lambda *a:(500,payload))
    try:
        result=client.call('email.verify',{'type':'single','mode':'quick','email':'person@example.com'},'first')
        assert result['state']==('unknown' if amount is None else 'failed')
        assert store.budget()['reserved']==('0.1' if amount is None else '0')
        assert Decimal(store.budget()['charged'])==Decimal(str(amount or 0))
        report=store.billing_report()
        assert report['paid_work_blocked']==(amount is None)
        assert report['provider_balance'] is None
        assert 'person@example.com' not in json.dumps(report)
        if amount is None:
            assert report['unresolved'][0]['http_status']==500
            assert report['unresolved'][0]['request_id']=='req-error'
            with pytest.raises(ValueError,match='Reconcile'):
                client.call('email.verify',{'type':'single','mode':'quick','email':'other@example.com'},'second')
    finally: store.close()


@pytest.mark.parametrize('amount', [None, 0, .1])
def test_email_checks_follow_all_core_work_and_keep_partial_audit(tmp_path, monkeypatch, amount):
    monkeypatch.setenv('TRADEWIND_API_KEY','fixture-key')
    config={'tradewind':{'state_dir':str(tmp_path/'state'),'max_credits':'10','max_enrich':2,
        'require_product_match':False,'verify_email':True,'customs_enabled':True,
        'customs_start':'2026-01-01','customs_end':'2026-10-30',
        'customs_importer_country':'75','customs_exporter_country':'40'},
        'pipeline':{'target_countries':['US'],'max_results_per_customer':2}}
    calls=[]
    def ok(**data):
        return 200, {'success':True,'request_id':'req-'+str(len(calls)),
                     'meta':{'billing':{'credits_charged':.1}},**data}
    def send(method,url,body,headers,timeout):
        path=url.removeprefix('https://app.trade-wind.co'); calls.append((path,body))
        if path.endswith('/company/search'):
            return ok(companies=[{'name':n,'domain':n.lower()+'.example','country':'US'} for n in ('Alpha','Beta')])
        if path.endswith('/company/enrich'):
            d=body['identity']['domains'][0]
            return ok(company={'domain':d,'profile':{'description':'faucet distributor',
                'emails':['sales@'+d],'hq':{'country_code':'US'}}})
        if path.endswith('/people/search'): return ok(people=[])
        if path.endswith('/customs/search'): return ok(records=[])
        if path.endswith('/email/verify'):
            payload={'success':False,'request_id':'req-error','error':{'code':'INTERNAL_ERROR'}}
            if amount is not None: payload['meta']={'billing':{'credits_charged':amount}}
            return 500,payload
        raise AssertionError(path)
    seed=CustomerProfile(customer_id='seed',customer_name='Seed',product_tags=['faucet'])
    companies=tw.mine([seed],config,tmp_path/'run.xlsx',send=send)
    assert len(companies)==2 and all(not c.email_verified for c in companies)
    first_email=next(i for i,(p,_) in enumerate(calls) if p.endswith('/email/verify'))
    assert first_email==7  # discovery + 2 * (company, customs, people)
    assert len(calls)==(8 if amount is None else 9)
    report=config['_run_stats']['tradewind']
    assert not report['execution_audit']['coverage_complete']
    assert report['budget']['unresolved_operations']==(1 if amount is None else 0)
    assert bool(report['stop_reason'])==(amount is None)
    # Resume reuses both failed and successful operations; no paid retry.
    tw.mine([seed],config,tmp_path/'again.xlsx',send=lambda *a:pytest.fail('Repeated paid request'))
    assert config['_run_stats']['tradewind']['new_credits_known']=='0'


def test_report_screenshot_arithmetic_does_not_claim_provider_balance(tmp_path):
    store=Store(tmp_path);store.set_budget('350')
    try:
        store.reserve('spent','s','POST','/api/company/search',{},'78.57',True)
        store.finish('spent','completed',{},'78.57')
        store.reserve('pending','p','POST','/api/email/verify',{},'.1',True)
        store.finish('pending','unknown',{'success':False},None,request_id='req-error',note='HTTP 500; transport=live')
        before=store.get('pending')
        report=store.billing_report()
        assert report['budget']['available']=='271.33'
        assert report['budget']['charged']=='78.57'
        assert report['budget']['reserved']=='0.1'
        assert report['paid_work_blocked'] and report['provider_balance'] is None
        assert store.get('pending')==before
    finally: store.close()


@pytest.mark.parametrize('extra', [
    {'request_id':None}, {'task_id':'task'}, {'data':{'taskId':'task'}},
    {'status':'pending'}, {'status':'unknown'},
    {'meta':{'billing':{'credits_charged':0},'waterfall':{'async_pending':True}}},
])
def test_ambiguous_500_with_amount_still_blocks(tmp_path, extra):
    store=Store(tmp_path);store.set_budget(2)
    payload={'success':False,'request_id':'req','error':{'code':'INTERNAL_ERROR'},
             'meta':{'billing':{'credits_charged':0}},**extra}
    try:
        client=Client({'key':'fixture','base':'https://app.trade-wind.co','insight_prefix':'/api/insight'},store,
                      send=lambda *a:(500,payload))
        assert client.call('email.verify',{'type':'single','mode':'quick','email':'a@example.com'},'one')['state']=='unknown'
        assert store.budget()['reserved']=='0.1'
    finally: store.close()


@pytest.mark.parametrize('code', [401,402,403,409,429])
def test_account_or_rate_failure_stops_even_with_zero_receipt(tmp_path, monkeypatch, code):
    monkeypatch.setenv('TRADEWIND_API_KEY','fixture-key')
    cfg={'tradewind':{'state_dir':str(tmp_path),'max_credits':'2'}}
    session=tw.Session(cfg,send=lambda *a:(code,{'success':False,'request_id':'req',
        'error':{'code':'STOP'},'meta':{'billing':{'credits_charged':0}}}))
    try:
        assert session.call('email.verify',{'type':'single','mode':'quick','email':'a@example.com'}) is None
        assert session.stop_reason
        assert session.call('email.verify',{'type':'single','mode':'quick','email':'b@example.com'}) is None
        assert len(session.events)==1
    finally:session.store.close()


def test_billing_report_cli_rejects_missing_ledger_and_exports_existing(tmp_path, monkeypatch, capsys):
    import hashlib
    from scripts.tradewind_ops import main
    monkeypatch.setenv('TRADEWIND_API_KEY','fixture-key')
    state=tmp_path/'state';output=tmp_path/'handoff.json'
    args=['--state-dir',str(state),'billing-report','--output',str(output)]
    with pytest.raises(ValueError,match='未找到原账户账本'):
        main(args)
    assert not state.exists() and not output.exists()
    store=Store(state,hashlib.sha256(b'fixture-key').hexdigest()[:16]);store.set_budget(2)
    store.reserve('one','one','POST','/api/email/verify',{'email':'private@example.com'},'.1',True)
    store.finish('one','unknown',{'error':{'code':'INTERNAL_ERROR'}},None,request_id='req',note='HTTP 500; transport=live')
    before=store.get('one')
    try:
        assert main(args)==0
        report=json.loads(output.read_text())
        assert report['paid_work_blocked'] and report['network_calls']==0
        assert report['unresolved'][0]['request_id']=='req'
        assert store.get('one')==before
        assert 'private@example.com' not in output.read_text()+capsys.readouterr().out
    finally:store.close()
