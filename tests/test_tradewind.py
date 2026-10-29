import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from src import tradewind as tw
from src.models import CustomerProfile, SimilarCompany
from src.tradewind_core.api import Client
from src.tradewind_core.security import settings
from src.tradewind_core.store import Store
from scripts.build_skill import build


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv('TRADEWIND_API_KEY','fixture-key')
    return {'runtime':{'mode':'live'},'tradewind':{'state_dir':str(tmp_path/'state'),'max_credits':'3','max_enrich':1,'require_product_match':False},
            'pipeline':{'target_countries':['US'],'max_results_per_customer':3}}


def ok(**fields):
    return 200, {'success':True,'request_id':'req_fixture',
                 'meta':{'billing':{'credits_charged':.24}},**fields}


def seed():
    return CustomerProfile(customer_id='A1',customer_name='seed.example',product_tags=['faucet'])


def fake(send_log):
    def send(method,url,body,headers,timeout):
        send_log.append((url,body))
        assert url.startswith('https://app.trade-wind.co/')
        assert 'byok' not in json.dumps(body)
        if url.endswith('/company/search'):
            return ok(companies=[{'name':'Seed','domain':'seed.example'},
                {'name':'New Buyer','domain':'buyer.example','country':'US'},
                {'name':'New Buyer Duplicate','domain':'buyer.example'},
                {'name':'Foreign','domain':'foreign.example','country':'GB'}])
        if url.endswith('/company/enrich'):
            return ok(company={'name':'New Buyer','domain':'buyer.example','profile':{'description':'Faucet distributor',
                'hq':{'country_code':'US'},'emails':['sales@buyer.example']}})
        if url.endswith('/people/search'):
            return ok(people=[{'company_domain':'buyer.example','emails':['info@buyer.example']},
                {'first_name':'Alex','last_name':'Buyer','company_domain':'buyer.example','current_title':'Purchasing Director'}])
        if url.endswith('/people/enrich'):
            assert body['identity']['domain']=='buyer.example'
            assert body['waterfall']['reveal_phone'] is False
            return ok(person={'first_name':'Alex','last_name':'Buyer','company_domain':'buyer.example',
                              'current_title':'Purchasing Director','emails':[{'email':'alex@buyer.example'}]})
        raise AssertionError(url)
    return send


def test_full_discovery_enrichment_and_cached_resume(config,tmp_path):
    calls=[]
    companies=tw.mine([seed()],config,tmp_path/'one.xlsx',send=fake(calls))
    assert len(companies)==1
    c=companies[0]
    assert c.company_name=='New Buyer' and c.contact_name=='Alex Buyer'
    assert c.email=='alex@buyer.example' and not c.email_verified
    assert not c.hs_codes and c.customs_china_purchase is None
    assert len(calls)==4
    assert config['_run_stats']['tradewind']['discovery']=={'excluded_seed':1,'duplicates':1,'country_mismatch':1,'identity_missing':0}
    # Rerunning the exact query never repays, including dynamic enrichment.
    tw.mine([seed()],config,tmp_path/'two.xlsx',send=lambda *a:pytest.fail('Cache miss'))
    assert config['_run_stats']['tradewind']['new_credits_known']=='0'
    assert config['_run_stats']['tradewind']['reused_requests']==4


def test_budget_delivers_partial_candidates(config,tmp_path):
    config['tradewind']['max_credits']='0.24'
    calls=[]
    companies=tw.mine([seed()],config,tmp_path/'partial.xlsx',send=fake(calls))
    assert len(companies)==1 and len(calls)==1
    assert 'budget' in config['_run_stats']['tradewind']['stop_reason'].lower()
    assert (tmp_path/'partial.evidence.json').exists()


def test_unknown_billing_blocks_followups_and_resume(config,tmp_path):
    calls=[]
    def timeout(*args):calls.append(1);raise TimeoutError('fixture-key')
    assert tw.mine([seed()],config,tmp_path/'failed.xlsx',send=timeout)==[]
    assert len(calls)==1
    cfg=dict(config);cfg['tradewind']={**config['tradewind'],'cache_days':0}
    assert tw.mine([seed()],cfg,tmp_path/'again.xlsx',send=timeout)==[]
    assert len(calls)==1
    text=(tmp_path/'failed.evidence.json').read_text()
    assert 'fixture-key' not in text
    assert cfg['_run_stats']['tradewind']['budget']['reserved']=='0.24'


