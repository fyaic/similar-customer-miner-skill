from datetime import datetime, timezone
import json
import pytest
from src import tradewind as tw
from src.cli import main
from src.execution_audit import build_audit, verify_ledger
from src.models import SimilarCompany, CustomerProfile
from tests.test_tradewind import ok


def test_no_implicit_execution(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(['--input', str(tmp_path/'nonexistent.csv'), '--output', str(tmp_path/'out.xlsx')])
    assert exc.value.code == 2
    assert not (tmp_path/'out.xlsx').exists()


@pytest.mark.parametrize('raw,safe,catch_all,expected', [
    ('safe', True, False, True), ('role_account', True, False, True),
    ('safe', False, False, False), ('safe', None, False, False),
    ('valid', False, False, False), ('safe', True, None, False),
    ('role_account', True, True, False), ('invalid', True, False, False)])
def test_provider_status_normalization(raw, safe, catch_all, expected):
    c=SimilarCompany(email='sales@example.com')
    tw.apply_verification(c, {'operation_id':'op','observed_at':datetime.now(timezone.utc).isoformat(),
        'response':{'result':{'email':c.email,'status':raw,'is_deliverable':True,
                             'is_safe_to_send':safe,'is_catch_all':catch_all}}})
    assert c.email_verified is expected
    assert c.email_verification_raw_status == raw
    assert c.email_is_catch_all is catch_all
    assert c.contact_name is None


def fixture_receipt(transport='live', reused=False):
    return {'operation':'company.search','context':{'seed':'one','query':0},'body':{},
        'state':'completed','billing_known':True,'request_id':'req','operation_id':'op',
        'response':{'companies':[]},'transport':transport,'reused':reused}


@pytest.mark.parametrize('transport,reused,classification', [
    ('live',False,'new_online_complete'),('live',True,'cached_complete'),
    ('injected',False,'partial_or_unproven'),('legacy',True,'partial_or_unproven')])
def test_provenance_and_empty_result(transport,reused,classification):
    audit=build_audit([{'seed':'one','query':0,'body':{}}],[],[fixture_receipt(transport,reused)],{})
    assert audit['classification']==classification
    assert audit['companies_planned']==0


@pytest.mark.parametrize('change', [{'request_id':None},{'billing_known':False},{'response':{'success':True}},{'state':'pending'}])
def test_bad_receipt_does_not_complete(change):
    audit=build_audit([{'seed':'one','query':0,'body':{}}],[],[{**fixture_receipt(),**change}],{})
    assert not audit['coverage_complete'] and not audit['new_online_case']


def test_company_cap_and_product_hold_remain_visible(tmp_path, monkeypatch):
    monkeypatch.setenv('TRADEWIND_API_KEY','fixture-key')
    cfg={'tradewind':{'state_dir':str(tmp_path),'max_credits':'5','max_enrich':1},
         'pipeline':{'target_countries':['US'],'max_results_per_customer':3}}
    def send(method,url,body,*a):
        if url.endswith('/company/search'):
            return ok(companies=[{'name':'Company '+str(i),'domain':f'c{i}.example','country':'US'} for i in range(3)])
        if url.endswith('/company/enrich'):return ok(company={'domain':'c0.example','description':'Unknown products'})
        pytest.fail('Contacts must not run before product review')
    tw.mine([CustomerProfile(customer_id='one',product_tags=['faucet'])],cfg,tmp_path/'out.xlsx',send)
    a=cfg['_run_stats']['tradewind']['execution_audit']
    assert a['companies_planned']==3 and a['companies_complete']==0
    assert sorted(c['disposition'] for c in a['companies'])==['pending','pending','product_review_required']
    assert not a['coverage_complete']


def test_receipt_tampering_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('TRADEWIND_API_KEY','fixture-key')
    s=tw.Session({'tradewind':{'state_dir':str(tmp_path),'max_credits':'2'}},lambda *a:ok(companies=[]))
    try:
        s.call('company.search',{'company':{'names':['Example']},'waterfall':{'source_order':['hunter']}})
        evidence=s.report()
        assert verify_ledger(evidence,s.store.db)==[]
        evidence['operations'][0]['body']['company']['names']=['Different']
        assert verify_ledger(evidence,s.store.db)
    finally:s.store.close()


def test_live_cli_rejects_partial_export_even_without_stop_reason(tmp_path, monkeypatch):
    from src import cli
    original=tw.mine
    monkeypatch.setenv('TRADEWIND_API_KEY','fixture-key')
    source=tmp_path/'seed.csv'
    source.write_text('id,name,main_products\none,seed.example,faucet\n')
    def send(method,url,body,*a):
        return ok(companies=[{'name':'New','domain':'new.example','description':'Faucet supplier','country':'US'}])
    monkeypatch.setattr(tw,'mine',lambda profiles,cfg,path: original(profiles,cfg,path,send))
    config=tmp_path/'config.yaml'
    config.write_text(f'tradewind:\n  max_enrich: 0\n  state_dir: {tmp_path}/state\n')
    output=tmp_path/'out.xlsx'
    assert cli.main(['--input',str(source),'--output',str(output),'--config',str(config),'--mode','live'])==2
    assert output.exists()
    stats=json.loads(output.with_suffix('.stats.json').read_text())['tradewind']
    assert stats['stop_reason'] is None
    assert not stats['execution_audit']['coverage_complete']


def test_mailbox_raw_status_and_unknown_boolean_survive_export(tmp_path):
    import pandas as pd
    from src.exporter import export_results
    from src.field_labels import to_canonical_columns
    c=SimilarCompany(company_name='Example',email_verification_status='valid',
        email_verification_raw_status='role_account',email_is_catch_all=False,email_is_safe_to_send=True)
    out=tmp_path/'result.xlsx'
    export_results([c],str(out),{})
    row=to_canonical_columns(pd.read_excel(out,sheet_name='Results')).iloc[0]
    assert row['email_verification_raw_status']=='role_account'
    assert row['email_verification_status']=='valid'
    assert not row['email_is_catch_all'] and row['email_is_safe_to_send']
