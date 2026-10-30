import errno
import json
import socket
import urllib.error
import pytest
from src.tradewind_core.network import connection_refused, diagnose, legacy_refusal, proxy_summary
from src.tradewind_core.api import Client, transport
from src.tradewind_core.store import Store
from src import tradewind as tw


def refused():
    error=ConnectionRefusedError(10061,'connection refused')
    error.winerror=10061
    return urllib.error.URLError(error)


@pytest.mark.parametrize('error,expected',[(refused(),True),
    (urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED,'refused')),True),
    (urllib.error.URLError(TimeoutError('timed out')),False),
    (urllib.error.URLError(ConnectionResetError('reset')),False),
    (urllib.error.URLError('10061 in a string is not typed evidence'),False),
    (ValueError('failure after response'),False)])
def test_preconnect_classification(error,expected):
    assert connection_refused(error) is expected


def test_refused_releases_reserve_no_automatic_retry_and_preserves_origin(tmp_path,monkeypatch):
    monkeypatch.setenv('TRADEWIND_API_KEY','fixture-key')
    calls=[]
    def send(*args):calls.append(1);raise refused()
    cfg={'tradewind':{'state_dir':str(tmp_path),'max_credits':'1'}}
    body={'company':{'names':['Example']},'waterfall':{'source_order':['hunter']}}
    for _ in range(2):
        session=tw.Session(cfg,send)
        try:
            assert session.call('company.search',body) is None
            e=session.events[0]
            assert e['state']=='not_sent' and e['transport']=='injected'
            assert session.store.budget()['reserved']=='0'
            assert session.store.budget()['unresolved_operations']==0
            assert session.call('company.search',body) is None
        finally:session.store.close()
    assert len(calls)==2


def test_timeout_still_blocks_new_paid_request(tmp_path):
    store=Store(tmp_path)
    store.set_budget(2)
    def send(*args):raise urllib.error.URLError(TimeoutError('timed out'))
    client=Client({'key':'fixture','base':'https://app.trade-wind.co','insight_prefix':'/api/insight'},store,send)
    body={'company':{'names':['Example']},'waterfall':{'source_order':['hunter']}}
    try:
        assert client.call('company.search',body,'one')['state']=='unknown'
        with pytest.raises(ValueError,match='unresolved'):client.call('company.search',body,'two')
        assert store.budget()['reserved']=='0.24'
    finally:store.close()


def seed_legacy(store,op='legacy',**updates):
    store.set_budget(2)
    store.reserve(op,op,'POST','/api/company/search',{'body':{}},'.24',True)
    payload={'error_type':'URLError','message':'<urlopen error [WinError 10061] connection refused>', 'http_status':None,'payload':None}
    payload.update(updates)
    store.finish(op,'unknown',payload,None,note='Transport/protocol failed; reconcile before retry')


def test_recover_exact_rc4_case_keeps_original_and_is_idempotent(tmp_path):
    store=Store(tmp_path)
    try:
        seed_legacy(store)
        old=store.get('legacy')
        assert store.recover_refused()['matched_operations']==['legacy']
        assert store.get('legacy')==old
        store.recover_refused(True)
        assert store.get('legacy')['state']=='not_sent'
        assert store.budget()['reserved']=='0' and store.budget()['unresolved_operations']==0
        archived=json.loads(store.db.execute('SELECT original FROM network_recoveries').fetchone()[0])
        assert archived==old
        assert store.recover_refused(True)['matched_operations']==[]
    finally:store.close()


@pytest.mark.parametrize('updates',[{'http_status':503},{'payload':{'request_id':'x'}},
    {'error_type':'TimeoutError'},{'message':'connection timed out'},{'message':'WinError 10054 reset'}])
def test_recovery_does_not_clear_other_unknowns(tmp_path,updates):
    store=Store(tmp_path)
    try:
        seed_legacy(store,**updates)
        assert not store.recover_refused(True)['matched_operations']
        assert store.budget()['unresolved_operations']==1
    finally:store.close()