@pytest.mark.parametrize('person',[
    {'company_domain':'buyer.example','emails':['sales@buyer.example']},
    {'first_name':'Wrong','company_domain':'other.example','email':'wrong@other.example'},
    {'first_name':'Missing','email':'missing@buyer.example'},
    {'first_name':'Generic','company_domain':'buyer.example','email':'sales@buyer.example'},
    {'first_name':'External','company_domain':'buyer.example','email':'external@gmail.com'},
])
def test_no_false_contact_binding(person):
    c=SimilarCompany(company_name='Buyer',website='https://buyer.example',email='sales@buyer.example')
    assert not tw.apply_person(c,person,'fixture')
    assert c.contact_name is None and c.email=='sales@buyer.example'


def test_company_conflicts_preserve_identity():
    c=SimilarCompany(company_name='Buyer',website='https://buyer.example',country='US')
    assert not tw.apply_company(c,{'name':'Other','domain':'other.example','emails':['x@other.example']},'evidence')
    assert c.email is None and c.company_name=='Buyer'
    tw.apply_company(c,{'domain':'buyer.example','name':'New Name','hq':{'country_code':'GB'}},'evidence')
    assert c.country=='US' and c.company_name=='Buyer'
    assert 'Country conflict' in c.notes


def test_country_filter_is_not_fabricated_evidence(config,tmp_path):
    config['tradewind']['max_enrich']=0
    c=tw.mine([seed()],config,tmp_path/'missing.xlsx',send=lambda *a:ok(companies=[{'name':'New','domain':'new.example'}]))[0]
    assert c.country is None and c.country_confidence==0
    assert 'Country missing' in c.notes


def test_unknown_response_not_zero_credit_success(config,tmp_path):
    companies=tw.mine([seed()],config,tmp_path/'bad.xlsx',send=lambda *a:(200,{'success':True,'companies':[]}))
    assert companies==[]
    assert config['_run_stats']['tradewind']['budget']['unresolved_operations']==1


def test_allowlisted_host_and_no_redirect(monkeypatch):
    monkeypatch.setenv('TRADEWIND_API_BASE_URL','https://example.com')
    with pytest.raises(ValueError,match='Credentials may only'):
        settings()
    from src.tradewind_core.api import NoRedirect
    with pytest.raises(ValueError,match='Redirect refused'):
        NoRedirect().redirect_request(None,None,302,'',{},'https://example.com')


def test_customs_sample_exact_match_and_no_procurement_inference(config,tmp_path):
    config['tradewind'].update(customs_enabled=True,customs_start='2026-01-01',customs_end='2026-10-28',
                              customs_importer_country='75',customs_exporter_country='40')
    class Session:
        def call(self,*args):
            return {'operation_id':'customs','response':{'request_id':'req_customs','records':[
                {'id':'one','importer_company_name':'Buyer','hs_code':'8481','fob':'999','fob_unit':'USD'},
                {'id':'one','importer_company_name':'Buyer','hs_code':'8481'},
                {'id':'other','importer_company_name':'Other','hs_code':'9999'}]}}
    c=SimilarCompany(company_name='Buyer',website='https://buyer.example')
    tw.verify_customs(c,Session(),config['tradewind'])
    assert c.hs_codes==['8481']
    assert c.shipment_frequency.startswith('1 sampled customs records')
    assert c.customs_china_purchase is None and c.estimated_shipping_spend is None


def test_options_preflight_before_any_request(config,tmp_path):
    config['tradewind']['customs_enabled']=True
    with pytest.raises(ValueError):
        tw.mine([seed()],config,tmp_path/'bad.xlsx',send=lambda *a:pytest.fail('Network before preflight'))


def test_live_cli_never_calls_legacy_tools(config,tmp_path,monkeypatch):
    from src import cli
    for module,method in [(cli.buyer_discovery,'discover_buyers'),(cli.company_verify,'verify_companies'),
                          (cli.enrichment,'enrich_companies'),(cli.validation,'validate_companies')]:
        monkeypatch.setattr(module,method,lambda *a:pytest.fail('Legacy live path invoked'))
    monkeypatch.setenv('APIFY_API_TOKEN','forbidden')
    monkeypatch.setenv('HUNTER_API_KEY','forbidden')
    monkeypatch.setattr(tw,'mine',lambda *a:[SimilarCompany(company_name='New Buyer',notes='candidate')])
    result=cli.run_pipeline('tests/fixtures/mini_customers.csv',str(tmp_path/'output.xlsx'),config)
    assert result[0].fact_check_status=='pending'