def test_actual_closed_local_socket_uses_production_transport_without_credentials():
    # Reserve then close a fresh loopback port; no third-party request or key.
    server=socket.socket()
    server.bind(('127.0.0.1',0))
    url='http://127.0.0.1:'+str(server.getsockname()[1])
    server.close()
    with pytest.raises(urllib.error.URLError) as failure:
        transport('POST',url,{}, {},2,proxy_mode='direct')
    assert connection_refused(failure.value)


def test_proxy_diagnostics_never_expose_auth(monkeypatch):
    monkeypatch.setattr('urllib.request.getproxies',lambda:{'https':'http://secretuser:secretpass@127.0.0.1:7890'})
    monkeypatch.setattr('urllib.request.proxy_bypass',lambda host:False)
    result=proxy_summary('https://app.trade-wind.co/')
    assert result=={'mode':'system','route':'proxy','host':'127.0.0.1','port':7890}
    class Opener:
        def open(self,request,timeout):
            assert request.get_method()=='HEAD'
            assert not request.has_header('Authorization')
            raise refused()
    monkeypatch.setattr('urllib.request.build_opener',lambda *args:Opener())
    result=diagnose()
    assert not result['network_reachable'] and result['business_api_calls']==0
    assert 'secret' not in json.dumps(result)


def test_trial_preview_is_bounded(tmp_path):
    from src.cli import main
    source=tmp_path/'seeds.csv';out=tmp_path/'preview.json'
    source.write_text('id,name,main_products\na,first.example,sofas\nb,second.example,tables\n')
    assert main(['--input',str(source),'--output',str(out),'--dry-run','--trial','--max-results','100'])==0
    data=json.loads(out.read_text())
    assert len(data['requests'])==1 and data['requests'][0]['body']['per_page']==3
    assert data['max_enrich']==1


def test_real_closed_proxy_is_live_not_legacy(tmp_path,monkeypatch):
    server=socket.socket();server.bind(('127.0.0.1',0));port=server.getsockname()[1];server.close()
    monkeypatch.setattr('urllib.request.getproxies',lambda:{'https':f'http://127.0.0.1:{port}'})
    monkeypatch.setattr('urllib.request.proxy_bypass',lambda host:False)
    store=Store(tmp_path);store.set_budget(2)
    try:
        client=Client({'key':'fixture-only','base':'https://app.trade-wind.co','insight_prefix':'/api/insight'},store)
        result=client.call('company.search',{'company':{'names':['Example']},'waterfall':{'source_order':['hunter']}},'refused-proxy',timeout=2)
        assert result['state']=='not_sent' and result['response']['transport']=='live'
        assert 'transport=live' in store.get('refused-proxy')['notes']
        assert store.budget()['charged']=='0' and store.budget()['reserved']=='0'
    finally:store.close()


def test_cli_refusal_automatically_diagnoses_without_second_paid_query(tmp_path,monkeypatch):
    from src import cli
    from src.tradewind_core import network
    monkeypatch.setenv('TRADEWIND_API_KEY','fixture-key')
    source=tmp_path/'seed.csv';source.write_text('id,name,main_products\none,seed.example,sofas\n')
    config=tmp_path/'config.yaml';config.write_text(f'tradewind:\n  state_dir: {tmp_path}/state\n')
    original=tw.mine;calls=[];diagnoses=[]
    def send(*args):calls.append(1);raise refused()
    monkeypatch.setattr(tw,'mine',lambda ps,cfg,path:original(ps,cfg,path,send))
    def diagnose(mode):
        diagnoses.append(mode)
        return {'network_reachable':False,'credentials_sent':False,'business_api_calls':0,'next_action':'代理端口连接被拒绝'}
    monkeypatch.setattr(network,'diagnose',diagnose)
    out=tmp_path/'out.xlsx'
    assert cli.main(['--input',str(source),'--output',str(out),'--config',str(config),'--mode','live','--trial'])==2
    assert calls==[1] and diagnoses==['system']
    assert '代理端口连接被拒绝' in out.with_suffix('.status.md').read_text()
    assert json.loads(out.with_suffix('.diagnostics.json').read_text())['business_api_calls']==0