def test_preview_no_key_no_network(config,monkeypatch):
    monkeypatch.delenv('TRADEWIND_API_KEY')
    p=tw.preview([seed()],config)
    assert p['network_calls']==0
    assert p['requests'][0]['body']['company']=={'keywords':{'include':['faucet']}}
    assert 'fixture-key' not in json.dumps(p) and 'api_key' not in json.dumps(p)


def test_internal_package_manifest_and_portable_doctor(tmp_path):
    key='tw_live_'+'a'*64
    keyfile=tmp_path/'key';keyfile.write_text(key)
    archive=tmp_path/'internal.zip'
    meta=build(archive,keyfile,'sps')
    assert meta['internal']
    with zipfile.ZipFile(archive) as z:
        names=z.namelist();prefix='similar-customer-miner/'
        manifest=json.loads(z.read(prefix+'MANIFEST.json'))
        assert set(names)=={prefix+n for n in manifest['files']}|{prefix+'MANIFEST.json'}
        for name,digest in manifest['files'].items():
            assert hashlib.sha256(z.read(prefix+name)).hexdigest()==digest
        assert [n for n in names if key.encode() in z.read(n)]==[prefix+'.credentials/tradewind.env']
        assert all('/.env' not in n and '/outputs/' not in n and '/local.yaml' not in n for n in names)
        assert manifest['distribution_profile'] == 'recipient'
        assert not any(n.startswith(prefix+'docs/') or n.startswith(prefix+'tests/') or
                       '/ENGINEERING' in n or '/validate_live.py' in n or '/replay_release.py' in n
                       for n in names)
        catalog = z.read(prefix+'references/api-catalog.json').decode()
        assert 'live_scope' not in catalog and 'live_verified' not in catalog
        # Removing internal reports must not leave recipient instructions with broken links.
        import re
        import posixpath
        from urllib.parse import unquote, urlsplit
        for name in names:
            if not name.endswith('.md'):
                continue
            content = z.read(name).decode()
            assert not any(report in content for report in
                           ['RELEASE_REVIEW.md', 'validation.json', 'package-validation.json'])
            for target in re.findall(r'\]\(([^)]+)\)', content):
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(parsed.path)))
                assert resolved in names, (name, target)
        z.extractall(tmp_path/'installed')
    import os
    env={**os.environ,'TRADEWIND_API_KEY':'unrelated-workspace-key'}
    r=subprocess.run([sys.executable,str(tmp_path/'installed'/prefix/'scripts/tradewind_ops.py'),'doctor'],cwd=tmp_path,env=env,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert key not in r.stdout+r.stderr
    info=json.loads(r.stdout)
    assert info['config_source']=='bundled' and info['distribution']['recipient']=='sps'


def test_public_package_has_no_credentials(tmp_path):
    zpath=tmp_path/'public.zip';build(zpath)
    with zipfile.ZipFile(zpath) as z:
        assert not any('.credentials' in n or 'DISTRIBUTION' in n for n in z.namelist())


def test_provider_guessed_email_stays_low_confidence():
    c=SimilarCompany(company_name='Buyer',website='https://buyer.example')
    assert tw.apply_person(c,{'first_name':'Alex','company_domain':'buyer.example','current_title':'Purchasing Manager',
        'emails':[{'email':'alex@buyer.example','status':'guessed','confidence':50}]},'fixture')
    assert c.email_confidence==.35 and not c.email_verified
    assert 'guessed' in c.notes


def test_demo_ignores_ambient_legacy_keys(monkeypatch):
    from tools.importyeti_tool import ImportYetiTool
    from tools.email_tool import EmailTool
    from tools.opencorporates_tool import OpenCorporatesTool
    for k in ['HUNTER_API_KEY','APIFY_API_TOKEN','OPENCORPORATES_API_TOKEN']:
        monkeypatch.setenv(k,'must-not-be-used')
    cfg={'runtime':{'mode':'demo'}}
    assert not ImportYetiTool(cfg).token
    assert not EmailTool(cfg).hunter_key
    assert not OpenCorporatesTool(cfg).token


def test_explicit_env_file_overrides_ambient_key(tmp_path,monkeypatch):
    monkeypatch.setenv('TRADEWIND_API_KEY','wrong-account')
    f=tmp_path/'chosen.env';f.write_text('TRADEWIND_API_KEY=chosen-account\n')
    assert settings(str(f))['key']=='chosen-account'
    with pytest.raises(ValueError,match='Explicit env file'):
        settings(str(tmp_path/'missing'))
